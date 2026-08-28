"""SwingCoach CLI.

  python -m swingcoach live               # connect to a Movella DOT and coach
  python -m swingcoach simulate           # run the pipeline on synthetic swings
  python -m swingcoach replay data.csv    # re-analyze a recorded session
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import logging
import pathlib
import sys
from typing import List, Optional, TextIO

from .coach import coach, format_summary
from .detector import SwingDetector
from .metrics import compute_metrics
from .protocol import Sample


class Session:
    """Shared engine: feed samples in, get post-swing summaries out."""

    def __init__(self, log_path: Optional[pathlib.Path] = None,
                 lever_m: float = 1.05, web_server=None):
        self.detector = SwingDetector()
        self.swing_no = 0
        self.lever_m = lever_m
        self.web = web_server
        self._log: Optional[TextIO] = None
        if log_path:
            self._log = open(log_path, "w", newline="")
            self._log.write(Sample.CSV_HEADER + "\n")

    def feed(self, s: Sample) -> None:
        if self._log:
            self._log.write(s.to_csv_row() + "\n")
        rec = self.detector.feed(s)
        if rec is None:
            return
        self.swing_no += 1
        m = compute_metrics(rec, lever_m=self.lever_m)
        cues = coach(m)
        print(format_summary(m, cues, self.swing_no), flush=True)
        if self.web is not None:
            from .export import swing_to_dict
            self.web.add_swing(swing_to_dict(rec, self.lever_m))

    def close(self) -> None:
        if self._log:
            self._log.close()


# Standard men's club lengths (inches); used as the wrist-to-clubhead lever.
CLUB_LENGTHS_IN = {
    "driver": 45.5, "3w": 43.0, "5w": 42.0, "hybrid": 40.5,
    "4i": 38.5, "5i": 38.0, "6i": 37.5, "7i": 37.0, "8i": 36.5, "9i": 36.0,
    "pw": 35.75, "sw": 35.25,
}


def default_log_path() -> pathlib.Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    d = pathlib.Path("sessions")
    d.mkdir(exist_ok=True)
    return d / f"session_{stamp}.csv"


# --- subcommands -------------------------------------------------------------

def _maybe_server(args):
    """Start the local live dashboard when --web was passed."""
    if not getattr(args, "web", False):
        return None
    from .webapp import DashboardServer
    server = DashboardServer(port=args.port, lever_m=args.lever)
    server.start(open_browser=not args.no_browser)
    return server


def cmd_live(args) -> int:
    try:
        from .dot_client import stream_forever
    except ImportError:
        print("bleak is not installed. Run: pip install bleak", file=sys.stderr)
        return 1

    log_path = default_log_path() if not args.no_log else None
    server = _maybe_server(args)
    session = Session(log_path, lever_m=args.lever, web_server=server)
    on_status = server.set_status if server is not None else None
    stop = asyncio.Event()

    async def main() -> None:
        print("Hold the sensor still at address, aimed down the target line —")
        print("heading will be zeroed on connect. Ctrl+C to finish.\n")
        try:
            await stream_forever(session.feed, stop, address=args.address,
                                 on_status=on_status)
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession ended.")
    finally:
        session.close()
        if log_path:
            print(f"Raw data saved to {log_path}")
    return 0


def cmd_simulate(args) -> int:
    import time
    from .simulator import SwingParams, generate_session

    base = dict(backswing_deg=120.0, backswing_s=1.1, downswing_s=0.40)
    swings = [
        SwingParams(**base),                                   # solid baseline
        SwingParams(**{**base, "backswing_s": 0.50,
                       "downswing_s": 0.32}),                  # rushed tempo
        SwingParams(**{**base, "path_bias_deg": -9.0}),        # out-to-in cut
        SwingParams(backswing_deg=165.0, backswing_s=0.85,
                    downswing_s=0.27),                         # fast, clips sensor
    ]
    server = _maybe_server(args)
    if server is not None:
        server.set_status("ready", "simulated session — no sensor")
    session = Session(None, lever_m=args.lever, web_server=server)
    prev = session.swing_no
    for s in generate_session(swings):
        session.feed(s)
        if server is not None and session.swing_no != prev:
            prev = session.swing_no
            time.sleep(2.0)   # let the board breathe between swings
    print(f"\nSimulated {len(swings)} swings, detected {session.swing_no}.")
    if server is not None:
        print("Dashboard stays up — Ctrl+C to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0 if session.swing_no == len(swings) else 1


def cmd_replay(args) -> int:
    import time
    server = _maybe_server(args)
    if server is not None:
        server.set_status("ready", f"replaying {args.file} — no sensor")
    session = Session(None, lever_m=args.lever, web_server=server)
    with open(args.file, newline="") as f:
        for row in csv.DictReader(f):
            session.feed(Sample(
                t=float(row["t"]),
                roll=float(row["roll"]), pitch=float(row["pitch"]),
                yaw=float(row["yaw"]),
                ax=float(row["ax"]), ay=float(row["ay"]), az=float(row["az"]),
                gx=float(row["gx"]), gy=float(row["gy"]), gz=float(row["gz"]),
            ))
    print(f"\nReplay complete: {session.swing_no} swing(s) detected.")
    if server is not None:
        print("Dashboard stays up — Ctrl+C to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="swingcoach",
                                 description="Movella DOT golf swing coach")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--lever", type=float, default=1.05,
                    help="wrist-to-clubhead distance in meters (default 1.05)")
    ap.add_argument("--club", choices=sorted(CLUB_LENGTHS_IN),
                    help="club preset for the lever arm (overrides --lever); "
                         "the dashboard also has a club selector")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_web_flags(p):
        p.add_argument("--web", action="store_true",
                       help="serve the live dashboard at http://localhost:PORT")
        p.add_argument("--port", type=int, default=8787)
        p.add_argument("--no-browser", action="store_true",
                       help="don't auto-open the dashboard in a browser")

    p_live = sub.add_parser("live", help="stream from a Movella DOT")
    p_live.add_argument("--address", help="BLE address/UUID of a specific DOT")
    p_live.add_argument("--no-log", action="store_true",
                        help="don't write the session CSV")
    add_web_flags(p_live)
    p_live.set_defaults(fn=cmd_live)

    p_sim = sub.add_parser("simulate", help="run pipeline on synthetic swings")
    add_web_flags(p_sim)
    p_sim.set_defaults(fn=cmd_simulate)

    p_rep = sub.add_parser("replay", help="re-analyze a recorded session CSV")
    p_rep.add_argument("file")
    add_web_flags(p_rep)
    p_rep.set_defaults(fn=cmd_replay)

    args = ap.parse_args(argv)
    if args.club:
        args.lever = CLUB_LENGTHS_IN[args.club] * 0.0254
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
