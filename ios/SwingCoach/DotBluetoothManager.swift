import CoreBluetooth
import Foundation
import UIKit

/// Native CoreBluetooth client for the Movella DOT, mirroring the web app's
/// Web Bluetooth flow: connect → battery → heading reset → notifications on
/// the medium payload → start Custom Mode 1 (ts + euler + freeAcc + gyro).
/// Parsed samples are batched and injected into the web app's pipeline.
final class DotBluetoothManager: NSObject, ObservableObject {

    // Movella DOT UUIDs (base 1517xxxx-4947-11E9-8646-D663BD873D93)
    private enum DOT {
        static let measurementService = CBUUID(string: "15172000-4947-11E9-8646-D663BD873D93")
        static let controlChar        = CBUUID(string: "15172001-4947-11E9-8646-D663BD873D93")
        static let mediumPayloadChar  = CBUUID(string: "15172003-4947-11E9-8646-D663BD873D93")
        static let orientationReset   = CBUUID(string: "15172006-4947-11E9-8646-D663BD873D93")
        static let batteryService     = CBUUID(string: "15173000-4947-11E9-8646-D663BD873D93")
        static let batteryChar        = CBUUID(string: "15173001-4947-11E9-8646-D663BD873D93")
        static let payloadCustomMode1: UInt8 = 22
    }

    /// Injected by WebContainer: runs JS in the hosted page.
    var evaluator: ((String) -> Void)?

    private var central: CBCentralManager?
    private var peripheral: CBPeripheral?
    private var controlC: CBCharacteristic?
    private var mediumC: CBCharacteristic?
    private var resetC: CBCharacteristic?
    private var batteryC: CBCharacteristic?

    private var wantConnect = false
    private var battery: Int?
    private var lastState = "idle"
    private var lastDetail = ""
    private var discovered: [String: CBPeripheral] = [:]
    private var discoveredMeta: [(id: String, name: String, rssi: Int)] = []
    private var scanTimeout: DispatchWorkItem?

    // Remember the last sensor the user picked so the next launch connects
    // silently (scan → picker → tap was three steps before any value). The
    // page can ask for the chooser explicitly with {cmd:"connect", choose:true}.
    private let lastSensorKey = "sc.lastDotId"
    private var forceChooser = false
    private var rememberedId: String? { UserDefaults.standard.string(forKey: lastSensorKey) }

    // timestamp unwrap: DOT clock is uint32 microseconds
    private var tsFirst: UInt32?
    private var tsLast: UInt32 = 0
    private var tsOffset: Double = 0

    // sample batching (evaluateJavaScript is expensive at 60 Hz). While the
    // app is backgrounded/locked the webview's JS is suspended, so samples
    // BUFFER here (bluetooth-central keeps the stream alive) and replay in
    // chunks when the app returns to the foreground.
    private var sampleBuf: [String] = []
    private var flushTimer: Timer?
    private var appActive = true
    private let bufCap = 300_000        // ~80 min at 60 Hz; oldest dropped past this

    // Stream watchdog: the DOT can silently drop out of measurement mode
    // while the BLE link stays up (seen in the field: LED "connected" but no
    // data, fixed only by power-cycling). Detect the silence and restart the
    // stream ourselves — re-arm notifications + rewrite the start command,
    // and if that fails twice, force a full reconnect cycle.
    private var lastSampleAt: Date?
    private var stallRetries = 0
    private var watchdog: Timer?

    override init() {
        super.init()
        let nc = NotificationCenter.default
        nc.addObserver(forName: UIApplication.didBecomeActiveNotification,
                       object: nil, queue: .main) { [weak self] _ in
            guard let self else { return }
            self.appActive = true
            LocationTrail.shared.flushNow()          // trail first, so replayed
            self.status(self.lastState, self.lastDetail)  // swings can be placed
        }
        nc.addObserver(forName: UIApplication.willResignActiveNotification,
                       object: nil, queue: .main) { [weak self] _ in
            self?.appActive = false
        }
    }

    // MARK: public API (called from the page via the message handler)

