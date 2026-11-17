"""HTTPS server exposing the station to browsers on the LAN.

Runs `http.server` on a background thread inside the PySide6 process. PySide6's
QtHttpServer binding can only return plain-text bodies, so it can't serve this UI.
- Live state is pushed with Server-Sent Events (/api/events).
- Actions (arm, disarm, relay, buzzer) need the station password on every request.
  The scrypt check runs on the request thread, and the state change itself always
  runs on the Qt main thread through MainThreadInvoker.
"""
import json
import ssl
import sys
import threading
import urllib.parse
from concurrent.futures import Future
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .. import config
from ..eventlog import SEVERITIES
from ..station import ACTIONS, Station

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/static/app.css": ("app.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
MAX_BODY = 4096
SSE_KEEPALIVE_S = 15
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                                "base-uri 'none'; form-action 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


class MainThreadInvoker(QObject):
    """Run a callable on the thread this object lives in (the Qt main thread) and wait for it."""

    _job = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._job.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, job):
        fn, args, future = job
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(fn(*args))
        except Exception as exc:  # noqa: BLE001 - forwarded to the waiting thread
            future.set_exception(exc)

    def call(self, fn, *args, timeout: float = 10.0):
        future: Future = Future()
        self._job.emit((fn, args, future))
        return future.result(timeout)


class SnapshotHub:
    """Latest serialised snapshot, shared with any number of SSE client threads."""

    def __init__(self):
        self._cond = threading.Condition()
        self._payload = b"{}"
        self._version = 0
        self._closed = False

    def publish(self, payload: bytes):
        with self._cond:
            self._payload = payload
            self._version += 1
            self._cond.notify_all()

    def latest(self) -> bytes:
        with self._cond:
            return self._payload

    def wait(self, last_version: int, timeout: float) -> tuple[int, bytes, bool]:
        with self._cond:
            self._cond.wait_for(lambda: self._version != last_version or self._closed, timeout)
            return self._version, self._payload, self._closed

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify_all()


class SnapshotPublisher(QObject):
    """Coalesces station changes and publishes a JSON snapshot at most every 200 ms."""

    def __init__(self, station: Station, hub: SnapshotHub, parent: QObject | None = None):
        super().__init__(parent)
        self.station = station
        self.hub = hub
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.publish_now)
        station.changed.connect(self._schedule)
        self.publish_now()

    def _schedule(self):
        if not self._timer.isActive():
            self._timer.start()

    def publish_now(self):
        self.hub.publish(json.dumps(self.station.snapshot(), separators=(",", ":")).encode())


@dataclass
class AppContext:
    station: Station
    hub: SnapshotHub
    invoker: MainThreadInvoker


class RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SecurityStation"
    sys_version = ""
    server: "StationHTTPServer"

    # ------------------------------------------------------------- helpers
    @property
    def app(self) -> AppContext:
        return self.server.app

    def log_message(self, format, *args):  # noqa: A002 - signature from base class
        if self.command == "POST" or (args and str(args[0]).startswith(("4", "5"))):
            super().log_message(format, *args)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _error(self, status: HTTPStatus, message: str):
        if self.command == "POST":
            self.close_connection = True   # the request body may be unread; don't reuse the socket
        self._json(status, {"ok": False, "message": message})

    # -------------------------------------------------------------- routes
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        path = url.path
        if path in STATIC_FILES:
            name, ctype = STATIC_FILES[path]
            self._send(200, (STATIC_DIR / name).read_bytes(), ctype)
        elif path == "/api/state":
            self._send(200, self.app.hub.latest(), "application/json")
        elif path == "/api/events":
            self._stream_events()
        elif path == "/api/logs":
            self._logs(query)
        elif path == "/api/logs.csv":
            csv_text = self.app.station.log.to_csv()
            self._send(200, csv_text.encode(), "text/csv; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="security_logs.csv"'})
        else:
            self._error(HTTPStatus.NOT_FOUND, "Not found")

    do_HEAD = do_GET

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/api/action":
            return self._error(HTTPStatus.NOT_FOUND, "Not found")
        # Requiring JSON forces a CORS preflight for cross-site requests, which we never approve.
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Expected application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, "Bad Content-Length")
        if length <= 0 or length > MAX_BODY:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Body too large or empty")
        try:
            body = json.loads(self.rfile.read(length))
            action = body["action"]
            password = body["password"]
        except (ValueError, KeyError, TypeError):
            return self._error(HTTPStatus.BAD_REQUEST, "Expected {action, password}")
        if action not in ACTIONS or not isinstance(password, str):
            return self._error(HTTPStatus.BAD_REQUEST, "Unknown action")

        station = self.app.station
        source = f"Web ({self.client_address[0]})"
        authorised = station.passwords.verify(password)   # slow scrypt, off the GUI thread
        fn = station.apply if authorised else station.reject
        result = self.app.invoker.call(fn, action, source)
        status = HTTPStatus.OK if authorised else HTTPStatus.UNAUTHORIZED
        self._json(status, {"ok": result.ok, "message": result.message})

    def _logs(self, query: dict):
        severity = query.get("severity", [None])[0]
        if severity not in SEVERITIES:
            severity = None
        try:
            limit = int(query.get("limit", [config.LOG_TABLE_ROWS])[0])
        except ValueError:
            limit = config.LOG_TABLE_ROWS
        log = self.app.station.log
        self._json(200, {"total": log.count(), "events": log.recent(limit, severity)})

    def _stream_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.close_connection = True
        version = -1
        try:
            self.wfile.write(b"retry: 2000\n\n")
            while True:
                new_version, payload, closed = self.app.hub.wait(version, SSE_KEEPALIVE_S)
                if closed:
                    break
                if new_version != version:
                    version = new_version
                    self.wfile.write(b"data: " + payload + b"\n\n")
                else:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (OSError, ssl.SSLError):
            pass  # client went away


