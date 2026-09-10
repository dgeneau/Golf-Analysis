#!/usr/bin/env python3
"""Characterize Garmin pilot swings exported from the garmin_pilot table.

Phase-0 questions this answers:
  1. Does the flat payload reshape cleanly (cols=6: ax,ay,az,gx,gy,gz)?
  2. Are the units sane (accel ~1000 mG at rest; gyro deg/s)?
  3. Does the accelerometer or gyro SATURATE on a swing (flat-topped peak)?
  4. Can 25 Hz gyro resolve a tempo (backswing / downswing)?

Input: CSV or JSON exported from Supabase (columns include rate_hz, cols,
n, payload). payload is a JSON string of a flat number list.
Usage: python3 analyze_pilot.py <export.csv|export.json>
"""
import sys, json, csv, math, statistics as st


def load_rows(path):
    if path.endswith(".json"):
        data = json.load(open(path))
        return data if isinstance(data, list) else [data]
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        if isinstance(r.get("payload"), str):
            r["payload"] = json.loads(r["payload"])
    return rows


def analyze(row):
    rate = int(row.get("rate_hz") or 25)
    cols = int(row.get("cols") or 6)
    flat = row["payload"]
    n = len(flat) // cols
    samp = [flat[i*cols:(i+1)*cols] for i in range(n)]
    ax = [s[0] for s in samp]; ay = [s[1] for s in samp]; az = [s[2] for s in samp]
    gx = [s[3] for s in samp]; gy = [s[4] for s in samp]; gz = [s[5] for s in samp]
    amag = [math.sqrt(x*x+y*y+z*z)/1000.0 for x, y, z in zip(ax, ay, az)]   # g
    gmag = [math.sqrt(x*x+y*y+z*z) for x, y, z in zip(gx, gy, gz)]          # deg/s

    print(f"\n=== swing id={row.get('id')} · {n} samples · {n/rate:.2f}s @ {rate}Hz ===")
    print(f"  accel |a|: rest~{st.median(amag):.2f}g  peak {max(amag):.2f}g")
    print(f"  per-axis mG extent: "
          f"x[{min(ax)},{max(ax)}] y[{min(ay)},{max(ay)}] z[{min(az)},{max(az)}]")
    print(f"  gyro |g|: peak {max(gmag):.0f} deg/s  "
          f"per-axis peak x{max(abs(v) for v in gx)} y{max(abs(v) for v in gy)} z{max(abs(v) for v in gz)}")

    # saturation heuristic: does the per-axis extreme repeat (flat top)?
    for name, arr in [("ax", ax), ("ay", ay), ("az", az), ("gx", gx), ("gy", gy), ("gz", gz)]:
        hi, lo = max(arr), min(arr)
        hits = sum(1 for v in arr if v == hi or v == lo)
        if hits >= 3 and (abs(hi) > 3000 or abs(lo) > 3000):
            print(f"  ! possible clip on {name}: extreme {hi}/{lo} repeats {hits}x")

    # crude tempo from gyro magnitude: peak-search either side of the global min
    if n >= 6 and max(gmag) > 100:
        iPk = gmag.index(max(gmag))                     # ~impact (fastest)
        pre = gmag[:iPk] if iPk > 2 else gmag
        iBack = pre.index(max(pre))                      # backswing peak
        mid = gmag[iBack:iPk+1]
        iTop = iBack + mid.index(min(mid)) if len(mid) > 1 else iBack  # transition
        back_s = (iTop - 0) / rate
        down_s = (iPk - iTop) / rate
        if down_s > 0:
            print(f"  tempo (gyro): back {back_s:.2f}s / down {down_s:.2f}s = "
                  f"{back_s/down_s:.1f}:1  [DOT norm ~2.5-2.8]  "
                  f"(downswing = {iPk-iTop} samples — {'thin' if iPk-iTop < 5 else 'ok'} at {rate}Hz)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    rows = load_rows(sys.argv[1])
    print(f"loaded {len(rows)} swing(s)")
    for r in rows:
        analyze(r)
