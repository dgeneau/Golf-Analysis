import Foundation
import CoreMotion
import HealthKit
import WatchConnectivity
import WatchKit

/// Captures wrist motion on the watch and ships each detected swing to the
/// iPhone, where it enters the same analysis pipeline the Movella DOT feeds.
///
/// Two capture paths:
/// - Series 8 / Ultra and later (watchOS 10+): CMBatchedSensorManager device
///   motion at 200 Hz — Apple's API built for golf-swing analysis. Requires
///   an active HealthKit workout session.
/// - Older watches: CMMotionManager device motion at 100 Hz (accelerometer
///   clips around ±8 g on fast swings — flagged in the UI).
///
/// Detection here is deliberately crude (gyro burst → quiet → cut segment);
/// the real segmentation/metrics run in the shared pipeline on the phone.
final class WatchMotionManager: NSObject, ObservableObject {
    enum State { case idle, starting, capturing, unsupported, error }

    @Published var state: State = .idle
    @Published var detail = ""
    @Published var swingCount = 0
    @Published var highRate = true

    private let health = HKHealthStore()
    private var workout: HKWorkoutSession?
    private let batched = CMBatchedSensorManager()
    private let classic = CMMotionManager()

    // ring buffer of converted samples (~12 s at 200 Hz)
    private struct S {
        var t, roll, pitch, yaw, ax, ay, az, gx, gy, gz: Double
    }
    private var buf: [S] = []
    private let bufMax = 2400

    // burst segmentation (thresholds mirror the pipeline's detector)
    private let BURST_DPS = 450.0     // gyro magnitude that marks a swing
    private let LOUD_DPS = 200.0      // still "in the swing" above this
    private let QUIET_S = 0.7         // this long below LOUD ends the swing
    private let PRE_S = 3.0           // context before the burst (address!)
    private let MAX_SWING_S = 4.5     // hard cap on one swing's duration
    private var burstT: Double?
    private var lastLoudT = 0.0
    private var cooldownUntil = 0.0
    private var swingId: UInt32 = 0

    override init() {
        super.init()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    // MARK: session control

    func start() {
        guard state != .capturing && state != .starting else { return }
        state = .starting
        detail = "requesting permissions…"
        health.requestAuthorization(toShare: [HKObjectType.workoutType()], read: []) { [weak self] _, _ in
            DispatchQueue.main.async { self?.beginCapture() }
        }
    }

    private func beginCapture() {
        // A workout session keeps the app running with the wrist down and is
        // required for batched (200 Hz) sensor delivery.
        let cfg = HKWorkoutConfiguration()
        cfg.activityType = .golf
        cfg.locationType = .outdoor
        do {
            workout = try HKWorkoutSession(healthStore: health, configuration: cfg)
            workout?.startActivity(with: Date())
        } catch {
            state = .error
            detail = "couldn't start a workout session: \(error.localizedDescription)"
            return
        }
        buf.removeAll(keepingCapacity: true)
        burstT = nil
        if CMBatchedSensorManager.isDeviceMotionSupported {
            highRate = true
            batched.startDeviceMotionUpdates { [weak self] batch, error in
                if let error {
                    DispatchQueue.main.async {
                        self?.state = .error
                        self?.detail = "sensor stream ended: \(error.localizedDescription)"
                    }
                    return
                }
                for dm in batch ?? [] { self?.feed(dm) }
            }
            state = .capturing
            detail = "swing away — each swing is sent to the phone"
        } else if classic.isDeviceMotionAvailable {
            highRate = false
            classic.deviceMotionUpdateInterval = 1.0 / 100.0
            classic.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: .main) { [weak self] dm, _ in
                if let dm { self?.feed(dm) }
            }
            state = .capturing
            detail = "older watch: 100 Hz, accel can clip on fast swings"
        } else {
            state = .unsupported
            detail = "this watch doesn't expose motion data"
            workout?.end()
            workout = nil
            return
        }
        sendEvent("capturing", extra: ["rate": highRate ? 200 : 100])
    }

    func stop() {
        if CMBatchedSensorManager.isDeviceMotionSupported { batched.stopDeviceMotionUpdates() }
        classic.stopDeviceMotionUpdates()
        workout?.end()
        workout = nil
        state = .idle
        detail = ""
        sendEvent("stopped")
    }

    // MARK: sample conversion (device frame → the pipeline's earth frame)

    private func feed(_ dm: CMDeviceMotion) {
        // Rotate user (gravity-removed) acceleration into the reference frame
        // using the attitude quaternion, then convert g → m/s² to match the
        // DOT's free acceleration. If real-world paths ever look dynamically
        // skewed (not just a constant rotation), invert this rotation.
        let q = dm.attitude.quaternion
        let (ax, ay, az) = Self.rotate(q,
                                       dm.userAcceleration.x * 9.80665,
                                       dm.userAcceleration.y * 9.80665,
                                       dm.userAcceleration.z * 9.80665)
        let d = 180.0 / Double.pi
        let s = S(t: dm.timestamp,
                  roll: dm.attitude.roll * d,
                  pitch: dm.attitude.pitch * d,
                  yaw: dm.attitude.yaw * d,
                  ax: ax, ay: ay, az: az,
                  gx: dm.rotationRate.x * d,   // body frame, deg/s — same as DOT
                  gy: dm.rotationRate.y * d,
                  gz: dm.rotationRate.z * d)
        buf.append(s)
        if buf.count > bufMax { buf.removeFirst(buf.count - bufMax) }
        detect(s)
    }

