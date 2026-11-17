"""Wires the backend, the simulated sensors, the desktop window and the web server together."""
import argparse
import signal
import sys

from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication, QTimer

from . import config
from .auth import PasswordStore
from .eventlog import EventLog
from .network import CertificateError, ensure_certificate, primary_lan_ip
from .simulator import SensorSimulator
from .station import Station


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raspberry Pi security station")
    parser.add_argument("--fullscreen", action="store_true", help="start fullscreen (Pi touchscreen)")
    parser.add_argument("--headless", action="store_true", help="no desktop window, web UI only")
    parser.add_argument("--no-web", action="store_true", help="disable the LAN web UI")
    parser.add_argument("--host", default=config.WEB_HOST, help=f"web bind address (default {config.WEB_HOST})")
    parser.add_argument("--port", type=int, default=config.WEB_PORT, help=f"web port (default {config.WEB_PORT})")
    parser.add_argument("--insecure-http", action="store_true",
                        help="serve plain HTTP instead of HTTPS (passwords cross the network unencrypted)")
    return parser.parse_args(argv)


def start_web(station: Station, args: argparse.Namespace):
    from .web.server import WebServer
    cert = None
    if not args.insecure_http:
        try:
            cert = ensure_certificate()
        except CertificateError as exc:
            print(f"[web] disabled: {exc}", file=sys.stderr)
            return None, None
    try:
        server = WebServer(station, args.host, args.port, cert)
    except OSError as exc:
        print(f"[web] disabled: cannot listen on {args.host}:{args.port} ({exc.strerror})", file=sys.stderr)
        return None, None
    server.start()
    url = server.url(primary_lan_ip())
    print(f"[web] dashboard available on your network at {url}")
    if cert:
        print("[web] the certificate is self-signed: accept the browser warning once per device")
    else:
        print("[web] WARNING: plain HTTP, passwords are sent unencrypted", file=sys.stderr)
    return server, url


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    sys.stdout.reconfigure(line_buffering=True)
    app = QCoreApplication(sys.argv) if args.headless else QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Security Station")

    # Let Ctrl+C stop the Qt event loop cleanly.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(250)

    passwords = PasswordStore()
    if passwords.is_default:
        print(f"[auth] default password '{config.DEFAULT_PASSWORD}' in use: run `make set-password`")
    log = EventLog()
    station = Station(passwords, log)
    simulator = SensorSimulator(station)

    web, url = (None, None) if args.no_web else start_web(station, args)

    window = None
    if not args.headless:
        from .qt_ui.dashboard import MainWindow
        from .qt_ui.theme import STYLESHEET, app_font
        app.setStyle("Fusion")
        app.setFont(app_font())
        app.setStyleSheet(STYLESHEET)
        window = MainWindow(station, url)
        window.resize(1024, 600)
        window.showFullScreen() if args.fullscreen else window.show()

    simulator.start()
    exit_code = app.exec()

    # The event loop has stopped: nothing can touch the station or the database any more.
    simulator.stop()
    if web:
        web.stop()
    log.close()
    return exit_code
