import AVFoundation
import QuartzCore

/// The strike channel.
///
/// The wrist sensor samples at 60 Hz, so it can only say *which sample* the
/// ball-strike shock landed in — ±8 ms, and the hand's velocity direction
/// slews about 11° in one sample. The microphone runs at 48 kHz: 800× finer.
/// Hearing the strike is therefore the cheapest way to pin impact, and the
/// only one that needs no extra hardware.
///
/// What this class reports is an onset time on the phone's *media clock*
/// (`CACurrentMediaTime`), the same clock `DotBluetoothManager` stamps every
/// IMU sample with. It deliberately does NOT try to be absolutely correct:
/// capture latency, the audio HAL's buffering and the speed of sound between
/// the ball and the phone are all fixed offsets for a given setup, and the
/// page removes them with one calibration constant. What the phone must get
/// right is the *jitter*, and that it can do to well under a millisecond.
///
///   native -> page : window._nativeStrike({mt, peak, base, bright, crest})
///                    window._nativeMic(state, detail, levelDb)
final class SwingAudio {
    static let shared = SwingAudio()
    var evaluator: ((String) -> Void)?

    private let engine = AVAudioEngine()
    private(set) var running = false

    // MARK: detector state (touched only on the audio thread)
    private var hpX1: Float = 0, hpY1: Float = 0     // 2× one-pole high-pass,
    private var hpX2: Float = 0, hpY2: Float = 0     // ~1.5 kHz, kills wind/rumble
    private var hpA: Float = 0.836
    private var fastEnv: Float = 0                    // 0.5 ms attack
    private var slowEnv: Float = 1e-6                 // ~150 ms baseline
    private var fastK: Float = 0, slowK: Float = 0
    private var refractoryUntil: Double = 0
    private var meterPeak: Float = 0
    private var lastMeterAt: Double = 0

    /// A strike must stand this far above the running background before it
    /// counts. Range ambience, wind and a neighbour's driver all sit in the
    /// baseline; a struck ball is 20–40 dB above it a metre or two away.
    private let onsetRatio: Float = 12.0     // ~22 dB over baseline
    private let absFloor: Float = 0.004      // ignore near-silence entirely
    /* First field test, 99 swings: the onset fired on the clubhead's rush past
       the phone, not the ball, on 93% of swings — 2 samples (~33 ms) early,
       which at 40 m/s puts the head 1.3 m out. A quarter-second refractory
       then guaranteed the strike that followed was never seen at all. Keep
       only enough to avoid counting one transient twice, and report every
       onset; the page decides which one was the ball. */
    private let refractory: Double = 0.025
    private var scratchRaw = [Float](repeating: 0, count: 4096)
    private var scratchHp  = [Float](repeating: 0, count: 4096)

    // MARK: - control

