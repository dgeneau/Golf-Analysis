// Downrange Garmin pilot logger — Phase 0.
// Probes the device's real sensor caps, records swing bursts, uploads raw
// segments. Analysis happens off-watch, in the SwingCoach Python pipeline.
import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

class GLoggerApp extends Application.AppBase {
    var recorder as Recorder?;

    function initialize() {
        AppBase.initialize();
    }

    function onStart(state as Dictionary?) as Void {
        recorder = new Recorder();
        recorder.start();
    }

    function onStop(state as Dictionary?) as Void {
        if (recorder != null) {
            recorder.stop();
        }
    }

    function getInitialView() as [Views] or [Views, InputDelegates] {
        var view = new GLoggerView();
        return [view, new GLoggerDelegate(view)];
    }
}
