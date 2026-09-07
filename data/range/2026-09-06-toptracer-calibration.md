# Toptracer calibration session — Cordova Bay range, Sep 6 2026

First ground-truth comparison for the SwingCoach club-speed estimate.
Source: `swingcoach-session-2026-09-06-23-16-05.csv` (22 swings, 7.3 min,
no clipping) + 4 photos of the bay-20 Toptracer Range screen.

**Correction (Sep 7):** the club shown as "7 iron" on the monitor was
actually an **8 iron** (Dan grabbed the wrong club). All iron numbers below
use 8-iron length (36.5″) and 8-iron smash factor (~1.31 ± 0.05).

## Monitor data (Toptracer Range, ball compensation ON)

Toptracer is photometric: it tracks the **ball**, so ball speed and carry are
its trustworthy columns. It does not report club head speed — club speed
below is *derived* as ball speed ÷ smash factor (assumed 8i 1.31, 5w 1.42,
driver 1.45, ±0.05).

| Club  | Avg carry | Avg total | Avg ball | Good-strike ball | Derived club speed (good / avg) |
|-------|-----------|-----------|----------|------------------|--------------------------------|
| 8 iron| 120 yd    | 142 yd    | 99 mph   | ~110 mph         | 84 / 76 mph                    |
| 5 wood| 124 yd    | 169 yd    | 122 mph  | ~130 mph         | 92 / 86 mph                    |
| Driver| 170 yd    | 210 yd    | 138 mph  | ~143 mph         | 99 / 95 mph                    |

Good-strike carries: 8i 145–153, 5w 170–177 (192–195 total), driver 191–200
(225–233 total). Consistency (Toptracer): 8i 22%, 5w 0% (one topped ball,
17 yd), driver 38%.

Note on the two targets: mishits lose smash (low ball speed at the same
club speed), so **avg-based targets are biased low** — the good-strike
column is the better anchor for club speed calibration, while the avg
column is the right one for expected on-course carry.

## SwingCoach side

22 swings grouped by inter-swing gaps (>25 s = club change); ordering
8i → 5w → driver matches both the group speed trend and the photo sequence.
Assignment is inferred, not logged — the range CSV has no club column.

| Club  | n  | Displayed est (per-club lever) | Hand speed | Tempo med |
|-------|----|-------------------------------|------------|-----------|
| 8 iron| 11 | 57.9 mph                      | ~14 mph    | 2.7       |
| 5 wood| 7  | 69.0 mph                      | ~14 mph    | 2.8       |
| Driver| 4  | 76.8 mph                      | ~15 mph    | 2.8       |

Hand speed being flat across clubs while ball data separates cleanly is
physically expected — club speed differences come mostly from the shaft,
not the hands.

## Finding

The estimate `v_hand + ω_wrist × club_length` **underreads by ~1.3–1.6×**,
because the wrist gyro can't see the extra shaft rotation added by wrist
release (uncocking). Fitting an *effective lever* multiplier k on club
length:

| Club  | k (good-strike target) | k (avg target) |
|-------|------------------------|----------------|
| 8 iron| 1.60                   | 1.41           |
| 5 wood| 1.40                   | 1.30           |
| Driver| 1.35                   | 1.30           |

A single **k = 1.40** is the best global compromise:
8i → 75, 5w → 91, driver → 102 mph (driver ~3 mph hot vs its good-strike
target, inside smash-factor uncertainty). The iron preferring a larger k
(1.6) is plausible — on a shorter club, wrist release contributes a larger
share of head speed — but with 11/7/4 swings per club and 3 visible monitor
rows each, one session can't settle per-club k values. Revisit when more
paired sessions land.

## Status

Proposed, NOT applied. Displayed speeds keep the "est." label; the
calibration goes in only after Dan approves. Uncertainty: smash factors
assumed; club assignment inferred; one session, one range, one player —
k is a personal calibration constant tied to Dan's release pattern, not a
universal one. A radar-based session (Trackman/FlightScope) would measure
club speed directly and pin this down properly.
