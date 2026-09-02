"""Rule-based coaching feedback from swing metrics.

Each rule maps a metric band to a short, actionable cue. Priorities:
  1 = fix this first, 2 = worth attention, 3 = fine-tuning.
The formatter prints the post-swing summary a player sees on the range.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .metrics import SwingMetrics


@dataclass
class Cue:
    priority: int
    title: str
    detail: str


def coach(m: SwingMetrics) -> List[Cue]:
    cues: List[Cue] = []

    # --- tempo ---------------------------------------------------------------
    if m.tempo_ratio > 0:
        if m.tempo_ratio < 2.2:
            cues.append(Cue(1, "Backswing is rushed",
                "Your tempo ratio is {:.1f}:1 (tour average ~3:1). Feel like the "
                "backswing takes twice as long — try counting '1-2-3' back, '1' down."
                .format(m.tempo_ratio)))
        elif m.tempo_ratio > 4.0:
            cues.append(Cue(2, "Backswing is sluggish",
                "Tempo ratio {:.1f}:1 is slower than the ~3:1 ideal. A slightly "
                "brisker takeaway keeps the swing connected and athletic."
                .format(m.tempo_ratio)))
        else:
            cues.append(Cue(3, "Tempo is in the good zone",
                "{:.1f}:1 backswing-to-downswing — close to the 3:1 tour benchmark. "
                "Keep that rhythm.".format(m.tempo_ratio)))

    # --- release timing --------------------------------------------------------
    if 0 < m.release_fraction < 0.55:
        cues.append(Cue(1, "Early release (casting)",
            "Peak wrist speed arrived only {:.0f}% of the way into the downswing. "
            "You're spending speed before impact — feel the wrists stay 'set' "
            "until your hands reach hip height.".format(m.release_fraction * 100)))
    elif m.release_fraction >= 0.75:
        cues.append(Cue(3, "Nice late release",
            "Peak wrist speed at {:.0f}% of the downswing — speed is being "
            "delivered at the ball, not wasted early.".format(m.release_fraction * 100)))

    # --- transition quality ------------------------------------------------------
    if m.pause_top_s > 0.35:
        cues.append(Cue(2, "Stalling at the top",
            "You sat at the top for {:.2f}s. A brief settle is good; a full stop "
            "kills the stretch-shorten cycle — feel the lower body start down as "
            "the arms finish going back.".format(m.pause_top_s)))
    elif 0 < m.tempo_ratio < 2.4 and m.pause_top_s < 0.04:
        cues.append(Cue(2, "No pause at the top",
            "The club never settled before the downswing — transition is doing "
            "the rushing. Feel one beat of stillness at the top before you go."))

    # --- swing path ------------------------------------------------------------
    # Path direction comes from integrated acceleration; skip the cue when the
    # accelerometer clipped, because the direction can't be trusted then.
    if not m.acc_clipped and abs(m.path_angle_deg) > 30:
        # A wrist IMU can't know the target line by itself — an offset this
        # big means the square calibration hasn't been done yet.
        cues.append(Cue(3, "Path not squared yet",
            "The path reference is off by a large constant — hit a few normal "
            "swings, then tap Set square on the path screen to zero it."))
    elif abs(m.path_angle_deg) > 0.1 and not m.acc_clipped:
        if m.path_angle_deg < -4:
            cues.append(Cue(1, "Out-to-in path ({:.0f}°)".format(m.path_angle_deg),
                "Hands are cutting across the ball — classic slice/pull pattern. "
                "Rehearse swinging toward 1 o'clock (right of target) through impact."))
        elif m.path_angle_deg > 6:
            cues.append(Cue(2, "Strongly in-to-out path (+{:.0f}°)".format(m.path_angle_deg),
                "Big in-to-out move — good for a draw, but this much can produce "
                "pushes and hooks. Feel the chest rotating through impact."))
        else:
            cues.append(Cue(3, "Path is neutral ({:+.0f}°)".format(m.path_angle_deg),
                "Hand path through impact is close to the target line."))

    # --- backswing length --------------------------------------------------------
    if m.backswing_rotation_deg > 0:
        if m.backswing_rotation_deg < 140:
            cues.append(Cue(2, "Short backswing",
                "Limited rotation going back ({:.0f}° of wrist travel). A fuller "
                "turn stores more speed — check hip and shoulder rotation."
                .format(m.backswing_rotation_deg)))
        elif m.backswing_rotation_deg > 320:
            cues.append(Cue(2, "Possible over-swing",
                "Very long backswing ({:.0f}° of wrist travel) can cost control. "
                "Feel 'loaded' at the top rather than stretched."
                .format(m.backswing_rotation_deg)))

    # --- data-quality notes come through as info cues ----------------------------
    for note in m.notes:
        cues.append(Cue(3, "Data note", note))

    cues.sort(key=lambda c: c.priority)
    return cues


def format_summary(m: SwingMetrics, cues: List[Cue], swing_no: int) -> str:
    bar = "─" * 46
    lines = [
        "",
        bar,
        f"  SWING #{swing_no}",
        bar,
        f"  Tempo            {m.tempo_ratio:.1f} : 1   "
        f"(back {m.backswing_s:.2f}s / down {m.downswing_s:.2f}s)",
        f"  Hand speed       {m.hand_speed_mph:5.1f} mph  ({m.hand_speed_mps:.1f} m/s)",
        f"  Est. club speed  {m.club_speed_est_mph:5.1f} mph  (estimate)",
        f"  Peak wrist rot.  {m.peak_gyro_dps:5.0f} deg/s"
        + ("  ⚠ clipped" if m.gyro_clipped else ""),
        f"  Backswing turn   {m.backswing_rotation_deg:5.0f}° of wrist travel",
        f"  Transition       {m.pause_top_s:.2f}s pause · builds at {m.transition_build_dps2:,.0f} °/s²",
        f"  Forearm rot.     {m.forearm_rotation_deg:+5.0f}° top→impact  ({m.forearm_rate_impact_dps:+.0f} °/s at impact)",
        f"  Swing plane      {m.swing_plane_tilt_deg:5.1f}° from horizontal",
        f"  Path             {m.path_angle_deg:+5.1f}°  "
        + ("(in-to-out)" if m.path_angle_deg > 1 else
           "(out-to-in)" if m.path_angle_deg < -1 else "(neutral)"),
        f"  Attack angle     {m.attack_angle_deg:+5.1f}°",
        bar,
    ]
    for c in cues:
        marker = {1: "▶▶", 2: "▶", 3: "·"}[c.priority]
        lines.append(f"  {marker} {c.title}")
        lines.append(f"     {c.detail}")
    lines.append(bar)
    return "\n".join(lines)
