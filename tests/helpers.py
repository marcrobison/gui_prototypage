import os
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from security_station.auth import PasswordStore  # noqa: E402
from security_station.eventlog import EventLog  # noqa: E402
from security_station.station import Station  # noqa: E402


def qt_app() -> QtWidgets.QApplication:
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class TempStation:
    """A Station backed by a throwaway config + database."""

    def __init__(self):
        qt_app()
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name)
        self.passwords = PasswordStore(self.path / "config.json")
        self.log = EventLog(self.path / "security.db")
        self.station = Station(self.passwords, self.log)

    def close(self):
        self.log.close()
        self.dir.cleanup()


def run_with_event_loop(fn, timeout: float = 15.0):
    """Run `fn` on a worker thread while the Qt main thread keeps processing events."""
    app = qt_app()
    result, error = {}, {}

    def target():
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            error["exc"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    deadline = time.monotonic() + timeout
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    thread.join(0.1)
    if thread.is_alive():
        raise TimeoutError("worker thread did not finish")
    if "exc" in error:
        raise error["exc"]
    return result.get("value")
