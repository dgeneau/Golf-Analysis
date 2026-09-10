// SELECT (or tap) uploads the stored swings, one HTTPS POST per swing.
import Toybox.Lang;
import Toybox.WatchUi;

class GLoggerDelegate extends WatchUi.BehaviorDelegate {
    private var _view as GLoggerView;

    function initialize(view as GLoggerView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    function onSelect() as Boolean {
        var app = Application.getApp() as GLoggerApp;
        var rec = app.recorder;
        if (rec == null || rec.swings.size() == 0) {
            _view.uploadStatus = "no swings yet";
            WatchUi.requestUpdate();
            return true;
        }
        _view.uploadStatus = "uploading " + rec.swings.size() + "...";
        WatchUi.requestUpdate();
        try {
            Uploader.uploadAll(rec, _view);
        } catch (ex) {
            rec.err = "UPLOAD " + ex.getErrorMessage();
            WatchUi.requestUpdate();
        }
        return true;
    }
}
