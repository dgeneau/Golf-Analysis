# SwingCoach — Movella DOT golf swing analysis

Live golf-swing coaching from a single wrist-mounted Movella DOT IMU.
Connects over Bluetooth (no official SDK needed — talks the documented BLE
protocol directly via `bleak`, so it works on macOS), detects each swing,
and prints a post-swing summary with metrics and coaching cues.

## Setup (macOS)

```bash
cd golf-swing-coach
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

First run will trigger a macOS Bluetooth permission prompt for your terminal
app — allow it (System Settings → Privacy & Security → Bluetooth).

## Quick start

1. Charge the DOT and turn it on (LED blinking). Make sure the Movella DOT
   app is NOT connected to it — the sensor accepts one connection at a time.
2. Strap the sensor to the **lead wrist** (top of the wrist, like a watch
   face; lead = left wrist for a right-handed golfer).
3. Run:

   ```bash
   python -m swingcoach live
   ```

4. At address, hold still with your forearm aimed **down the target line**
   for a second — heading is zeroed on connect, which is what makes the
   swing-path direction meaningful.
5. Swing. After each swing you get a summary: tempo, hand speed, estimated
   club speed, backswing turn, swing plane, path, attack angle, and
   prioritized coaching cues.
6. Ctrl+C to finish. Raw data is saved to `sessions/session_<timestamp>.csv`.

## Sharing with colleagues — the hosted web app

`docs/index.html` is a standalone build of the dashboard that talks to the
Movella DOT **directly from the browser** via Web Bluetooth — no Python, no
install. Host it with GitHub Pages from this repo:

1. Push the repo to GitHub (the `docs/` folder is already built).
2. Repo **Settings → Pages → Deploy from a branch → `main` / `docs/` → Save**.
3. Share the URL (`https://<user>.github.io/<repo>/`). Colleagues open it,
   click **Connect sensor**, pick their DOT, and swing.

Browser support (a Web Bluetooth limitation, not ours): **Chrome or Edge** on
Windows / macOS / Linux / Android. **Safari and all iPhone/iPad browsers do
not work** — Apple doesn't ship Web Bluetooth. The page says so politely when
opened in an unsupported browser. Sessions can be saved with **Download
session CSV** and re-analyzed later with `swingcoach replay`.

After changing `swingcoach/dashboard.html`, rebuild the hosted page with
`python scripts/build_web.py` and commit `docs/index.html`. The analysis
pipeline exists twice (Python package, JS in the dashboard) and is kept
numerically identical — verified to ~1e-13 on simulated swings.

## Accounts & history (optional cloud)

With a free Supabase project configured (see **SETUP-CLOUD.md**), the hosted
app gains email sign-in, automatic offline-first sync of every swing and
round, and a **Progress** tab with per-session tempo and club-speed trends.
Each golfer sees only their own data (Postgres row-level security). Without
configuration these features stay hidden and the app works as before.

## Round mode (on-course, hosted app)

On the hosted page (Chrome/Edge — an Android tablet is ideal, since it has
GPS), switch the **Range | Round** toggle and start a round. Full swings are
detected from the sensor and stamped with GPS, club, and swing metrics; shot
distance is measured to where the next shot was hit from. Putts and short
chips don't auto-detect — use **+ Putt**. Includes hole/score tracking, undo,
per-club real distances, auto-reconnect when you walk back into Bluetooth
range (~20 m), a screen wake lock, resume-after-reload (the round is saved in
the browser), and round JSON/CSV export.

**Course map:** satellite view (Esri imagery) with your live position, this
hole's shot trail, and mapped greens/hole lines from OpenStreetMap — press
**Load course data** once while you have internet (at home works) and it's
cached for offline use on the course. Tap anywhere on the map to set a
target: you get the distance to it, the remaining carry to the green,
front/middle/back distances when you target the green itself, and club
suggestions drawn from your own measured shot distances (cloud history +
this round). OSM green coverage varies by course; without it, tap-to-target
distances still work.

