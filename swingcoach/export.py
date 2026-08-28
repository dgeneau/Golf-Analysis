"""Export analyzed swing data as JSON for the SwingCoach dashboard.

Usage:
    python -m swingcoach.export session.csv > dashboard_data.json
    python -m swingcoach.export --simulate > dashboard_data.json
"""
from __future__ import annotations

import dataclasses
import json
import sys
from typing import List, Optional

import numpy as np

from .coach import coach
from .detector import SwingDetector, SwingRecord
from .metrics import compute_metrics
from .protocol import Sample


def _hand_path(rec: SwingRecord) -> dict:
    """Integrate acceleration twice for a rough world-frame hand path.

    Starts at takeaway with v=0 (hands are still at address). Good enough
    for a visual; not used for any coached metric.
    """
    s = rec.samples
    i0, i3 = rec.i_takeaway, min(rec.i_finish, len(s) - 1)
    t = np.array([x.t for x in s[i0:i3 + 1]])
    acc = np.array([[x.ax, x.ay, x.az] for x in s[i0:i3 + 1]])
    vel = np.zeros_like(acc)
    pos = np.zeros_like(acc)
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        vel[i] = vel[i - 1] + acc[i] * dt
        pos[i] = pos[i - 1] + vel[i] * dt
    return {
        "t": [round(float(x), 4) for x in t],
        "x": [round(float(p[0]), 4) for p in pos],   # + toward target
        "y": [round(float(p[1]), 4) for p in pos],   # + left of target
        "z": [round(float(p[2]), 4) for p in pos],   # + up
        "i_top": int(rec.i_top - i0),
        "i_impact": int(rec.i_impact - i0),
    }


def swing_to_dict(rec: SwingRecord, lever_m: float = 1.05) -> dict:
    """Serialize one segmented swing (metrics + cues + trace + path) for the dashboard."""
    m = compute_metrics(rec, lever_m=lever_m)
    cues = coach(m)
    seg = rec.samples[rec.i_takeaway:rec.i_finish + 1]
    t0 = rec.t_takeaway
    return {
        "metrics": dataclasses.asdict(m),
        "cues": [dataclasses.asdict(c) for c in cues],
        "events": {
            "takeaway": 0.0,
            "top": round(rec.t_top - t0, 4),
            "impact": round(rec.t_impact - t0, 4),
            "finish": round(seg[-1].t - t0, 4),
        },
        "trace": {
            "t": [round(x.t - t0, 4) for x in seg],
            "gyro": [round(x.gyro_mag, 1) for x in seg],
            "acc": [round(x.acc_mag, 2) for x in seg],
            "forearm": [round(x.gx, 1) for x in seg],
        },
        "path": _hand_path(rec),
    }


def analyze_stream(samples: List[Sample], lever_m: float = 1.05) -> dict:
    """Run the full pipeline over a sample stream; return the dashboard bundle."""
    det = SwingDetector()
    swings = []
    for s in samples:
        rec = det.feed(s)
        if rec is not None:
            swings.append(swing_to_dict(rec, lever_m))
    return {"swings": swings, "lever_m": lever_m}


def _simulated_session() -> List[Sample]:
    from .simulator import SwingParams, generate_session
    base = dict(backswing_deg=120.0, backswing_s=1.1, downswing_s=0.40)
    return generate_session([
        SwingParams(**base),
        SwingParams(**{**base, "backswing_s": 0.50, "downswing_s": 0.32}),
        SwingParams(**{**base, "path_bias_deg": -9.0}),
        SwingParams(backswing_deg=165.0, backswing_s=0.85, downswing_s=0.27),
        SwingParams(**{**base, "path_bias_deg": 4.0, "downswing_s": 0.38}),
        SwingParams(**{**base, "backswing_s": 1.35, "backswing_deg": 130.0}),
    ])


def _load_csv(path: str) -> List[Sample]:
    import csv
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append(Sample(**{k: float(row[k]) for k in
                                 ("t", "roll", "pitch", "yaw",
                                  "ax", "ay", "az", "gx", "gy", "gz")}))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--simulate":
        samples = _simulated_session()
        source = "simulated"
    elif argv:
        samples = _load_csv(argv[0])
        source = argv[0]
    else:
        print(__doc__, file=sys.stderr)
        return 2
    bundle = analyze_stream(samples)
    bundle["source"] = source
    json.dump(bundle, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
