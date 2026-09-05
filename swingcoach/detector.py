"""Swing detection: segment a continuous IMU stream into individual swings.

Strategy: rather than guessing swing phases in real time (fragile), we detect
that *a swing happened* — a burst of angular velocity well above anything a
waggle or walk produces — wait for the sensor to go quiet again, then segment
the buffered window retrospectively:

    impact   = peak free-acceleration magnitude in the high-speed burst
    top      = last local minimum of gyro magnitude before impact
    takeaway = last time gyro magnitude was below the quiet threshold
               before the top

This is robust at 60 Hz and fits a post-swing summary workflow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .protocol import Sample

# Tunable thresholds (deg/s unless noted)
QUIET_GYRO = 40.0          # below this = hands quiet
SWING_GYRO = 450.0         # a burst above this = definitely a swing
MIN_SWING_PEAK_ACC = 20.0  # m/s^2; reject slow rehearsal moves
QUIET_TIME = 0.6           # s of quiet to close out a swing
PRE_BUFFER = 3.0           # s of history to keep before the burst
MAX_SWING_WINDOW = 6.0     # s; give up if it never goes quiet


@dataclass
class SwingRecord:
    """A segmented swing: raw samples plus event indices into `samples`."""
    samples: List[Sample]
    i_takeaway: int
    i_top: int
    i_impact: int
    i_finish: int

    @property
    def t_takeaway(self) -> float:
        return self.samples[self.i_takeaway].t

    @property
    def t_top(self) -> float:
        return self.samples[self.i_top].t

    @property
    def t_impact(self) -> float:
        return self.samples[self.i_impact].t


@dataclass
class SwingDetector:
    """Feed samples one at a time; returns a SwingRecord when a swing completes."""
    _buf: List[Sample] = field(default_factory=list)
    _in_swing: bool = False
    _burst_t: float = 0.0
    _quiet_since: Optional[float] = None

    def feed(self, s: Sample) -> Optional[SwingRecord]:
        self._buf.append(s)

        if not self._in_swing:
            # Trim buffer to the pre-roll window
            t0 = s.t - PRE_BUFFER
            while len(self._buf) > 2 and self._buf[0].t < t0:
                self._buf.pop(0)
            if s.gyro_mag > SWING_GYRO:
                self._in_swing = True
                self._burst_t = s.t
                self._quiet_since = None
            return None

        # In a swing: wait for sustained quiet (or timeout)
        if s.gyro_mag < QUIET_GYRO:
            if self._quiet_since is None:
                self._quiet_since = s.t
            if s.t - self._quiet_since >= QUIET_TIME:
                return self._finalize()
        else:
            self._quiet_since = None

        if s.t - self._burst_t > MAX_SWING_WINDOW:
            return self._finalize()
        return None

    def _finalize(self) -> Optional[SwingRecord]:
        buf, self._buf = self._buf, []
        self._in_swing = False
        self._quiet_since = None
        rec = segment_swing(buf)
        return rec


def segment_swing(samples: List[Sample]) -> Optional[SwingRecord]:
    """Retrospectively locate takeaway / top / impact in a swing window."""
    n = len(samples)
    if n < 20:
        return None
    gyro = [s.gyro_mag for s in samples]
    acc = [s.acc_mag for s in samples]

    # Impact: the ball-strike shock is the sharpest change in acceleration
    # (peak jerk) inside the region of high angular velocity. Jerk stays
    # reliable even when the accelerometer clips on fast swings.
    peak_gyro = max(gyro)
    if peak_gyro < SWING_GYRO:
        return None
    i_peak_gyro = gyro.index(peak_gyro)
    # The strike happens while the club is moving FAST. Search barely before
    # the wrist-speed peak (release timing) but generously after (a clipped
    # gyro plateau puts the true peak later), and require high angular
    # velocity at the candidate: an aggressive transition produces its own
    # sharp acceleration spike early in the downswing, and at 60 Hz that can
    # out-jerk the undersampled ball-strike shock — the field-observed
    # systematic early-impact bug.
    lo = _idx_at(samples, samples[i_peak_gyro].t - 0.06, default=0)
    hi = _idx_at(samples, samples[i_peak_gyro].t + 0.18, default=n - 1)
    lo = max(lo, 1)

    def jerk(i: int) -> float:
        dax = samples[i].ax - samples[i - 1].ax
        day = samples[i].ay - samples[i - 1].ay
        daz = samples[i].az - samples[i - 1].az
        return (dax * dax + day * day + daz * daz) ** 0.5

    cands = [i for i in range(lo, hi + 1) if gyro[i] >= 0.5 * peak_gyro]
    if not cands:
        cands = list(range(lo, hi + 1))
    i_impact = max(cands, key=jerk)
    # Walk back to the shock ONSET so impact isn't timed at the tail of the
    # spike (the shock spans 2-3 samples at 60 Hz) — but never more than
    # 3 samples, so the onset can't slide down a long acceleration ramp.
    jmax = jerk(i_impact)
    steps = 0
    while i_impact - 1 > lo and steps < 3 and jerk(i_impact - 1) > 0.4 * jmax:
        i_impact -= 1
        steps += 1
    if max(acc[lo:hi + 1]) < MIN_SWING_PEAK_ACC:
        return None  # too gentle: a rehearsal or handling motion

    # Top of backswing: last local minimum of gyro magnitude before the
    # downswing surge, searching back from impact.
    i_top = None
    i = i_impact - 2
    while i > 1:
        if gyro[i] <= gyro[i - 1] and gyro[i] <= gyro[i + 1] and \
                gyro[i] < 0.5 * peak_gyro:
            i_top = i
            break
        i -= 1
    if i_top is None:
        i_top = max(1, i_impact - int(0.25 / _dt(samples)))

    # Takeaway: walk back from the top, skipping any quiet pause AT the top,
    # then back through the backswing motion to the last quiet sample.
    i = i_top
    while i > 0 and gyro[i] < QUIET_GYRO:   # pause at the top
        i -= 1
    while i > 0 and gyro[i] >= QUIET_GYRO:  # backswing motion
        i -= 1
    i_takeaway = i

    # Finish: first sample after impact where things go quiet-ish.
    i_finish = n - 1
    for i in range(i_impact, n):
        if gyro[i] < QUIET_GYRO * 1.5:
            i_finish = i
            break

    # Sanity: ordering and plausible durations
    if not (i_takeaway < i_top < i_impact):
        return None
    backswing = samples[i_top].t - samples[i_takeaway].t
    downswing = samples[i_impact].t - samples[i_top].t
    if not (0.1 < backswing < 3.0 and 0.08 < downswing < 1.0):
        return None

    return SwingRecord(samples, i_takeaway, i_top, i_impact, i_finish)


def _dt(samples: List[Sample]) -> float:
    span = samples[-1].t - samples[0].t
    return span / max(1, len(samples) - 1)


def _idx_at(samples: List[Sample], t: float, default: int) -> int:
    for i, s in enumerate(samples):
        if s.t >= t:
            return i
    return default
