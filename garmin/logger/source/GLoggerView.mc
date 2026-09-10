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
            if (rec.err != null) {
                // wrap the caught error across the face so it's readable
                dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_WHITE);
                var w = dc.getWidth() - 20;
                dc.drawText(cx, y, Graphics.FONT_XTINY, "CRASH:", Graphics.TEXT_JUSTIFY_CENTER);
                y += dc.getFontHeight(Graphics.FONT_XTINY) + 2;
                var msg = rec.err;
                var per = 22;   // rough chars per line at XTINY
                for (var p = 0; p < msg.length(); p += per) {
                    var end = (p + per < msg.length()) ? p + per : msg.length();
                    dc.drawText(cx, y, Graphics.FONT_XTINY, msg.substring(p, end),
                                Graphics.TEXT_JUSTIFY_CENTER);
                    y += dc.getFontHeight(Graphics.FONT_XTINY);
                }
                return;
            }
            dc.drawText(cx, y, Graphics.FONT_MEDIUM, rec.status, Graphics.TEXT_JUSTIFY_CENTER);
            y += dc.getFontHeight(Graphics.FONT_MEDIUM) + 6;
            var line = rec.capturing ? "CAPTURING" : ("swings: " + rec.swings.size());
            dc.drawText(cx, y, Graphics.FONT_MEDIUM, line, Graphics.TEXT_JUSTIFY_CENTER);
            y += dc.getFontHeight(Graphics.FONT_MEDIUM) + 6;
        }
        dc.drawText(cx, y, Graphics.FONT_XTINY, uploadStatus, Graphics.TEXT_JUSTIFY_CENTER);
    }
}
