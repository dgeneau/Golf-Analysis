// Uploads raw swing segments straight to Supabase over the phone's
// connection (CIQ proxies makeWebRequest through Garmin Connect Mobile —
// no companion-app code needed for the pilot).
//
// Table: garmin_pilot (see supabase/migration-garmin-pilot.sql).
// The anon key is the same publishable key the web app ships; the table's
// RLS allows INSERT only, so the key can contribute data but read nothing.
import Toybox.Communications;
import Toybox.Lang;
import Toybox.System;
import Toybox.WatchUi;

module Uploader {
    const URL = "https://gdzloagomjndfolqngit.supabase.co/rest/v1/garmin_pilot";
    const ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdkemxvYWdvbWpuZGZvbHFuZ2l0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc5NDM0MjEsImV4cCI6MjEwMzUxOTQyMX0.xNWZfSVMkzfoEqFn3v4JMEIh6jOEhzDK7iu1yBw9lws";

    var _pending as Number = 0;
    var _ok as Number = 0;
    var _view as GLoggerView?;

    function uploadAll(rec as Recorder, view as GLoggerView) as Void {
        _view = view;
        _pending = rec.swings.size();
        _ok = 0;
        var dev = System.getDeviceSettings();
        for (var i = 0; i < rec.swings.size(); i++) {
            var flat = rec.swings[i] as Array;
            var body = {
                "device" => "vivoactive4",
                "part" => dev.partNumber,
                "rate_hz" => rec.rateHz,
                "has_gyro" => rec.hasGyro,
                "cols" => 5,                     // reshape by 5: t_ms, kind, x, y, z
                "n" => flat.size() / 5,          // row count (accel + gyro rows)
                "payload" => flat                // FLAT [t_ms,kind,x,y,z,...] kind 0=accel mG, 1=gyro deg/s
            };
            Communications.makeWebRequest(URL, body, {
                :method => Communications.HTTP_REQUEST_METHOD_POST,
                :headers => {
                    "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON,
                    "apikey" => ANON,
                    "Authorization" => "Bearer " + ANON,
                    "Prefer" => "return=minimal"
                },
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_TEXT_PLAIN
            }, new Lang.Method(Uploader, :onResponse));   // module callback: method() needs an instance, modules have none
        }
    }

    function onResponse(code as Number, data as Dictionary or String or Null) as Void {
        _pending -= 1;
        if (code == 201 || code == 200) { _ok += 1; }
        if (_view != null) {
            _view.uploadStatus = _pending > 0
                ? ("uploading... " + _ok + " ok")
                : (_ok + " uploaded (last code " + code + ")");
            WatchUi.requestUpdate();
        }
    }
}
