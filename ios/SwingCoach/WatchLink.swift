import Foundation
import WatchConnectivity

/// Receives swing segments from the SwingCoach watch app and injects them
/// into the web pipeline through the same entry points the DOT uses
/// (window._nativeSamples / window._nativeStatus). Binary layout is defined
/// in WatchMotionManager.ship(_:) — keep the two in lockstep.
final class WatchLink: NSObject {
    static let shared = WatchLink()

    /// Injected by WebContainer: runs JS in the hosted page.
    var evaluator: ((String) -> Void)?

    private var chunks: [UInt32: [Int: [String]]] = [:]   // swingId → idx → sample JSON
    private var counts: [UInt32: Int] = [:]

    func start() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    // MARK: decode + inject

    private func handle(_ data: Data) {
        guard data.count >= 24 else { return }
        var off = 0
        func u16() -> UInt16 { defer { off += 2 }; return data.readLE(off) }
        func u32() -> UInt32 { defer { off += 4 }; return data.readLE(off) }
        func f64() -> Double { defer { off += 8 }; return Double(bitPattern: data.readLE(off)) }
        func f32() -> Double { defer { off += 4 }; return Double(Float32(bitPattern: data.readLE(off))) }
        guard u32() == 0x5357_4731 else { return }        // "SWG1"
        let id = u32()
        let idx = Int(u16()), total = Int(u16())
        let t0 = f64()
        let n = Int(u32())
        guard data.count >= 24 + n * 40, total > 0, idx < total else { return }
        var out: [String] = []
        out.reserveCapacity(n)
        for _ in 0..<n {
            let dt = f32(), roll = f32(), pitch = f32(), yaw = f32()
            let ax = f32(), ay = f32(), az = f32()
            let gx = f32(), gy = f32(), gz = f32()
            out.append(String(
                format: "{\"t\":%.6f,\"roll\":%.3f,\"pitch\":%.3f,\"yaw\":%.3f,\"ax\":%.4f,\"ay\":%.4f,\"az\":%.4f,\"gx\":%.3f,\"gy\":%.3f,\"gz\":%.3f}",
                t0 + dt, roll, pitch, yaw, ax, ay, az, gx, gy, gz))
        }
        DispatchQueue.main.async { [self] in
            chunks[id, default: [:]][idx] = out
            counts[id] = total
            guard chunks[id]?.count == total else { return }
            let all = (0..<total).compactMap { chunks[id]?[$0] }.flatMap { $0 }
            chunks[id] = nil
            counts[id] = nil
            inject(all)
        }
    }

    private func inject(_ samples: [String]) {
        guard let evaluator, !samples.isEmpty else { return }
        evaluator("window._nativeStatus && window._nativeStatus('ready','Apple Watch — swing received',null);")
        // feed in slices so no single evaluateJavaScript call gets huge
        var i = 0
        while i < samples.count {
            let part = samples[i..<min(i + 300, samples.count)]
            evaluator("window._nativeSamples && window._nativeSamples([\(part.joined(separator: ","))]);")
            i += 300
        }
    }

    private func handleEvent(_ msg: [String: Any]) {
        guard let evt = msg["evt"] as? String else { return }
        DispatchQueue.main.async { [self] in
            switch evt {
            case "capturing":
                let rate = (msg["rate"] as? Int) ?? 200
                evaluator?("window._nativeStatus && window._nativeStatus('ready','Apple Watch capturing at \(rate) Hz — swing away',null);")
            case "stopped":
                evaluator?("window._nativeStatus && window._nativeStatus('disconnected','watch session ended',null);")
            default: break
            }
        }
    }
}

// MARK: - WCSessionDelegate (phone side)

extension WatchLink: WCSessionDelegate {
    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {}
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }

    func session(_ session: WCSession, didReceiveMessageData messageData: Data) {
        handle(messageData)
    }
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if let blob = userInfo["blob"] as? Data { handle(blob) }
        else { handleEvent(userInfo) }
    }
    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        handleEvent(message)
    }
}

private extension Data {
    func readLE<T: FixedWidthInteger>(_ offset: Int) -> T {
        var v: T = 0
        _ = Swift.withUnsafeMutableBytes(of: &v) { dst in
            copyBytes(to: dst, from: offset..<(offset + MemoryLayout<T>.size))
        }
        return T(littleEndian: v)
    }
}
