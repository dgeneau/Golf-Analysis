# SwingCoach iOS (first iteration)

A native Swift shell around the SwingCoach web app: **CoreBluetooth talks to
the Movella DOT natively** (no Web Bluetooth needed on iOS) and feeds parsed
samples into the exact same analysis pipeline the hosted app uses. The UI is
the live GitHub Pages app loaded in a WKWebView — every feature (range mode,
rounds, maps, cloud sync, share cards) works, and web updates ship to the app
with a normal `git push`, no rebuild.

## Run it on your iPhone

1. Open `ios/SwingCoach.xcodeproj` in Xcode (16 or newer).
2. Select the **SwingCoach** target → **Signing & Capabilities** → set
   **Team** to your personal team (your Apple ID; add it in Xcode →
   Settings → Accounts if it isn't there). With a free Apple ID, change the
   bundle identifier to something unique, e.g. `com.<yourname>.swingcoach`.
3. Plug in your iPhone, pick it as the run destination, press **Run**.
4. First launch on-device: iOS blocks apps from unknown developers —
   Settings → General → VPN & Device Management → trust your developer
   certificate, then launch again.
5. In the app: **Connect sensor** → allow Bluetooth → the DOT connects
   natively. Allow Location when Round mode asks.

Free-Apple-ID signing expires after 7 days (re-run from Xcode to refresh);
a paid developer account ($99/yr) removes that and enables TestFlight.

## Architecture

- `SwingCoachApp.swift` / `ContentView.swift` — SwiftUI entry; keeps the
  screen awake during sessions (`isIdleTimerDisabled`).
- `WebContainer.swift` — WKWebView hosting https://dgeneau.github.io/Golf-Analysis/
  with an offline retry page. Bridge: the page posts
  `{cmd: connect|disconnect}` to `webkit.messageHandlers.swingcoach`; native
  code calls `window._nativeStatus(...)` and `window._nativeSamples([...])`.
- `DotBluetoothManager.swift` — CoreBluetooth central mirroring the web BLE
  flow: scan by name prefix → connect → battery read → heading reset
  (`0x2006 ← 01 00`) → notify on medium payload (`0x2003`) → start Custom
  Mode 1 (`0x2001 ← 01 01 16h`). Parses 40-byte packets (uint32 µs timestamp
  unwrapped to seconds + 9 little-endian floats), batches ~6 samples per
  100 ms into one `evaluateJavaScript` call. Auto-reconnects when the sensor
  comes back into range (pending-connect semantics).
- The web side detects the shell via the `swingcoach` message handler and
  routes the Connect button natively (`NATIVE_BLE` in dashboard.html).

## Known v1 limitations (by design, for the first test)

- Foreground only: no background/pocket streaming yet (that's the
  `bluetooth-central` background mode + native buffering step in
  `claude/ios-app-plan.md`). The idle timer is disabled, so the screen stays
  on like a Garmin would.
- Share card uses the Web Share API where WKWebView allows it; the blob
  download fallback does nothing in a webview — a native share bridge is a
  planned follow-up.
- Magic-link email sign-in opens in the webview and persists; if the link
  opens in Safari instead of the app, sign in once via the hosted site inside
  the app's own view (tap Sign in from within the app).

## What Xcode errors to send back

This project was generated outside Xcode. If the first build complains,
copy the exact error text — the usual suspects are trivial (a build setting
or a Swift API availability tweak) and can be fixed in one pass.