    func start() {
        guard !running else { return }
        let proceed: (Bool) -> Void = { [weak self] ok in
            DispatchQueue.main.async {
                guard let self else { return }
                guard ok else {
                    self.report("denied", "Microphone access is off for Downrange. Settings \u{203A} Privacy \u{203A} Microphone.")
                    return
                }
                self.begin()
            }
        }
        if #available(iOS 17.0, *) {
            AVAudioApplication.requestRecordPermission(completionHandler: proceed)
        } else {
            AVAudioSession.sharedInstance().requestRecordPermission(proceed)
        }
    }

    func stop() {
        guard running else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        running = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        report("off", "")
    }

    private func begin() {
        let session = AVAudioSession.sharedInstance()
        do {
            // .measurement turns off AGC, EQ and noise suppression. Those are
            // built to flatter speech and they would both smear the transient
            // and add unpredictable latency — exactly the two things that
            // would make this useless.
            try session.setCategory(.record, mode: .measurement, options: [])
            try session.setPreferredIOBufferDuration(0.005)
            try session.setActive(true)
            // Force the built-in mic: a paired Bluetooth headset would add
            // 100 ms+ of codec latency and its own AGC.
            if let builtIn = session.availableInputs?.first(where: { $0.portType == .builtInMic }) {
                try? session.setPreferredInput(builtIn)
            }
        } catch {
            report("error", "Couldn't open the microphone: \(error.localizedDescription)")
            return
        }

        let input = engine.inputNode
        let format = input.inputFormat(forBus: 0)
        let sr = format.sampleRate
        guard sr > 8000 else {
            report("error", "Microphone unavailable.")
            return
        }
        // One-pole high-pass coefficient for ~1.5 kHz at this rate, applied twice.
        hpA = Float(1.0 / (1.0 + 2.0 * Double.pi * 1500.0 / sr))
        fastK = Float(1.0 - exp(-1.0 / (0.0005 * sr)))
        slowK = Float(1.0 - exp(-1.0 / (0.1500 * sr)))

        var timebase = mach_timebase_info_data_t()
        mach_timebase_info(&timebase)
        let tbScale = Double(timebase.numer) / Double(timebase.denom) / 1_000_000_000.0

        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buf, when in
            self?.process(buf, hostSeconds: Double(when.hostTime) * tbScale, sr: sr)
        }

        do {
            engine.prepare()
            try engine.start()
        } catch {
            report("error", "Couldn't start audio: \(error.localizedDescription)")
            return
        }
        running = true
        let lat = session.inputLatency + session.ioBufferDuration
        report("on", String(format: "listening at %.0f kHz · %.1f ms capture latency", sr / 1000, lat * 1000))
    }

    // MARK: - detection

    private func process(_ buf: AVAudioPCMBuffer, hostSeconds: Double, sr: Double) {
        guard let ch = buf.floatChannelData?[0] else { return }
        let n = Int(buf.frameLength)
        if n == 0 { return }
        let dt = 1.0 / sr

        var hitIdx = -1
        var hitPeak: Float = 0
        var baseAt: Float = 0
        if scratchRaw.count < n { scratchRaw = [Float](repeating: 0, count: n) }
        if scratchHp.count  < n { scratchHp  = [Float](repeating: 0, count: n) }

        for i in 0..<n {
            let x = ch[i]
            // cascaded one-pole high-pass
            let y1 = hpA * (hpY1 + x - hpX1); hpX1 = x; hpY1 = y1
            let y2 = hpA * (hpY2 + y1 - hpX2); hpX2 = y1; hpY2 = y2
            let a = abs(y2)

            // Kept per sample so the features below can describe the TRANSIENT.
            // They used to be summed over the whole 21 ms block, which meant
            // "brightness" described the block's ambient character rather than
            // the thing that triggered — and that is why gating on it made the
            // field-test scatter worse instead of better.
            scratchRaw[i] = x
            scratchHp[i] = y2

            fastEnv += (a - fastEnv) * fastK
            if fastEnv > meterPeak { meterPeak = fastEnv }

            if hitIdx < 0 && fastEnv > absFloor && fastEnv > onsetRatio * slowEnv {
                hitIdx = i
                baseAt = slowEnv
            }
            // The baseline must not chase the transient it is supposed to
            // stand out from, so it only tracks while nothing is happening.
            if hitIdx < 0 || i > hitIdx + Int(0.05 * sr) {
                slowEnv += (a - slowEnv) * slowK
                if slowEnv < 1e-7 { slowEnv = 1e-7 }
            }
            if hitIdx >= 0 && a > hitPeak { hitPeak = a }
        }

        let bufStart = hostSeconds
        let now = CACurrentMediaTime()

        // 5 Hz level meter so the range screen can show the mic is alive and
        // the user can judge placement before hitting anything.
        if now - lastMeterAt > 0.2 {
            lastMeterAt = now
            let db = 20 * log10(max(meterPeak, 1e-6))
            meterPeak = 0
            let js = String(format: "window._nativeMic && window._nativeMic('level','',%.1f);", db)
            DispatchQueue.main.async { [weak self] in self?.evaluator?(js) }
        }

        guard hitIdx >= 0 else { return }
        let onsetAbs = bufStart + Double(hitIdx) * dt
        guard onsetAbs > refractoryUntil else { return }
        refractoryUntil = onsetAbs + refractory

        // Walk back to where the transient actually began. The envelope
        // detector fires a little late by construction (it needs the level to
        // rise), and a ball-strike's leading edge is only a few hundred
        // microseconds wide — worth recovering, since the whole point of this
        // channel is the leading edge.
        var i = hitIdx
        let onsetFloor = max(hitPeak * 0.08, baseAt * 2)
        let backLimit = max(0, hitIdx - Int(0.003 * sr))
        while i > backLimit && abs(ch[i]) > onsetFloor { i -= 1 }
        let refinedAbs = bufStart + Double(i) * dt

        // Brightness over the 3 ms following the onset, not the block.
        var tRaw: Float = 0, tHp: Float = 0
        let fEnd = min(n, hitIdx + Int(0.003 * sr))
        var bright: Float = -1
        if fEnd - hitIdx > 8 {
            for k in hitIdx..<fEnd { tRaw += scratchRaw[k] * scratchRaw[k]; tHp += scratchHp[k] * scratchHp[k] }
            if tRaw > 0 { bright = sqrt(tHp / tRaw) }
        }
        // Crest: the peak against the 20 ms of background before it. A struck
        // ball rises in well under a millisecond and towers over that; a
        // clubhead swishing past swells over tens of milliseconds and does
        // not. This is the feature that separates them — brightness alone
        // demonstrably does not.
        var crest: Float = -1
        let bgFrom = max(0, hitIdx - Int(0.020 * sr))
        if hitIdx > bgFrom {
            var bg: Float = 0
            for k in bgFrom..<hitIdx { bg += scratchHp[k] * scratchHp[k] }
            bg = (bg / Float(hitIdx - bgFrom)).squareRoot()
            if bg > 0 { crest = hitPeak / bg }
        }
        let peakDb = 20 * log10(max(hitPeak, 1e-6))
        let baseDb = 20 * log10(max(baseAt, 1e-6))

        let js = String(
            format: "window._nativeStrike && window._nativeStrike({mt:%.6f,peak:%.1f,base:%.1f,bright:%.3f,crest:%.1f});",
            refinedAbs, peakDb, baseDb, bright, crest)
        DispatchQueue.main.async { [weak self] in self?.evaluator?(js) }
    }

    // MARK: - plumbing

    private func report(_ state: String, _ detail: String) {
        let d = detail
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\n", with: " ")
        let js = "window._nativeMic && window._nativeMic('\(state)','\(d)',null);"
        DispatchQueue.main.async { [weak self] in self?.evaluator?(js) }
    }
}