    func connect(choose: Bool = false) {
        wantConnect = true
        forceChooser = choose
        tsFirst = nil; tsOffset = 0
        discovered.removeAll()
        discoveredMeta.removeAll()
        pushDeviceList()
        if central == nil {
            central = CBCentralManager(delegate: self, queue: .main)
            status("scanning", "starting Bluetooth…")
        } else {
            startScan()
        }
        if flushTimer == nil {
            flushTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
                self?.flushSamples()
            }
        }
        if watchdog == nil {
            let t = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
                self?.watchdogTick()
            }
            t.tolerance = 1.0
            watchdog = t
        }
    }

    /// Runs every 5 s while connecting is wanted. In round mode the GPS trail
    /// keeps the process alive in the background, so this fires there too.
    private func watchdogTick() {
        guard wantConnect, lastState == "ready",
              let p = peripheral, p.state == .connected,
              let last = lastSampleAt else { return }
        let silence = Date().timeIntervalSince(last)
        guard silence > 5 else { stallRetries = 0; return }
        if stallRetries < 2 {
            stallRetries += 1
            status("connected", "stream stalled — restarting…")
            if let mediumC { p.setNotifyValue(true, for: mediumC) }
            if let controlC {
                p.writeValue(Data([0x01, 0x01, DOT.payloadCustomMode1]),
                             for: controlC, type: .withResponse)
            }
            lastSampleAt = Date()   // give the restart its own 5 s window
        } else {
            stallRetries = 0
            lastSampleAt = nil      // paused until the reconnect streams again
            status("scanning", "stream dead — reconnecting…")
            central?.cancelPeripheralConnection(p)  // didDisconnect auto-reconnects
        }
    }

    /// Connect to a specific sensor the user chose in the picker.
    func pick(id: String) {
        guard let p = discovered[id] else { return }
        UserDefaults.standard.set(id, forKey: lastSensorKey)
        central?.stopScan()
        scanTimeout?.cancel()
        peripheral = p
        p.delegate = self
        status("connected", "connecting to \(p.name ?? "sensor")…")
        central?.connect(p, options: nil)
    }

    /// Forget the remembered sensor (the page's "choose a different sensor").
    func forgetSensor() {
        UserDefaults.standard.removeObject(forKey: lastSensorKey)
    }

    func disconnect() {
        wantConnect = false
        central?.stopScan()
        scanTimeout?.cancel()
        if let p = peripheral { central?.cancelPeripheralConnection(p) }
        peripheral = nil
        status("disconnected", "sensor disconnected")
    }

    private func pushDeviceList() {
        let items = discoveredMeta.map {
            "{\"id\":\(jsString($0.id)),\"name\":\(jsString($0.name)),\"rssi\":\($0.rssi)}"
        }.joined(separator: ",")
        evaluator?("window._nativeDevices && window._nativeDevices([\(items)]);")
    }

    // MARK: page callbacks

    private func status(_ state: String, _ detail: String) {
        lastState = state; lastDetail = detail
        guard appActive else { return }   // re-emitted on didBecomeActive
        let batt = battery.map(String.init) ?? "null"
        let js = "window._nativeStatus && window._nativeStatus(\(jsString(state)), \(jsString(detail)), \(batt));"
        evaluator?(js)
    }

    private func jsString(_ s: String) -> String {
        let escaped = s
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\n", with: " ")
        return "'\(escaped)'"
    }

    private func flushSamples() {
        guard appActive, !sampleBuf.isEmpty else { return }
        // Chunked so a long locked-phone backlog drains smoothly (~40k/s).
        let n = min(sampleBuf.count, 4000)
        let payload = sampleBuf.prefix(n).joined(separator: ",")
        sampleBuf.removeFirst(n)
        evaluator?("window._nativeSamples && window._nativeSamples([\(payload)]);")
    }

    // MARK: BLE flow

    private func startScan() {
        guard let central, central.state == .poweredOn else { return }
        status("scanning", "looking for Movella DOT sensors…")
        // The DOT doesn't reliably advertise its services — scan broadly and
        // filter by name prefix, like the web app does.
        central.scanForPeripherals(withServices: nil, options: nil)
        scanTimeout?.cancel()
        let timeout = DispatchWorkItem { [weak self] in
            guard let self, self.peripheral == nil else { return }
            if self.discoveredMeta.isEmpty {
                self.central?.stopScan()
                self.wantConnect = false
                self.status("error", "No sensor found. Hold the DOT's button until the LED blinks, check it's charged, and make sure it isn't connected to the Movella app or another phone — then tap Connect again.")
            }
        }
        scanTimeout = timeout
        DispatchQueue.main.asyncAfter(deadline: .now() + 12, execute: timeout)
    }

    private func setupComplete() {
        lastSampleAt = Date()   // grace period before the watchdog may fire
        stallRetries = 0
        status("ready", "streaming at 60 Hz")
    }

    private func parseCustomMode1(_ data: Data) {
        guard data.count >= 40 else { return }
        let raw = data.withUnsafeBytes { $0.loadUnaligned(fromByteOffset: 0, as: UInt32.self) }
        if tsFirst == nil { tsFirst = raw; tsLast = raw }
        if raw < tsLast { tsOffset += 4294967296 }
        tsLast = raw
        let t = (Double(raw) + tsOffset - Double(tsFirst!)) / 1_000_000.0

        var f = [Float](repeating: 0, count: 9)
        data.withUnsafeBytes { buf in
            for i in 0..<9 {
                f[i] = buf.loadUnaligned(fromByteOffset: 4 + 4 * i, as: Float.self)
            }
        }
        // Keys must match the web pipeline's Sample fields exactly.
        // "ep" (wall-clock epoch ms) rides along so the page can place swings
        // captured while the phone was locked at the right time and position.
        let json = String(
            format: "{\"t\":%.6f,\"roll\":%.3f,\"pitch\":%.3f,\"yaw\":%.3f,\"ax\":%.4f,\"ay\":%.4f,\"az\":%.4f,\"gx\":%.3f,\"gy\":%.3f,\"gz\":%.3f,\"ep\":%.0f}",
            t, f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8],
            Date().timeIntervalSince1970 * 1000)
        sampleBuf.append(json)
        if sampleBuf.count > bufCap { sampleBuf.removeFirst(sampleBuf.count - bufCap) }
        lastSampleAt = Date()
        if stallRetries > 0 {
            stallRetries = 0
            status("ready", "streaming at 60 Hz")   // recovered without reconnect
        }
    }
}

