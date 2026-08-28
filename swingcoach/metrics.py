"""Swing metrics computed from a segmented SwingRecord.

All computations use only what a single wrist-mounted IMU can honestly
provide. Free acceleration from the DOT is gravity-removed and expressed in
the EARTH frame, so integrating it over the short downswing window gives
world-frame hand velocity with minimal drift.

Conventions (after a heading reset at address, aimed down the target line):
  +X = toward the target, +Y = left of target, +Z = up  (ENU-style)
  Path angle > 0  => in-to-out (right of target line for a RH golfer)
  Attack angle > 0 => hitting up on the ball
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .detector import SwingRecord

GYRO_CLIP_DPS = 1900.0     # near the DOT's +/-2000 deg/s range
ACC_CLIP_MS2 = 150.0       # near the +/-16 g (157 m/s^2) range
DEFAULT_LEVER_M = 1.05     # wrist -> clubhead distance, driver ~1.05-1.15 m


@dataclass
class SwingMetrics:
    # timing
    backswing_s: float = 0.0
    downswing_s: float = 0.0
    tempo_ratio: float = 0.0          # backswing / downswing (ideal ~3.0)
    # speed
    hand_speed_mps: float = 0.0       # wrist speed at impact
    hand_speed_mph: float = 0.0
    peak_gyro_dps: float = 0.0
    omega_impact_dps: float = 0.0     # wrist angular velocity at impact
    club_speed_est_mph: float = 0.0   # v_hand + omega x lever (estimate!)
    # geometry
    backswing_rotation_deg: float = 0.0   # total rotation takeaway -> top
    swing_plane_tilt_deg: float = 0.0     # plane tilt from horizontal
    path_angle_deg: float = 0.0           # + in-to-out, - out-to-in
    attack_angle_deg: float = 0.0         # + up, - down
    # release timing: when peak wrist rotation occurs within the downswing
    # (0 = at the top -> casting; ~0.8-1.0 = late release, near impact)
    release_fraction: float = 0.0
    # transition quality
    pause_top_s: float = 0.0            # quiet time at the top of the backswing
    transition_build_dps2: float = 0.0  # rotational build rate out of transition
    # forearm rotation about the sensor/forearm long axis (pronation/supination).
    # Sign and scale depend on mounting orientation — interpret RELATIVE to the
    # player's own baseline, with the sensor strapped the same way each session.
    forearm_rotation_deg: float = 0.0     # net rotation, top -> impact
    forearm_rate_impact_dps: float = 0.0  # rotation rate at impact
    # data quality
    gyro_clipped: bool = False
    acc_clipped: bool = False
    n_downswing_samples: int = 0
    notes: List[str] = field(default_factory=list)


def compute_metrics(rec: SwingRecord, lever_m: float = DEFAULT_LEVER_M) -> SwingMetrics:
    m = SwingMetrics()
    s = rec.samples
    m.backswing_s = rec.t_top - rec.t_takeaway
    m.downswing_s = rec.t_impact - rec.t_top
    m.tempo_ratio = m.backswing_s / m.downswing_s if m.downswing_s > 0 else 0.0

    t = np.array([x.t for x in s])
    acc = np.array([[x.ax, x.ay, x.az] for x in s])       # earth frame, m/s^2
    gyr = np.array([[x.gx, x.gy, x.gz] for x in s])       # body frame, deg/s
    gyro_mag = np.linalg.norm(gyr, axis=1)

    i0, i1, i2 = rec.i_takeaway, rec.i_top, rec.i_impact

    # --- clipping flags ------------------------------------------------------
    seg = slice(i1, i2 + 1)
    m.gyro_clipped = bool(np.any(np.abs(gyr[seg]) > GYRO_CLIP_DPS))
    m.acc_clipped = bool(np.any(np.abs(acc[seg]) > ACC_CLIP_MS2))
    m.n_downswing_samples = i2 - i1 + 1
    if m.gyro_clipped:
        m.notes.append("Gyro saturated during downswing; speed metrics are a floor, not a ceiling.")
    if m.acc_clipped:
        m.notes.append("Accelerometer saturated near impact; hand speed is a floor "
                       "and path/attack angles are unreliable for this swing.")
    if m.n_downswing_samples < 8:
        m.notes.append("Few samples in downswing at this output rate; timing is approximate.")

    # --- hand velocity: integrate earth-frame free acceleration -------------
    # Assume hand velocity ~0 at the top of the backswing (brief pause).
    # The ball-strike shock (impact sample and its tail) is not part of the
    # swing motion — interpolate across it so it doesn't pollute the integral.
    acc_i = acc.copy()
    a_lo, a_hi = i2 - 1, min(i2 + 3, len(s) - 1)
    if a_hi > a_lo + 1:
        for k, idx in enumerate(range(a_lo + 1, a_hi)):
            u = (k + 1) / (a_hi - a_lo)
            acc_i[idx] = acc[a_lo] * (1 - u) + acc[a_hi] * u
    vel = np.zeros_like(acc_i)
    for i in range(i1 + 1, len(s)):
        dt = t[i] - t[i - 1]
        vel[i] = vel[i - 1] + acc_i[i] * dt
    v_impact = vel[i2]
    m.hand_speed_mps = float(np.linalg.norm(v_impact))
    m.hand_speed_mph = m.hand_speed_mps * 2.23694

    # --- club speed estimate: v_club ~ v_hand + omega * lever ----------------
    omega_impact_rad = float(np.deg2rad(gyro_mag[max(i1, i2 - 1):i2 + 1].max()))
    m.omega_impact_dps = float(np.rad2deg(omega_impact_rad))
    m.peak_gyro_dps = float(gyro_mag[i1:i2 + 1].max())
    v_club = m.hand_speed_mps + omega_impact_rad * lever_m
    m.club_speed_est_mph = v_club * 2.23694

    # --- backswing rotation: integrate gyro magnitude takeaway -> top -------
    rot = 0.0
    for i in range(i0 + 1, i1 + 1):
        rot += gyro_mag[i] * (t[i] - t[i - 1])
    m.backswing_rotation_deg = float(rot)

    # --- swing plane: fit plane to downswing hand-velocity directions --------
    vseg = vel[i1 + 1:i2 + 1]
    speeds = np.linalg.norm(vseg, axis=1)
    good = speeds > max(0.5, 0.1 * speeds.max() if len(speeds) else 0.5)
    if good.sum() >= 3:
        dirs = vseg[good] / speeds[good, None]
        # plane through origin: normal = smallest singular vector
        _, _, vt = np.linalg.svd(dirs)
        normal = vt[-1]
        if normal[2] < 0:
            normal = -normal
        # tilt of the plane from horizontal = angle between normal and vertical
        m.swing_plane_tilt_deg = float(np.rad2deg(
            np.arccos(np.clip(normal[2], -1.0, 1.0))))
    else:
        m.notes.append("Not enough clean velocity samples to fit a swing plane.")

    # --- path & attack angle at impact (needs heading reset at address) -----
    if m.hand_speed_mps > 1.0:
        vx, vy, vz = v_impact
        horiz = float(np.hypot(vx, vy))
        if horiz > 0.5:
            # angle of horizontal velocity relative to +X (target line);
            # +Y is left, so positive atan2(vy,vx) = out-to-in for RH golfer
            m.path_angle_deg = float(-np.rad2deg(np.arctan2(vy, vx)))
            m.attack_angle_deg = float(np.rad2deg(np.arctan2(vz, horiz)))

    # --- release timing -------------------------------------------------------
    if i2 > i1:
        i_peak = int(np.argmax(gyro_mag[i1:i2 + 1])) + i1
        m.release_fraction = float((t[i_peak] - t[i1]) / (t[i2] - t[i1])) \
            if t[i2] > t[i1] else 0.0

    # --- transition quality ----------------------------------------------------
    # Pause at the top: contiguous quiet window around i_top.
    PAUSE_THRESH = 60.0  # deg/s
    if gyro_mag[i1] < PAUSE_THRESH:
        j0 = i1
        while j0 - 1 > i0 and gyro_mag[j0 - 1] < PAUSE_THRESH:
            j0 -= 1
        j1 = i1
        while j1 + 1 < i2 and gyro_mag[j1 + 1] < PAUSE_THRESH:
            j1 += 1
        m.pause_top_s = float(t[j1] - t[j0])
    # Build rate: how fast rotation ramps from the top to 50% of downswing peak.
    peak_ds = float(gyro_mag[i1:i2 + 1].max())
    k = i1
    while k < i2 and gyro_mag[k] < 0.5 * peak_ds:
        k += 1
    dt50 = float(t[k] - t[i1])
    if dt50 > 0:
        m.transition_build_dps2 = float((gyro_mag[k] - gyro_mag[i1]) / dt50)

    # --- forearm rotation (about sensor x / forearm long axis) -----------------
    rot_x = 0.0
    for i in range(i1 + 1, i2 + 1):
        rot_x += gyr[i, 0] * (t[i] - t[i - 1])
    m.forearm_rotation_deg = float(rot_x)
    m.forearm_rate_impact_dps = float(gyr[i2, 0])

    return m