When the course has `golf=hole` lines mapped on OSM (a line per hole,
tee→green, tagged `ref=<hole number>` and optionally `par=`), rounds become
fully guided: the header shows hole par and length, the map frames each hole,
the correct green drives the to-green readout, the scorecard tracks vs par —
and walking onto the next tee auto-advances the app to that hole.

## Live dashboard

Add `--web` to any command and a dashboard opens at http://localhost:8787,
updating the moment each swing finishes (stat tiles, tempo/speed trends,
per-swing traces, hand path, coaching cues):

```bash
python -m swingcoach live --web            # the real thing: sensor + live board
python -m swingcoach simulate --web        # demo the live board, no hardware
python -m swingcoach replay sess.csv --web # review a recorded session as a board
```

`--port N` changes the port; `--no-browser` skips auto-opening a tab. The
server is local-only (binds 127.0.0.1) and needs no extra dependencies.

## Other commands

```bash
python -m swingcoach simulate              # test the pipeline, no hardware
python -m swingcoach replay sessions/session_XXXX.csv   # re-analyze a session
python -m swingcoach live --lever 0.95     # shorter club (7-iron ~0.95 m)
python -m swingcoach live --address <UUID> # connect to a specific sensor
python -m swingcoach.export sess.csv       # dashboard JSON to stdout
```

## What the metrics mean (and their honest limits)

| Metric | Method | Reliability |
|---|---|---|
| Tempo ratio | backswing time / downswing time (ideal ~3:1) | High |
| Backswing turn | integrated wrist rotation, takeaway→top | High |
| Swing plane tilt | SVD plane fit to downswing hand velocity | Good |
| Hand speed | earth-frame free-acceleration integral, top→impact | Good unless sensor clips |
| Club speed | hand speed + wrist angular velocity × lever arm | Estimate — calibrate per club |
| Path / attack angle | hand velocity direction at impact vs target line | ±6–10° at 60 Hz; unreliable when accelerometer clips |
| Release timing | when peak wrist speed occurs in the downswing | Good |
| Pause at top / transition build | quiet time at the top; rotational ramp rate out of it | High (pure timing) |
| Forearm rotation | integrated roll about the forearm axis, top→impact | Good — interpret relative to your own baseline; strap the sensor the same way every session |
| Repeatability / similarity | DTW similarity of speed-normalized rotation traces + session SDs (dashboard) | High — sensor compared only to itself |

Fast swings can saturate the DOT's ±16 g accelerometer and ±2000°/s gyro near
impact. Clipped swings are flagged in the summary and path cues are
suppressed rather than reported wrongly.

## Architecture

```
swingcoach/
  protocol.py    BLE UUIDs + payload parsing (verified against Movella's
                 own xsens_dot_server reference implementation)
  dot_client.py  async BLE client (bleak) — scan, connect, stream, heading reset
  detector.py    swing segmentation (retrospective: burst → quiet → segment)
  metrics.py     tempo, speeds, plane, path, release (numpy)
  coach.py       rule-based coaching cues + summary formatting
  simulator.py   synthetic swing generator for hardware-free testing
  export.py      dashboard JSON serialization (per swing / whole session)
  webapp.py      local live dashboard server (HTTP + Server-Sent Events)
  dashboard.html the dashboard page (shared by --web and static exports)
  app.py         CLI: live / simulate / replay, each with optional --web
```

The analysis pipeline consumes a generic `Sample` stream, so live BLE,
recorded CSVs, and simulated swings all run through identical code.

## Roadmap ideas

- 120 Hz onboard recording + post-hoc download for sharper impact timing
- Per-player calibration against a launch monitor (club speed regression)
- Session trends: consistency scores, dispersion of tempo/plane across swings
- Second DOT on the glove/hand or club shaft for true clubface data
- Simple GUI / web dashboard for range use