// MARK: - CBCentralManagerDelegate

extension DotBluetoothManager: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            if wantConnect { startScan() }
        case .unauthorized:
            status("error", "Bluetooth permission denied — enable it in Settings")
        case .poweredOff:
            status("error", "Bluetooth is off — turn it on in Control Centre")
        default:
            break
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? ""
        guard name.hasPrefix("Movella DOT") || name.hasPrefix("Xsens DOT") else { return }
        // Don't auto-connect: collect matches and let the user pick one.
        let id = peripheral.identifier.uuidString
        discovered[id] = peripheral
        // Remembered sensor: skip the picker and connect straight away.
        if !forceChooser, self.peripheral == nil, id == rememberedId {
            status("connected", "reconnecting to your sensor…")
            pick(id: id)
            return
        }
        if let idx = discoveredMeta.firstIndex(where: { $0.id == id }) {
            discoveredMeta[idx].rssi = RSSI.intValue
        } else {
            discoveredMeta.append((id: id, name: name, rssi: RSSI.intValue))
            status("scanning", "found \(discoveredMeta.count) sensor\(discoveredMeta.count == 1 ? "" : "s") — pick one")
        }
        pushDeviceList()
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        status("connected", "setting up…")
        peripheral.discoverServices([DOT.measurementService, DOT.batteryService])
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral,
                        error: Error?) {
        status("error", error?.localizedDescription ?? "connection failed")
        if wantConnect { central.connect(peripheral, options: nil) }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                        error: Error?) {
        guard wantConnect else { return }
        // Walked out of range — CoreBluetooth pending connects resume
        // automatically the moment the sensor is back in range.
        status("scanning", "connection lost — reconnecting…")
        central.connect(peripheral, options: nil)
    }
}

// MARK: - CBPeripheralDelegate

extension DotBluetoothManager: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        for service in peripheral.services ?? [] {
            if service.uuid == DOT.measurementService {
                peripheral.discoverCharacteristics(
                    [DOT.controlChar, DOT.mediumPayloadChar, DOT.orientationReset], for: service)
            } else if service.uuid == DOT.batteryService {
                peripheral.discoverCharacteristics([DOT.batteryChar], for: service)
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral,
                    didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        for c in service.characteristics ?? [] {
            switch c.uuid {
            case DOT.controlChar: controlC = c
            case DOT.mediumPayloadChar: mediumC = c
            case DOT.orientationReset: resetC = c
            case DOT.batteryChar: batteryC = c; peripheral.readValue(for: c)
            default: break
            }
        }
        // Once the measurement service is fully mapped, run the start sequence.
        if let resetC, let mediumC, let controlC, service.uuid == DOT.measurementService {
            status("connected", "calibrating — hold the sensor still for a second")
            tsFirst = nil; tsOffset = 0
            peripheral.writeValue(Data([0x01, 0x00]), for: resetC, type: .withResponse)
            peripheral.setNotifyValue(true, for: mediumC)
            peripheral.writeValue(Data([0x01, 0x01, DOT.payloadCustomMode1]),
                                  for: controlC, type: .withResponse)
        }
    }

    func peripheral(_ peripheral: CBPeripheral,
                    didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if characteristic.uuid == DOT.controlChar, error == nil {
            setupComplete()
        } else if let error, characteristic.uuid == DOT.controlChar {
            status("error", "couldn't start streaming: \(error.localizedDescription)")
        }
    }

    func peripheral(_ peripheral: CBPeripheral,
                    didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, let data = characteristic.value else { return }
        switch characteristic.uuid {
        case DOT.mediumPayloadChar:
            parseCustomMode1(data)
        case DOT.batteryChar:
            if data.count >= 1 {
                battery = Int(data[0])
                status(lastState, lastDetail)   // re-emit so the badge shows battery
            }
        default:
            break
        }
    }
}
