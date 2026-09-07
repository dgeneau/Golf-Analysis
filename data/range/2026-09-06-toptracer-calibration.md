# Toptracer calibration session — Cordova Bay range, Sep 6 2026

First ground-truth comparison for the SwingCoach club-speed estimate.
Source: `swingcoach-session-2026-09-06-23-16-05.csv` (22 swings, 7.3 min,
no clipping) + 4 photos of the bay-20 Toptracer Range screen.

## Monitor data (Toptracer Range, ball compensation ON)

Toptracer is photometric: it tracks the **ball**, so ball speed and carry are
its trustworthy columns. It does not report club head speed — club speed
below is *derived* as ball speed ÷ smash factor (assumed 7i 1.33, 5w 1.42,
driver 1.45, ±0.05).

| Club  | Avg carry | Avg total | Avg ball | Good-strike ball | Derived club speed (good / avg) |
|-------|-----------|-----------|----------|------------------|--------------------------------|
| 7 iron| 120 yd    | 142 yd    | 99 mph   | ~110 mph         | 82 / 74 mph                    |
| 5 wood| 124 yd    | 169 yd    | 122 mph  | ~130 mph         | 92 / 86 mph                    |
| Driver| 170 yd    | 210 yd    | 138 mph  | ~143 mph         | 99 / 95 mph                    |

Good-strike carries: 7i 145–153, 5w 170–177 (192–195 total), driver 191–200
(225–233 total). Consistency (Toptracer): 7i 22%, 5w 0% (one topped ball,
17 yd), driver 38%.

## SwingCoach side

22 swings grouped by inter-swing gaps (>25 s = club change); ordering
7i → 5w → driver matches both the group speed trend and the photo sequence.
Assignment is inferred, not logged — the range CSV has no club column.

| Club  | n  | Displayed est (per-club lever) | Hand speed | Tempo med |
|-------|----|-------------------------------|------------|-----------|
| 7 iron| 11 | 58.5 mph                      | ~14 mph    | 2.7       |
| 5 wood| 7  | 69.0 mph                      | ~14 mph    | 2.8       |
| Driver| 4  | 76.8 mph                      | ~15 mph    | 2.8       |

Hand speed being flat across clubs while ball data separates cleanly is
physically expected — club speed differences come mostly from the shaft,
not the hands.

## Finding

The estimate `v_hand + ω_wrist × club_length` **underreads by ~1.3–1.5×**,
because the wrist gyro can't see the extra shaft rotation added by wrist
release (uncocking). Fitting an *effective lever* multiplier k on club
length:

| Club  | k (good-strike target) | k (avg target) |
|-------|------------------------|----------------|
| 7 iron| 1.54                   | 1.36           |
| 5 wood| 1.40                   | 1.30           |
| Driver| 1.35                   | 1.30           |

A single **k = 1.35** lands every club inside its plausible band:
7i → 74 mph, 5w → 88 mph, driver → 99 mph.

## Status

Proposed, NOT applied. Displayed speeds keep the "est." label; the
calibration goes in only after Dan approves. Uncertainty: smash factors
assumed; club assignment inferred; one session, one range, one player —
k likely varies with release style, so treat as a personal calibration
constant, not a universal one.
