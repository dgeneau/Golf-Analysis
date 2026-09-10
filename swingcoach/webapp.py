"""Local live dashboard server (stdlib only — no extra dependencies).

Serves the SwingCoach dashboard at http://localhost:<port> and pushes each
newly detected swing to the page over Server-Sent Events, so the board
updates the moment a swing finishes.

Endpoints:
    GET /              the dashboard page
    GET /session.json  all swings so far (dashboard bootstraps from this)
    GET /events        SSE stream; each event is one swing's JSON
"""
from __future__ import annotations

import http.server
import json
import logging
import pathlib
import queue
import threading
import webbrowser
from typing import List

log = logging.getLogger("swingcoach.web")

TEMPLATE = pathlib.Path(__file__).parent / "dashboard.html"

def _render_page() -> bytes:
    body = TEMPLATE.read_text()
    body = body.replace("/*__DATA__*/", "null", 1)
    page = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, "
            "maximum-scale=1, user-scalable=no, viewport-fit=cover\">"
            # Downrange flagstick favicon (inline SVG, no extra request)
            "<link rel=\"icon\" href=\"data:image/svg+xml,"
            "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
            "%3Crect width='64' height='64' rx='14' fill='%23f0ede2'/%3E"
            "%3Cpath d='M12 48 Q 27 18 43 48' stroke='%238a9270' stroke-width='4.5' "
            "stroke-dasharray='1 8' stroke-linecap='round' fill='none'/%3E"
            "%3Cline x1='43' y1='12' x2='43' y2='50' stroke='%2323221c' "
            "stroke-width='5' stroke-linecap='round'/%3E"
            "%3Cpath d='M43 14 L43 29 L59 21.5 Z' fill='%233c4a30'/%3E%3C/svg%3E\">"
            "</head><body>" + body + "</body></html>")
    return page.encode()


class DashboardServer:
    """Threaded HTTP + SSE server holding the session's swings."""

    def __init__(self, port: int = 8787, lever_m: float = 1.05):
        self.port = port
        self.lever_m = lever_m
        self.swings: List[dict] = []
        self.status = {"state": "starting", "detail": "", "battery": None}
        self._clients: List[queue.Queue] = []
        self._lock = threading.Lock()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # quiet
                pass

            def _send(self, code, ctype, payload: bytes):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, "text/html; charset=utf-8", _render_page())
                elif self.path == "/session.json":
                    with outer._lock:
                        payload = json.dumps({
                            "swings": outer.swings,
                            "lever_m": outer.lever_m,
                            "source": "live",
                            "status": outer.status,
                        }).encode()
                    self._send(200, "application/json", payload)
                elif self.path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    q: queue.Queue = queue.Queue()
                    with outer._lock:
                        outer._clients.append(q)
                    try:
                        while True:
                            try:
                                item = q.get(timeout=15.0)
                                data = json.dumps(item)
                                self.wfile.write(f"data: {data}\n\n".encode())
                            except queue.Empty:
                                self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        with outer._lock:
                            if q in outer._clients:
                                outer._clients.remove(q)
                else:
                    self._send(404, "text/plain", b"not found")

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)

    # -- lifecycle ------------------------------------------------------------
    def start(self, open_browser: bool = True) -> None:
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        url = f"http://localhost:{self.port}"
        log.info("Dashboard: %s", url)
        print(f"Dashboard running at {url}")
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass

    def stop(self) -> None:
        self._httpd.shutdown()

    # -- data -----------------------------------------------------------------
    def _broadcast(self, event: dict) -> None:
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            q.put(event)

    def add_swing(self, swing: dict) -> None:
        with self._lock:
            self.swings.append(swing)
        self._broadcast({"type": "swing", "swing": swing})

    def set_status(self, state: str, detail: str = "",
                   battery: "int | None" = None) -> None:
        """Sensor lifecycle: scanning / connected / ready / disconnected / error."""
        with self._lock:
            if battery is None:
                battery = self.status.get("battery")
            self.status = {"state": state, "detail": detail, "battery": battery}
        log.info("Sensor status: %s %s", state, detail)
        self._broadcast({"type": "status", "status": self.status})
