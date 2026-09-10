// Sensor capture: probe the highest accel(+gyro) rate this device accepts,
// keep a rolling pre-buffer, detect swing bursts, store raw segments.
//
// Units per the CIQ SensorData docs: accelerometer in milli-g (mG),
// gyroscope in degrees/second.
//
// MEMORY: the vivoactive 4 (and this device tier generally) has a small
// per-app memory budget. Samples are stored as ONE flat number array per
// swing ([ax,ay,az,gx,gy,gz, ax,ay,az,...]) rather than an array of little
// 6-element arrays — far less object overhead — and the buffer sizes scale
// to the probed rate (2 s pre-roll, 5 s cap) instead of a fixed 100 Hz
// budget. Uploads carry cols=6 so the flat list is reshaped off-watch.
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.System;
import Toybox.WatchUi;

class Recorder {
    // ---- probed capabilities (shown on screen — the point of Phase 0) ----
    public var rateHz as Number = 0;        // accepted sample rate
    public var hasGyro as Boolean = false;  // did the device accept a gyro request?
    public var status as String = "probing sensors...";
    public var err as String? = null;       // last caught exception, shown on the face

    // ---- capture state ----
    public var swings as Array = [];        // stored flat segments (see MEMORY note)
    public var capturing as Boolean = false;

    // rolling pre-buffer + capture buffer, both FLAT (length is a multiple of 6)
    private var _pre as Array<Number> = [];
    private var _cap as Array<Number> = [];
    private var _quietBatches as Number = 0;

    // sizes in *samples*, derived from rateHz once probed (see _sizeBuffers)
    private var _preSamples as Number = 40;
    private var _maxCapSamples as Number = 125;
    private const MAX_SWINGS = 5;           // memory is tight on this tier
    private const COLS = 6;
    // burst thresholds: accel magnitude in mG (|a| incl. gravity ~1000 at rest)
    private const BURST_MG = 2500;          // ~2.5 g — any real swing exceeds this
    private const QUIET_MG = 1600;

    function start() as Void {
        // Try rates high to low, gyro first, then accel-only. Invalid options
        // throw — that behavior IS the capability probe.
        var rates = [100, 50, 25] as Array<Number>;
        for (var g = 0; g < 2; g++) {
            var wantGyro = (g == 0);
            for (var i = 0; i < rates.size(); i++) {
                if (_tryStart(rates[i], wantGyro)) {
                    rateHz = rates[i];
                    hasGyro = wantGyro;
                    _sizeBuffers();
                    status = "" + rateHz + " Hz" + (hasGyro ? " + gyro" : ", accel only");
                    return;
                }
            }
        }
        status = "sensor listener refused";
    }

    // Coerce a possibly-null sample to a Number (0 when missing).
    private function _num(v) as Number {
        return (v == null) ? 0 : (v as Number);
    }

    // 2 s of pre-roll, 5 s cap per swing — plenty for a golf swing, and tiny
    // in memory at this device's rates.
    private function _sizeBuffers() as Void {
        _preSamples = rateHz * 2;
        _maxCapSamples = rateHz * 5;
    }

    private function _tryStart(rate as Number, wantGyro as Boolean) as Boolean {
        var opts = {
            :period => 1,
            :accelerometer => {:enabled => true, :sampleRate => rate}
        };
        if (wantGyro) {
            opts[:gyroscope] = {:enabled => true, :sampleRate => rate};
        }
        try {
            Sensor.registerSensorDataListener(method(:onData), opts);
            return true;
        } catch (e) {
            return false;
        }
    }

    function stop() as Void {
        try {
            Sensor.unregisterSensorDataListener();
        } catch (e) {}
    }

    function onData(data as Sensor.SensorData) as Void {
        // Self-diagnosing: any exception in the data path is caught and shown
        // on the watch face instead of throwing the generic Connect IQ "IQ!"
        // crash screen — so a field crash reports its own cause.
        try {
            _onDataInner(data);
        } catch (ex) {
            err = "ERR " + ex.getErrorMessage();
            stop();
            WatchUi.requestUpdate();
        }
    }

    function _onDataInner(data as Sensor.SensorData) as Void {
        var acc = data.accelerometerData;
        if (acc == null) { return; }
        // On this device/firmware the axis arrays can be null even when the
        // container isn't (e.g. a batch with no fresh accel) — guard them.
        var axs = acc.x, ays = acc.y, azs = acc.z;
        if (axs == null || ays == null || azs == null) { return; }
        var gyr = data.gyroscopeData;   // null when accel-only
        var gxs = (gyr != null) ? gyr.x : null;
        var gys = (gyr != null) ? gyr.y : null;
        var gzs = (gyr != null) ? gyr.z : null;
        var n = axs.size();
        var gN = (gxs != null) ? gxs.size() : 0;
        var burst = false;
        var preCap = _preSamples * COLS;
        var maxCap = _maxCapSamples * COLS;

        for (var i = 0; i < n; i++) {
            var ax = _num(axs[i]), ay = _num(ays[i]), az = _num(azs[i]);
            var gx = 0, gy = 0, gz = 0;
            if (i < gN) { gx = _num(gxs[i]); gy = _num(gys[i]); gz = _num(gzs[i]); }
            var mag2 = ax*ax + ay*ay + az*az;
            if (mag2 > BURST_MG * BURST_MG) { burst = true; }

            if (capturing) {
                if (_cap.size() < maxCap) {
                    _cap.add(ax); _cap.add(ay); _cap.add(az);
                    _cap.add(gx); _cap.add(gy); _cap.add(gz);
                }
            } else {
                _pre.add(ax); _pre.add(ay); _pre.add(az);
                _pre.add(gx); _pre.add(gy); _pre.add(gz);
                // trim in one-second chunks to avoid per-sample reallocation
                if (_pre.size() > preCap + n * COLS) {
                    _pre = _pre.slice(_pre.size() - preCap, null);
                }
            }
        }

        if (!capturing && burst) {
            capturing = true;
            _cap = _pre.slice(0, null);   // copy the pre-roll in
            _pre = [];
            _quietBatches = 0;
            if (Toybox.Attention has :vibrate) {
                Toybox.Attention.vibrate([new Toybox.Attention.VibeProfile(60, 120)]);
            }
        } else if (capturing) {
            _quietBatches = burst ? 0 : (_quietBatches + 1);
            // ~1 batch/second (:period => 1); 2 quiet batches or the cap ends it
            if (_quietBatches >= 2 || _cap.size() >= maxCap) {
                capturing = false;
                if (swings.size() >= MAX_SWINGS) { swings = swings.slice(1, null); }
                swings.add(_cap);
                _cap = [];
                _pre = [];
            }
        }
        WatchUi.requestUpdate();
    }
}
