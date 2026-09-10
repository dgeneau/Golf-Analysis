// Sensor capture: probe the highest accel(+gyro) rate this device accepts,
// keep a rolling pre-buffer, detect swing bursts, store raw segments.
//
// Units per the CIQ SensorData docs: accelerometer in milli-g (mG),
// gyroscope in degrees/second.
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.System;
import Toybox.WatchUi;

class Recorder {
    // ---- probed capabilities (shown on screen — the point of Phase 0) ----
    public var rateHz as Number = 0;        // accepted sample rate
    public var hasGyro as Boolean = false;  // did the device accept a gyro request?
    public var status as String = "probing sensors...";

    // ---- capture state ----
    public var swings as Array = [];        // stored segments (raw sample arrays)
    public var capturing as Boolean = false;

    // rolling pre-buffer + capture buffer (flat [ax,ay,az,gx,gy,gz] per sample)
    private var _pre as Array = [];
    private var _cap as Array = [];
    private var _quietBatches as Number = 0;

    private const PRE_SAMPLES = 150;        // ~1.5 s at 100 Hz (scales w/ rate)
    private const MAX_CAP = 600;            // hard cap per swing (~6 s at 100 Hz)
    private const MAX_SWINGS = 6;           // memory is tight on this tier
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
                    status = "" + rateHz + " Hz" + (hasGyro ? " + gyro" : ", accel only");
                    return;
                }
            }
        }
        status = "sensor listener refused";
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
        var acc = data.accelerometerData;
        if (acc == null) { return; }
        var gyr = data.gyroscopeData;   // null when accel-only
        var n = acc.x.size();
        var burst = false;
        for (var i = 0; i < n; i++) {
            var ax = acc.x[i], ay = acc.y[i], az = acc.z[i];
            var gx = 0, gy = 0, gz = 0;
            if (gyr != null && i < gyr.x.size()) {
                gx = gyr.x[i]; gy = gyr.y[i]; gz = gyr.z[i];
            }
            var s = [ax, ay, az, gx, gy, gz];
            var mag2 = ax*ax + ay*ay + az*az;
            if (mag2 > BURST_MG * BURST_MG) { burst = true; }
            if (capturing) {
                _cap.add(s);
            } else {
                _pre.add(s);
                if (_pre.size() > PRE_SAMPLES) { _pre = _pre.slice(1, null); }
            }
            if (mag2 < QUIET_MG * QUIET_MG && capturing) {
                // quiet counting happens per batch below; nothing per-sample
            }
        }
        if (!capturing && burst) {
            capturing = true;
            _cap = [];
            _cap.addAll(_pre);
            _quietBatches = 0;
            if (Toybox.Attention has :vibrate) {
                Toybox.Attention.vibrate([new Toybox.Attention.VibeProfile(60, 120)]);
            }
        } else if (capturing) {
            if (!burst) { _quietBatches += 1; } else { _quietBatches = 0; }
            // ~1 batch per second (:period => 1) — 2 quiet batches ends the swing
            if (_quietBatches >= 2 || _cap.size() >= MAX_CAP) {
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
