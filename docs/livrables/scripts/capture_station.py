"""Runs the real station (Qt window + web server + simulator) for the report screenshots.

Usage: capture_station.py <data_dir> <port> <out_dir>
Reads one command per line on stdin and answers "ok" on stdout:
  shot <name>      save the Qt window as <out_dir>/<name>.png
  expand <tile>    open a tile's expanded view / collapse
  arm | badpw      arm the system / try a wrong password
  alarm | resume   force an intrusion (object at 18 cm + motion) / back to normal
  quit
The app itself is not modified: this script only drives its public objects.
"""
import os
import random
import sys
import threading
from pathlib import Path

data_dir, port, out_dir = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
os.environ["SECURITY_STATION_DATA"] = data_dir
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402

from security_station.auth import PasswordStore  # noqa: E402
from security_station.eventlog import EventLog  # noqa: E402
from security_station.network import ensure_certificate, primary_lan_ip  # noqa: E402
from security_station.qt_ui.dashboard import MainWindow  # noqa: E402
from security_station.qt_ui.theme import STYLESHEET, app_font  # noqa: E402
from security_station.simulator import SensorSimulator  # noqa: E402
from security_station.station import Station  # noqa: E402
from security_station.web.server import WebServer  # noqa: E402

app = QtWidgets.QApplication(sys.argv)
app.setStyle("Fusion")
app.setFont(app_font())
app.setStyleSheet(STYLESHEET)

passwords = PasswordStore()
log = EventLog()
station = Station(passwords, log)
simulator = SensorSimulator(station, random.Random(7))
web = WebServer(station, "0.0.0.0", port, ensure_certificate())
web.start()
window = MainWindow(station, web.url(primary_lan_ip()))
window.resize(1024, 600)
window.show()
simulator.start()
out_dir.mkdir(parents=True, exist_ok=True)


def handle(line: str):
    cmd, *args = line.split()
    if cmd == "shot":
        window.grab().save(str(out_dir / f"{args[0]}.png"))
    elif cmd == "expand":
        window.dashboard.expand(args[0])
    elif cmd == "collapse":
        window.dashboard.collapse()
    elif cmd == "arm":
        station.perform("arm", "1234", "Desktop")
    elif cmd == "badpw":
        station.perform("arm", "0000", "Desktop")
    elif cmd == "alarm":
        simulator.stop()
        station.update_distance(18.0)
        station.update_motion(True, "Zone A")
    elif cmd == "resume":
        station.update_motion(False)
        simulator.start()
    elif cmd == "quit":
        web.stop()
        app.quit()
    print("ok", flush=True)


class Control(QObject):
    command = Signal(str)


control = Control()
control.command.connect(handle, Qt.ConnectionType.QueuedConnection)


def read_stdin():
    for raw in sys.stdin:
        if raw.strip():
            control.command.emit(raw.strip())


threading.Thread(target=read_stdin, daemon=True).start()
print("ready", flush=True)
app.exec()
log.close()
