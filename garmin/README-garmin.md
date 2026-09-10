# Garmin sensor tier — Phase 0 pilot logger

Goal: find out what a **vivoactive 4** actually delivers before building any
live integration. The logger answers three questions in one range session:

1. What sample rate does CIQ accept on this device (100 / 50 / 25 Hz)?
2. Is the **gyroscope** exposed to CIQ apps on this model at all?
3. Do the sensors **saturate** on a real swing (accel range, gyro range)?

The app shows the answer to 1–2 on its face the moment it launches.
Question 3 comes from the uploaded data.

## One-time setup

1. **Garmin developer account** (free): developer.garmin.com → sign in with
   your Garmin account → download the **Connect IQ SDK Manager**. In the SDK
   manager, install the latest SDK and the **vivoactive 4** device files.
2. **VS Code** + the "Monkey C" extension (Garmin's official one). Point it
   at the SDK when prompted, and let it generate a **developer key**
   (`Monkey C: Generate a Developer Key`).
3. **Supabase table**: run `supabase/migration-garmin-pilot.sql` in the SQL
   editor (same flow as previous migrations). The watch uploads straight to
   this table — insert-only for the anon key, so nothing can be read back.

## Build & install

1. Open the `garmin/logger` folder in VS Code.
2. `Monkey C: Build for Device` → target **vivoactive4** → produces a `.prg`.
3. Plug the watch in over USB (it mounts as storage) and copy the `.prg`
   into `GARMIN/Apps/`. Eject, and it appears in the watch's activity list.
   (`Monkey C: Build and Run` also works with the simulator, but the
   simulator has no real IMU — device-only for this pilot.)

## Range protocol (mirrors the Toptracer session)

- Wear the Garmin on your **lead wrist** (same wrist as the DOT).
- If you can, wear the DOT too and run a Downrange range session in
  parallel — a paired dataset beats a solo one.
- Launch DR Logger. The face shows e.g. `100 Hz + gyro` or
  `25 Hz, accel only` — **photograph or note this line**; it's the
  headline result.
- Hit up to 6 swings (memory cap — it keeps the most recent 6; the watch
  buzzes when a burst is captured). Press **SELECT** to upload, wait for
  `N uploaded`, then hit the next batch. Phone must be nearby with Garmin
  Connect running (uploads route through it).
- Any club works; a few hard driver swings matter most (they probe
  saturation).

## Analysis

Ask Claude to pull the `garmin_pilot` rows and run them through the
pipeline: units are accel in **milli-g**, gyro in **deg/s**, flat
`[ax,ay,az,gx,gy,gz]` per sample. The verdicts to extract: usable rate,
gyro availability, clip levels vs the DOT's ±16 g / ±2000 °/s, and whether
tempo from the Garmin matches the DOT's on paired swings.

## Known limits / honesty notes

- This project was written outside Garmin's toolchain — expect the first
  build to want one or two trivial fixes (API availability by SDK version,
  resource naming). Send back the exact error text.
- The vivoactive 4 is a 2019 mid-tier device: 25 Hz accel-only is a real
  possibility. That outcome kills the swing-analysis use but still supports
  the **shot-detection tier** (swing happened + timestamp + phone GPS).
- `makeWebRequest` payloads: 6 swings × ~4 s × 100 Hz ≈ 10–25 KB each.
  If uploads fail with large captures (older CIQ builds cap request size),
  reduce MAX_CAP in Recorder.mc to 300 and re-test — even 3 s segments
  carry a full swing.
- Decision gate for Phase 1 (live GarminLink in the iOS app): gyro exposed
  at ≥50 Hz without saturating below ~1500 °/s. Below that, Garmin becomes
  the round-mode shot tracker only.
