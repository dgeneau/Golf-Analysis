"""Synthetic golf-swing generator for end-to-end pipeline testing.

Models the lead wrist moving on a circular arc (radius ~ arm length) in a
tilted swing plane, with a smooth backswing, a pause at the top, an
accelerating downswing to impact, and a decaying follow-through. Output is
the same Sample stream the BLE client produces, so the whole
detector -> metrics -> coach pipeline can be exercised without hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import List

import numpy as np

from .protocol import Sample


@dataclass
class SwingParams:
    backswing_s: float = 0.80
    downswing_s: float = 0.27
    hand_speed_mps: float = 9.0      # wrist speed at impact
    plane_tilt_deg: float = 55.0     # from horizontal
    path_bias_deg: float = 0.0       # + = in-to-out
    backswing_deg: float = 165.0     # arc swept going back
    arm_radius_m: float = 0.75
    noise_acc: float = 0.15          # m/s^2
    noise_gyro: float = 2.0          # deg/s


def _theta_profile(params: SwingParams, rate: float):
    """Arc angle vs time: quiet -> backswing -> top pause -> downswing -> finish."""
    dt = 1.0 / rate
    quiet0, pause, follow, quiet1 = 1.5, 0.08, 0.55, 1.2
    th_top = -math.radians(params.backswing_deg)
    th_impact = math.radians(8.0)

    # downswing sweep sets the impact speed: v = omega * R
    omega_impact = params.hand_speed_mps / params.arm_radius_m  # rad/s

    ts, th = [], []
    t = 0.0

    def emit(theta):
        nonlocal t
        ts.append(t)
        th.append(theta)
        t += dt

    while t < quiet0:
        emit(0.0)
    # backswing: smooth half-cosine 0 -> th_top
    n = max(2, int(params.backswing_s * rate))
    for i in range(n):
        u = (i + 1) / n
        emit(th_top * 0.5 * (1 - math.cos(math.pi * u)))
    while t < quiet0 + params.backswing_s + pause:
        emit(th_top)
    # downswing: accelerate so that d(theta)/dt at impact = omega_impact,
    # using theta(t) = th_top + A*(1 - cos(k u))-ish; simplest: quadratic ramp
    n = max(2, int(params.downswing_s * rate))
    sweep = th_impact - th_top
    for i in range(n):
        u = (i + 1) / n
        emit(th_top + sweep * u ** 2)   # omega grows linearly, peaks at impact
    # follow-through: decay from impact velocity
    omega = 2 * sweep / params.downswing_s  # rad/s at impact (d/du of u^2 scaled)
    theta = th_impact
    t_ft = 0.0
    while t_ft < follow:
        omega *= 0.90
        theta += omega * dt
        emit(theta)
        t_ft += dt
    while t_ft < follow + quiet1:
        emit(theta)
        t_ft += dt
    return np.array(ts), np.array(th)


def generate_swing(params: SwingParams = SwingParams(), rate: float = 60.0,
                   t_offset: float = 0.0, seed: int = 0) -> List[Sample]:
    rng = random.Random(seed)
    ts, th = _theta_profile(params, rate)

    tilt = math.radians(params.plane_tilt_deg)
    bias = math.radians(params.path_bias_deg)

    # Plane basis: e1 along target line (X), e2 tilted "up the plane".
    e1 = np.array([1.0, 0.0, 0.0])
    e2 = np.array([0.0, math.cos(tilt), math.sin(tilt)])
    # Path bias: rotate the whole plane about Z by -bias so that a positive
    # bias produces an in-to-out hand path (metrics: path = -atan2(vy, vx)).
    cb, sb = math.cos(-bias), math.sin(-bias)
    rz = np.array([[cb, -sb, 0], [sb, cb, 0], [0, 0, 1.0]])
    e1, e2 = rz @ e1, rz @ e2
    normal = np.cross(e1, e2)

    r = params.arm_radius_m
    # hand position on the arc; theta=0 is the bottom (address/impact zone)
    pos = np.array([r * (math.sin(t_) * e1 - math.cos(t_) * e2) for t_ in th])
    vel = np.gradient(pos, ts, axis=0)
    acc = np.gradient(vel, ts, axis=0)

    omega = np.gradient(th, ts)  # rad/s about the plane normal

    # Ball-strike shock: a brief deceleration spike where the arc crosses the
    # bottom (theta ~ 0) with downswing speed. Real impacts produce exactly
    # this, and the detector uses it to time impact precisely.
    for i in range(1, len(th)):
        if th[i - 1] < 0.0 <= th[i] and omega[i] > 5.0:
            shock_dir = -pos[i] / np.linalg.norm(pos[i])  # up the shaft
            acc[i] += shock_dir * 90.0
            if i + 1 < len(th):
                acc[i + 1] -= shock_dir * 40.0
            break

    # Mimic the real sensor: measurements clip at the hardware ranges.
    acc = np.clip(acc, -156.9, 156.9)      # +/-16 g

    samples: List[Sample] = []
    for i in range(len(ts)):
        # forearm roll (about sensor x): supinate going back, pronate through —
        # modeled as a fraction of the arc rate so it scales with the swing.
        w_dps = np.rad2deg(omega[i])
        g = np.clip(w_dps * normal + np.array([0.5 * w_dps, 0.0, 0.0]),
                    -2000.0, 2000.0)
        samples.append(Sample(
            t=t_offset + ts[i],
            roll=math.degrees(th[i]) * 0.3,
            pitch=params.plane_tilt_deg - 90.0,
            yaw=math.degrees(th[i]),
            ax=acc[i, 0] + rng.gauss(0, params.noise_acc),
            ay=acc[i, 1] + rng.gauss(0, params.noise_acc),
            az=acc[i, 2] + rng.gauss(0, params.noise_acc),
            gx=g[0] + rng.gauss(0, params.noise_gyro),
            gy=g[1] + rng.gauss(0, params.noise_gyro),
            gz=g[2] + rng.gauss(0, params.noise_gyro),
        ))
    return samples


def generate_session(swings: List[SwingParams], rate: float = 60.0) -> List[Sample]:
    """Several swings back-to-back, as one continuous stream."""
    out: List[Sample] = []
    t0 = 0.0
    for k, sp in enumerate(swings):
        chunk = generate_swing(sp, rate=rate, t_offset=t0, seed=k)
        out.extend(chunk)
        t0 = chunk[-1].t + 1.0 / rate
    return out