    /// v' = q · v · q⁻¹ (device → reference frame)
    private static func rotate(_ q: CMQuaternion, _ x: Double, _ y: Double, _ z: Double)
        -> (Double, Double, Double) {
        let qw = q.w, qx = q.x, qy = q.y, qz = q.z
        // t = 2 q_vec × v
        let tx = 2 * (qy * z - qz * y)
        let ty = 2 * (qz * x - qx * z)
        let tz = 2 * (qx * y - qy * x)
        // v' = v + w t + q_vec × t
        return (x + qw * tx + (qy * tz - qz * ty),
                y + qw * ty + (qz * tx - qx * tz),
                z + qw * tz + (qx * ty - qy * tx))
    }

    // MARK: crude burst detection → cut and ship a segment

    private func detect(_ s: S) {
        let gmag = (s.gx * s.gx + s.gy * s.gy + s.gz * s.gz).squareRoot()
        if s.t < cooldownUntil { return }
        if burstT == nil {
            if gmag > BURST_DPS { burstT = s.t; lastLoudT = s.t }
            return
        }
        if gmag > LOUD_DPS { lastLoudT = s.t }
        if s.t - lastLoudT > QUIET_S || s.t - burstT! > MAX_SWING_S {
            let from = burstT! - PRE_S
            let seg = buf.filter { $0.t >= from }
            burstT = nil
            cooldownUntil = s.t + 0.5
            ship(seg)
        }
    }

    // MARK: transfer to the phone
    // Binary chunks ≤ ~30 KB (WCSession message limit is 64 KB).
    // Layout, little-endian:
    //   UInt32 magic "SWG1" (0x53574731) · UInt32 swingId ·
    //   UInt16 chunkIdx · UInt16 chunkCount · Float64 t0 ·
    //   UInt32 sampleCount · then per sample 10×Float32:
    //   dt(from t0), roll, pitch, yaw, ax, ay, az, gx, gy, gz

    private func ship(_ seg: [S]) {
        guard seg.count >= 40 else { return }   // noise, not a swing
        swingId &+= 1
        let t0 = seg[0].t
        let perChunk = 700
        let chunks = stride(from: 0, to: seg.count, by: perChunk).map {
            Array(seg[$0..<min($0 + perChunk, seg.count)])
        }
        for (idx, part) in chunks.enumerated() {
            var d = Data(capacity: 24 + part.count * 40)
            d.appendLE(UInt32(0x5357_4731))
            d.appendLE(swingId)
            d.appendLE(UInt16(idx))
            d.appendLE(UInt16(chunks.count))
            d.appendLE(t0.bitPattern)
            d.appendLE(UInt32(part.count))
            for s in part {
                for v in [s.t - t0, s.roll, s.pitch, s.yaw,
                          s.ax, s.ay, s.az, s.gx, s.gy, s.gz] {
                    d.appendLE(Float32(v).bitPattern)
                }
            }
            send(d)
        }
        DispatchQueue.main.async {
            self.swingCount += 1
            WKInterfaceDevice.current().play(.success)
        }
    }

    private func send(_ data: Data) {
        let session = WCSession.default
        guard session.activationState == .activated else { return }
        if session.isReachable {
            session.sendMessageData(data, replyHandler: nil) { _ in
                // reachable send failed — fall back to the background queue
                session.transferUserInfo(["blob": data])
            }
        } else {
            session.transferUserInfo(["blob": data])
        }
    }

    private func sendEvent(_ name: String, extra: [String: Any] = [:]) {
        let session = WCSession.default
        guard session.activationState == .activated else { return }
        var msg: [String: Any] = ["evt": name]
        for (k, v) in extra { msg[k] = v }
        if session.isReachable { session.sendMessage(msg, replyHandler: nil, errorHandler: nil) }
        else { session.transferUserInfo(msg) }
    }
}

// MARK: - WCSessionDelegate (watch side)

extension WatchMotionManager: WCSessionDelegate {
    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {}
}

// MARK: - little-endian append helpers

private extension Data {
    mutating func appendLE(_ v: UInt16) { var x = v.littleEndian; Swift.withUnsafeBytes(of: &x) { append(contentsOf: $0) } }
    mutating func appendLE(_ v: UInt32) { var x = v.littleEndian; Swift.withUnsafeBytes(of: &x) { append(contentsOf: $0) } }
    mutating func appendLE(_ v: UInt64) { var x = v.littleEndian; Swift.withUnsafeBytes(of: &x) { append(contentsOf: $0) } }
}