def _redirect_plain_http(sock, port: int) -> bool:
    """If a browser speaks plain HTTP to the HTTPS port, redirect it instead of failing."""
    try:
        head = sock.recv(2048, 0x2)  # MSG_PEEK
    except OSError:
        return True
    if not head or not head[:8].split(b" ")[0].isalpha():
        return False  # empty or a TLS ClientHello (starts with 0x16)
    lines = head.decode("latin-1", "replace").split("\r\n")
    path = lines[0].split(" ")[1] if len(lines[0].split(" ")) > 1 else "/"
    host = next((l.split(":", 1)[1].strip() for l in lines[1:] if l.lower().startswith("host:")), "")
    host = host.rsplit(":", 1)[0] if host and not host.endswith("]") else host
    location = f"https://{host or 'localhost'}:{port}{path if path.startswith('/') else '/'}"
    location = location.replace("\r", "").replace("\n", "")
    try:
        sock.sendall((f"HTTP/1.1 301 Moved Permanently\r\nLocation: {location}\r\n"
                      "Content-Length: 0\r\nConnection: close\r\n\r\n").encode("latin-1", "replace"))
    except OSError:
        pass
    return True


class StationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True

    def __init__(self, address, app: AppContext, ssl_context: ssl.SSLContext | None):
        self.app = app
        self.ssl_context = ssl_context
        super().__init__(address, RequestHandler)

    def finish_request(self, request, client_address):
        """Runs on the per-connection thread, so a slow TLS handshake never blocks accept()."""
        request.settimeout(30)
        if self.ssl_context is not None:
            if _redirect_plain_http(request, self.server_address[1]):
                return
            try:
                tls = self.ssl_context.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                return  # e.g. the browser rejected our self-signed cert on this attempt
            try:
                super().finish_request(tls, client_address)
            finally:
                self.shutdown_request(tls)
            return
        super().finish_request(request, client_address)

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, ssl.SSLError)):
            return
        super().handle_error(request, client_address)


class WebServer:
    def __init__(self, station: Station, host: str = config.WEB_HOST, port: int = config.WEB_PORT,
                 cert: tuple[Path, Path] | None = None):
        self.hub = SnapshotHub()
        self.invoker = MainThreadInvoker()
        self.publisher = SnapshotPublisher(station, self.hub)
        ctx = None
        if cert is not None:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(*cert)
        self.scheme = "https" if ctx else "http"
        self.httpd = StationHTTPServer((host, port), AppContext(station, self.hub, self.invoker), ctx)
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="web-server", daemon=True)

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def url(self, host: str) -> str:
        return f"{self.scheme}://{host}:{self.port}"

    def start(self):
        self._thread.start()

    def stop(self):
        self.hub.close()
        self.httpd.shutdown()
        self.httpd.server_close()
