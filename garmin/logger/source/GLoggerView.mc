// One-screen status view: the probed sensor caps (the Phase-0 answer),
// swings captured, upload state. SELECT uploads, BACK exits.
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

class GLoggerView extends WatchUi.View {
    public var uploadStatus as String = "SELECT to upload";

    function initialize() {
        View.initialize();
    }

    function onUpdate(dc as Dc) as Void {
        var app = Application.getApp() as GLoggerApp;
        var rec = app.recorder;
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_WHITE);
        dc.clear();
        var cx = dc.getWidth() / 2;
        var y = dc.getHeight() / 6;
        dc.drawText(cx, y, Graphics.FONT_SMALL, "DR Logger", Graphics.TEXT_JUSTIFY_CENTER);
        y += dc.getFontHeight(Graphics.FONT_SMALL) + 6;
        if (rec != null) {
            dc.drawText(cx, y, Graphics.FONT_MEDIUM, rec.status, Graphics.TEXT_JUSTIFY_CENTER);
            y += dc.getFontHeight(Graphics.FONT_MEDIUM) + 6;
            var line = rec.capturing ? "CAPTURING" : ("swings: " + rec.swings.size());
            dc.drawText(cx, y, Graphics.FONT_MEDIUM, line, Graphics.TEXT_JUSTIFY_CENTER);
            y += dc.getFontHeight(Graphics.FONT_MEDIUM) + 6;
        }
        dc.drawText(cx, y, Graphics.FONT_XTINY, uploadStatus, Graphics.TEXT_JUSTIFY_CENTER);
    }
}
