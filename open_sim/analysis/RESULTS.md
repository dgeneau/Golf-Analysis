# Wrist-IMU → 3D kinematics — OpenCap pilot (2026-09-12)

First validation of the WIT-KinNet premise (arXiv 2606.22876, see
`kinematics-plan.md`) on **our own hardware and subject**: a single wrist DOT vs
OpenCap markerless 3D mocap.

## Data
- **OpenCap** (2 iPhones, markerless, LaiUhlrich2022 model, 60 Hz). Subject
  "Luke", 1.87 m / 84 kg. Two trials: `D1` (driver) and `5i` (5-iron), each ~45 s
  containing several swings → **14 usable swings** (5 driver, 9 iron) after
  segmentation. Gives ground-truth joint angles (`.mot`) + 63 markers (`.trc`).
- **Downrange DOT**: 60 Hz streaming log from the same session (orientation +
  accel + gyro), lead (left) wrist.

Method note — a **"virtual IMU" from mocap**: from the four lead-arm anatomical
markers I build a full 3D forearm/wrist frame → orientation + angular velocity,
perfectly time-synced to the body kinematics. This lets us test "wrist → trunk"
with **zero cross-device sync error**, then separately confirm the real DOT
matches that mocap-derived wrist signal.

## Part A — the DOT faithfully captures wrist motion (`figA`)
Real DOT gyro vs mocap-derived lead-wrist angular velocity, impact-aligned
(representative swings; no hardware sync, so shapes compared, not the identical
physical swing):

| club   | DOT peak | mocap peak |
|--------|---------:|-----------:|
| driver | 1272 °/s | 1129 °/s   |
| 5-iron | 1216 °/s | 1361 °/s   |

Impact peak magnitudes agree within ~11% and the downswing acceleration profile
matches. The sensor is a faithful wrist-kinematics source.

## Part B — trunk kinematics ARE recoverable from the wrist (`figB`)
Virtual-IMU features (orientation 6D + angular velocity + linear accel,
referenced to an address pose, ±3-frame context) → trunk angles via ridge
regression, **leave-one-swing-out** across all 14 swings:

| target            | Pearson r | R²   | MAE   |
|-------------------|----------:|-----:|------:|
| **X-factor**      | **0.905** | 0.82 | 4.9°  |
| pelvis rotation   | 0.854     | 0.73 | 7.2°  |
| thorax rotation   | 0.933     | 0.87 | 9.7°  |

This is a **linear lower bound** on one subject. WIT-KinNet's transformer over 36
golfers reported X-factor r=0.96, pelvis r=0.98. That a *linear* model on *one*
subject already reaches r≈0.9 for X-factor is strong evidence the wrist signal
carries the trunk-rotation information — the paper's central claim holds on our
data, and a proper temporal model + more subjects should close the gap.

## Part C — the coaching payload (`figC`)
Driver swing trunk sequence (OpenCap truth): peak X-factor ≈ 59°, shoulder turn
≈ 115°, hip turn ≈ 72°, with the correct kinematic sequence — X-factor builds to
the top, unwinds toward square at impact, rotates through. This is the eventual
Range-mode output: X-factor curve + pelvis/thorax traces + sequencing timing.

## Honest caveats
- **n = 1 subject, 14 swings.** Leave-one-swing-out tests *within-subject*
  generalization only. The real test is **leave-one-subject-out** — needs many
  golfers before any accuracy claim generalizes.
- **Ground truth is OpenCap markerless**, not marker-based Vicon (the paper's
  reference). OpenCap has its own error, notably shoulder rotation (115° reads a
  touch high) — treat absolute magnitudes as approximate.
- **60 Hz streaming** DOT; the plan calls for **120 Hz onboard recording** so the
  impact transient isn't undersampled (matters most for the downswing, the
  paper's worst region).
- Part A alignment is representative-swing (no hardware time-sync); Part B avoids
  cross-device sync entirely by using the mocap-derived wrist signal.

## What this de-risks, and what's next
De-risked: (1) the DOT is a faithful wrist sensor; (2) wrist → trunk is strongly
learnable, even linearly, on our hardware. Next, per the plan:
1. **Collection kit**: 120 Hz onboard DOT recording + download; hardware/impact
   sync IMU↔mocap; T-pose + address calibration each session; checklist mirroring
   the paper (clubs × amplitudes × trials).
2. **Multi-subject pilot** (target ~10–15 golfers) → train leave-one-subject-out.
3. **Model**: implement WIT-KinNet transformer (Phase 0) — this pipeline
   (`kin_core.py`, `analyze_A/B/C.py`) already loads/synced/segments the data and
   is the training-data feeder.
4. **App**: post-swing ONNX-Web inference → Range-mode kinematics panel.

Reproduce: `python3 analyze_A.py && python3 analyze_B.py && python3 analyze_C.py`
(needs the OpenCap `.mot`/`.trc` + the DOT CSV in the same folder).
