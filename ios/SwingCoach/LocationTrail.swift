import Foundation
import CoreLocation
import UIKit

/// Records a timestamped GPS trail natively — including while the phone is
/// locked (requires the `location` background mode) — and feeds it to the
/// page as `window._nativeTrail([{ep,lat,lon,acc},…])`. The page uses it to
/// place swings captured while the phone was asleep at the position where
/// they actually happened.
final class LocationTrail: NSObject, CLLocationManagerDelegate {
    static let shared = LocationTrail()

    var evaluator: ((String) -> Void)?

    private let mgr = CLLocationManager()
    private var pending: [(ep: Double, lat: Double, lon: Double, acc: Double)] = []
    private var flushTimer: Timer?
    private var running = false

    func start() {
        guard !running else { return }
        running = true
        mgr.delegate = self
        mgr.desiredAccuracy = kCLLocationAccuracyBest
        mgr.distanceFilter = 8
        mgr.activityType = .fitness
        mgr.pausesLocationUpdatesAutomatically = false
        mgr.requestWhenInUseAuthorization()
        applyBackgroundUpdates()
        mgr.startUpdatingLocation()
        if flushTimer == nil {
            flushTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
                self?.flushNow()
            }
        }
    }

    func stop() {
        running = false
        mgr.stopUpdatingLocation()
        flushTimer?.invalidate()
        flushTimer = nil
        flushNow()
    }

    private func applyBackgroundUpdates() {
        // Only legal once authorized and with the location background mode.
        let st = mgr.authorizationStatus
        if st == .authorizedWhenInUse || st == .authorizedAlways {
            mgr.allowsBackgroundLocationUpdates = true
            mgr.showsBackgroundLocationIndicator = true
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        applyBackgroundUpdates()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        for l in locations where l.horizontalAccuracy >= 0 {
            pending.append((ep: l.timestamp.timeIntervalSince1970 * 1000,
                            lat: l.coordinate.latitude,
                            lon: l.coordinate.longitude,
                            acc: l.horizontalAccuracy))
        }
        if pending.count > 4000 { pending.removeFirst(pending.count - 4000) }
    }

    /// Push everything pending into the page. Called on a timer while active,
    /// and directly (before sample replay) when the app returns to foreground.
    func flushNow() {
        // A suspended webview can't run JS — hold the trail until foreground.
        guard UIApplication.shared.applicationState == .active else { return }
        guard let evaluator, !pending.isEmpty else { return }
        let items = pending.map {
            String(format: "{\"ep\":%.0f,\"lat\":%.7f,\"lon\":%.7f,\"acc\":%.1f}",
                   $0.ep, $0.lat, $0.lon, $0.acc)
        }.joined(separator: ",")
        pending.removeAll(keepingCapacity: true)
        evaluator("window._nativeTrail && window._nativeTrail([\(items)]);")
    }
}
