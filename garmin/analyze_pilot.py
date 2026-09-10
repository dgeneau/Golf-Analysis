#!/usr/bin/env python3
"""Characterize Garmin pilot swings exported from the garmin_pilot table.

Handles both payload formats:
  cols=5 (current): flat [t_ms, kind, x, y, z, ...]  kind 0=accel mG, 1=gyro deg/s
  cols=6 (legacy) : flat [ax,ay,az,gx,gy,gz, ...] with accel/gyro in complementary
                    slots (no timestamps)

Phase-0 questions:
  1. Real per-sensor sample rate (from timestamps, cols=5 only).
  2. Accel saturation on a swing (does |a| flat-top at a rail?).
  3. Gyro saturation / peak.
  4. Tempo from the gyro stream (backswing / downswing), and whether the
     sample density resolves the downswing.
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


def split_streams(row):
    """Return (accel, gyro) as lists of (t_ms|None, x, y, z)."""
    cols = int(row.get("cols") or 6)
    flat = row["payload"]
    n = len(flat) // cols
    acc, gyr = [], []
    for i in range(n):
        s = flat[i*cols:(i+1)*cols]
        if cols == 5:
            t, kind, x, y, z = s
            (acc if kind == 0 else gyr).append((t, x, y, z))
        else:  # legacy cols=6, no timestamps
            ax, ay, az, gx, gy, gz = s
            if any((ax, ay, az)) and not any((gx, gy, gz)):
                acc.append((None, ax, ay, az))
            elif any((gx, gy, gz)):
                gyr.append((None, gx, gy, gz))
    return acc, gyr


def rate_of(stream):
    ts = [s[0] for s in stream if s[0] is not None]
    if len(ts) < 3:
        return None
    span = (max(ts) - min(ts)) / 1000.0
    return (len(ts) - 1) / span if span > 0 else None


def analyze(row):
    acc, gyr = split_streams(row)
    print(f"\n=== swing id {row.get('id')} · {int(row.get('n') or 0)} rows ===")
    ra, rg = rate_of(acc), rate_of(gyr)
    print(f"  accel: {len(acc)} samples" + (f" @ {ra:.1f} Hz" if ra else " (no timestamps)"))
    print(f"  gyro : {len(gyr)} samples" + (f" @ {rg:.1f} Hz" if rg else " (no timestamps)"))

    if acc:
        amag = [math.sqrt(x*x+y*y+z*z) for _, x, y, z in acc]
        pk = max(amag)
        railed = sum(1 for v in amag if v > 0.97*pk)
        print(f"  ACCEL |a|: rest~{min(amag):.0f}mG  peak {pk:.0f}mG ({pk/1000:.1f}g)"
              + (f"  ! {railed} samples within 3% of peak — possible clip" if railed >= 3 else ""))

    if gyr:
        gmag = [math.sqrt(x*x+y*y+z*z) for _, x, y, z in gyr]
        pk = max(gmag)
        railed = sum(1 for v in gmag if v > 0.97*pk)
        print(f"  GYRO |g|: peak {pk:.0f} deg/s"
              + (f"  ! {railed} samples within 3% of peak — possible clip" if railed >= 3 else ""))
        _tempo(gmag, rg or 25.0)


def _tempo(gmag, rate):
    if len(gmag) < 6 or max(gmag) < 200:
        print("  tempo: no clear swing (indoor wave / too weak)")
        return
    iPk = gmag.index(max(gmag))                    # impact ~ fastest
    if iPk < 3:
        print("  tempo: swing too near the start to segment")
        return
    pre = gmag[:iPk]
    iBack = pre.index(max(pre))
    mid = gmag[iBack:iPk+1]
    iTop = iBack + (mid.index(min(mid)) if len(mid) > 1 else 0)
    back_s, down_s = (iTop - iBack)/rate, (iPk - iTop)/rate
    dn = iPk - iTop
    if down_s > 0:
        print(f"  tempo (gyro): back {back_s:.2f}s / down {down_s:.2f}s = {back_s/down_s:.1f}:1"
              f"  [DOT norm ~2.5-2.8]  downswing={dn} samples "
              f"({'THIN' if dn < 4 else 'ok'} at {rate:.0f}Hz)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    rows = load_rows(sys.argv[1])
    # de-dup identical payloads (re-presses upload the same buffer)
    seen, uniq = set(), []
    for r in rows:
        k = str(r["payload"])[:200]
        if k not in seen:
            seen.add(k); uniq.append(r)
    print(f"{len(rows)} rows, {len(uniq)} unique swing(s)")
    for r in uniq:
        analyze(r)
