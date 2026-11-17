"""Desktop dashboard: compact tiles laid out like docs/figures/guide.jpg, plus an
expanded view for each tile (click a tile, then use ← Back or Esc to return)."""
import time

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut

from .. import config
from ..station import Station
from . import theme
from .widgets import (ArcGauge, ArmedWord, AuthForm, ClockLabel, ControlButtons, DefaultPasswordWarning,
                      DistancePlot, EnvironmentPlot, Fact, LogTable, PirStateView, StatusBadge, Tile,
                      fact_grid, fmt_clock, fmt_cm, label, log_buttons, setup_table)

TITLES = {
    "status": "System Status",
    "pir": "PIR Motion Detector",
    "ultrasonic": "Ultrasonic Distance",
    "environment": "Ambient Environment (DHT)",
    "manual": "Manual Controls",
    "auth": "User Authentication",
    "logs": "Security Logs (SQLite)",
}


def temp_gauge() -> ArcGauge:
    return ArcGauge("Temperature", 15, 30, lambda v: f"{v:.1f}°C")


def humidity_gauge() -> ArcGauge:
    return ArcGauge("Humidity", 0, 100, lambda v: f"{v:.0f}%")


# ============================================================ compact tiles
class SystemArmed(Tile):
    def __init__(self, station: Station):
        super().__init__("status")
        self.title.hide()
        self.body.addWidget(ClockLabel(17))
        self.body.addStretch(1)
        self.body.addWidget(label("SYSTEM\nSTATUS:", size=19, bold=True, align=Qt.AlignmentFlag.AlignCenter))
        self.body.addWidget(ArmedWord(station, 24))
        self.body.addStretch(1)
        self.body.addWidget(StatusBadge(station))


class PirMotion(Tile):
    def __init__(self, station: Station):
        super().__init__("pir", "PIR Motion Detector")
        self.body.addWidget(PirStateView(station), 1)


class UltrasonicDistance(Tile):
    def __init__(self, station: Station):
        super().__init__("ultrasonic", "ULTRASONIC DISTANCE")
        self.station = station
        self.reading = label("-- cm", size=18, bold=True, color=theme.ACCENT)
        font = self.reading.font()
        font.setItalic(True)
        self.reading.setFont(font)
        self.header.insertWidget(2, self.reading)
        self.body.addWidget(DistancePlot(station), 1)
        station.distance_changed.connect(self.refresh)
        if station.distance is not None:
            self.refresh(station.distance)

    def refresh(self, cm: float):
        self.reading.setText(fmt_cm(cm))
        self.reading.setStyleSheet(f"color: {theme.RED if cm < self.station.threshold else theme.ACCENT};")


class AmbientEnvironment(Tile):
    def __init__(self, station: Station):
        super().__init__("environment", "Ambient Environment (DHT)")
        row = QtWidgets.QHBoxLayout()
        self.temperature = temp_gauge()
        self.humidity = humidity_gauge()
        row.addWidget(self.temperature)
        row.addWidget(self.humidity)
        self.body.addLayout(row, 1)
        station.environment_changed.connect(self.refresh)
        if station.temperature is not None:
            self.refresh(station.temperature, station.humidity)

    def refresh(self, temperature: float, humidity: float):
        self.temperature.set_value(temperature)
        self.humidity.set_value(humidity)


class ManualControls(Tile):
    def __init__(self, station: Station):
        super().__init__("manual", "Manual Controls")
        self.body.addStretch(1)
        self.body.addWidget(ControlButtons(station))
        self.body.addStretch(1)


class SystemAuth(Tile):
    def __init__(self, station: Station):
        super().__init__("auth", "USER AUTHENTICATION")
        self.body.addSpacing(10)
        self.body.addWidget(AuthForm(station))
        self.body.addStretch(1)
        self.body.addWidget(DefaultPasswordWarning(station))


class SecurityLogs(Tile):
    def __init__(self, station: Station):
        super().__init__("logs", "RECENT SECURITY LOGS")
        self.header.insertWidget(1, label("(SQLite)", role="muted"))
        self.table = LogTable(station)
        for i, button in enumerate(log_buttons(station, self.table, self)):
            self.header.insertWidget(3 + i, button)
        self.body.addWidget(self.table, 1)


# =========================================================== expanded views
class StatusDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        self.station = station
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(ClockLabel(40))
        layout.addWidget(ArmedWord(station, 48))
        layout.addWidget(StatusBadge(station, size=24, icon=48))
        layout.addSpacing(16)
        self.facts = {k: Fact(k) for k in ("Uptime", "Distance", "Motion", "Temperature",
                                            "Humidity", "Relay", "Buzzer", "Logged events")}
        layout.addLayout(fact_grid(list(self.facts.values()), columns=4))
        layout.addStretch(1)
        station.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        s = self.station
        uptime = int(time.time() - s.started_at)
        self.facts["Uptime"].set(f"{uptime // 3600}h {uptime % 3600 // 60:02d}m {uptime % 60:02d}s")
        self.facts["Distance"].set(fmt_cm(s.distance))
        self.facts["Motion"].set(f"MOTION ({s.motion_zone})" if s.motion else "CLEAR")
        self.facts["Temperature"].set("--" if s.temperature is None else f"{s.temperature:.1f} °C")
        self.facts["Humidity"].set("--" if s.humidity is None else f"{s.humidity:.1f} %")
        self.facts["Relay"].set("ON" if s.relay_on else "OFF")
        self.facts["Buzzer"].set("SOUNDING" if s.buzzer_active else "Silent")
        self.facts["Logged events"].set(str(s.log.count()))


class PirDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        self.station = station
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(PirStateView(station, size=40, icon=False))
        self.counts = {zone: Fact(f"{zone} detections") for zone in config.PIR_ZONES}
        layout.addLayout(fact_grid(list(self.counts.values()), columns=len(self.counts)))
        layout.addWidget(label("Recent detections", role="title"))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Zone", "Duration", "While"])
        setup_table(self.table)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        station.motion_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        for zone, fact in self.counts.items():
            fact.set(str(self.station.zone_counts.get(zone, 0)))
        detections = list(self.station.detections)
        self.table.setRowCount(len(detections))
        for row, d in enumerate(detections):
            bg = theme.SEVERITY_BG["HIGH" if d["armed"] else "INFO"]
            values = [fmt_clock(d["ts"]), d["zone"],
                      "active" if d["duration"] is None else f"{d['duration']:.1f} s",
                      "Armed" if d["armed"] else "Disarmed"]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setBackground(QColor(bg))
                self.table.setItem(row, col, item)


class UltrasonicDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        self.station = station
        layout = QtWidgets.QVBoxLayout(self)
        self.facts = {
            "current": Fact("Current", accent=True), "min": Fact("Min (60 s)"), "avg": Fact("Avg (60 s)"),
            "max": Fact("Max (60 s)"), "threshold": Fact("Threshold"), "breaches": Fact("Crossings (session)"),
        }
        layout.addLayout(fact_grid(list(self.facts.values()), columns=6))
        layout.addWidget(DistancePlot(station), 1)
        station.distance_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        stats = self.station.distance_stats()
        self.facts["current"].set(fmt_cm(self.station.distance))
        for key in ("min", "avg", "max"):
            self.facts[key].set(fmt_cm(stats[key]))
        self.facts["threshold"].set(fmt_cm(self.station.threshold))
        self.facts["breaches"].set(str(self.station.breaches))


class EnvironmentDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        gauges = QtWidgets.QHBoxLayout()
        self.temperature = temp_gauge()
        self.humidity = humidity_gauge()
        for g in (self.temperature, self.humidity):
            g.setMinimumHeight(170)
            gauges.addWidget(g)
        layout.addLayout(gauges, 2)
        charts = QtWidgets.QHBoxLayout()
        for title, plot in (("Temperature (last 10 min)", EnvironmentPlot(station, 1, "°C", 2.0)),
                            ("Humidity (last 10 min)", EnvironmentPlot(station, 2, "% RH", 6.0))):
            column = QtWidgets.QVBoxLayout()
            column.addWidget(label(title, role="muted"))
            column.addWidget(plot, 1)
            charts.addLayout(column)
        layout.addLayout(charts, 3)
        station.environment_changed.connect(self.refresh)
        if station.temperature is not None:
            self.refresh(station.temperature, station.humidity)

    def refresh(self, temperature: float, humidity: float):
        self.temperature.set_value(temperature)
        self.humidity.set_value(humidity)


class ManualDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(ControlButtons(station, big=True))
        layout.addSpacing(24)
        self.relay = Fact("Relay output")
        self.buzzer = Fact("Buzzer")
        layout.addLayout(fact_grid([self.relay, self.buzzer], columns=2))
        layout.addWidget(label("Every control requires the station password. Actions are recorded "
                               "in the security log.", role="muted", align=Qt.AlignmentFlag.AlignCenter))
        layout.addStretch(2)
        station.controls_changed.connect(self.refresh)
        self.refresh(station.relay_on, station.buzzer_active)

    def refresh(self, relay_on: bool, buzzer: bool):
        self.relay.set("ON" if relay_on else "OFF")
        self.buzzer.set("SOUNDING" if buzzer else "Silent")


class AuthDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        outer = QtWidgets.QHBoxLayout(self)
        outer.addStretch(1)
        column = QtWidgets.QVBoxLayout()
        column.addStretch(1)
        column.addWidget(ArmedWord(station, 40))
        column.addSpacing(16)
        form = AuthForm(station, big=True)
        form.setMinimumWidth(380)
        column.addWidget(form)
        column.addWidget(DefaultPasswordWarning(station))
        column.addStretch(2)
        outer.addLayout(column)
        outer.addStretch(1)


class LogsDetail(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(label("Severity", role="muted"))
        self.filter = QtWidgets.QComboBox()
        self.filter.addItems(["All", "HIGH", "MEDIUM", "INFO"])
        bar.addWidget(self.filter)
        bar.addStretch(1)
        self.table = LogTable(station, limit=config.LOG_CAP)
        for button in log_buttons(station, self.table, self):
            bar.addWidget(button)
        layout.addLayout(bar)
        layout.addWidget(self.table, 1)
        self.filter.currentTextChanged.connect(lambda t: self.table.set_severity(None if t == "All" else t))


DETAIL_VIEWS = {
    "status": StatusDetail,
    "pir": PirDetail,
    "ultrasonic": UltrasonicDetail,
    "environment": EnvironmentDetail,
    "manual": ManualDetail,
    "auth": AuthDetail,
    "logs": LogsDetail,
}


# ================================================================ dashboard
class ExpandedPage(QtWidgets.QWidget):
    def __init__(self, station: Station):
        super().__init__()
        self.station = station
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QtWidgets.QHBoxLayout()
        self.back = QtWidgets.QPushButton("← Back", objectName="back")
        self.back.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(self.back)
        header.addSpacing(12)
        self.title = label("", size=16, bold=True)
        header.addWidget(self.title)
        header.addStretch(1)
        layout.addLayout(header)
        self.frame = Tile("expanded")
        self.frame.setCursor(Qt.CursorShape.ArrowCursor)
        self.frame.mouseReleaseEvent = lambda e: None
        self.frame.expand_button.hide()
        self.frame.title.hide()
        self.views = QtWidgets.QStackedWidget()
        self.frame.body.addWidget(self.views, 1)
        layout.addWidget(self.frame, 1)
        self._built: dict[str, QtWidgets.QWidget] = {}

    def show_view(self, key: str):
        if key not in self._built:
            view = DETAIL_VIEWS[key](self.station)
            self._built[key] = view
            self.views.addWidget(view)
        self.title.setText(TITLES[key])
        self.views.setCurrentWidget(self._built[key])


class Dashboard(QtWidgets.QWidget):
    def __init__(self, station: Station, footer_text: str = ""):
        super().__init__()
        self.station = station
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.system_armed = SystemArmed(station)
        self.user_auth = SystemAuth(station)
        self.security_logs = SecurityLogs(station)
        self.pir_motion = PirMotion(station)
        self.ambient_environment = AmbientEnvironment(station)
        self.manual_controls = ManualControls(station)
        self.ultrasonic_distance = UltrasonicDistance(station)
        self.tiles = [self.system_armed, self.user_auth, self.security_logs, self.pir_motion,
                      self.ambient_environment, self.manual_controls, self.ultrasonic_distance]
        for tile in self.tiles:
            tile.expand_requested.connect(self.expand)

        self.stack = QtWidgets.QStackedWidget()
        self.grid_page = QtWidgets.QWidget()
        self._layout_setup(self.grid_page)
        self.expanded_page = ExpandedPage(station)
        self.expanded_page.back.clicked.connect(self.collapse)
        self.stack.addWidget(self.grid_page)
        self.stack.addWidget(self.expanded_page)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 4)
        outer.setSpacing(6)
        outer.addWidget(self.stack, 1)
        self.footer = label(footer_text or "RASPBERRY PI SECURITY STATION", align=Qt.AlignmentFlag.AlignCenter)
        self.footer.setObjectName("footer")
        self.footer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.footer)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.collapse)

    def _layout_setup(self, page: QtWidgets.QWidget):
        """Same nesting as the original prototype; stretch factors follow guide.jpg."""
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(10)
        center_top = QtWidgets.QVBoxLayout()
        center_top.setSpacing(10)
        top_center_top = QtWidgets.QHBoxLayout()
        top_center_top.setSpacing(10)
        bottom_center_top = QtWidgets.QHBoxLayout()
        bottom_center_top.setSpacing(10)

        main_layout.addLayout(top_layout, 8)
        main_layout.addWidget(self.security_logs, 5)

        top_layout.addWidget(self.system_armed, 10)
        top_layout.addLayout(center_top, 27)
        top_layout.addWidget(self.user_auth, 11)

        center_top.addLayout(top_center_top, 5)
        center_top.addLayout(bottom_center_top, 2)

        top_center_top.addWidget(self.pir_motion, 1)
        top_center_top.addWidget(self.ultrasonic_distance, 2)

        bottom_center_top.addWidget(self.ambient_environment, 5)
        bottom_center_top.addWidget(self.manual_controls, 3)

    def expand(self, key: str):
        self.expanded_page.show_view(key)
        self.stack.setCurrentWidget(self.expanded_page)

    def collapse(self):
        self.stack.setCurrentWidget(self.grid_page)

    @property
    def expanded_key(self) -> str | None:
        if self.stack.currentWidget() is self.grid_page:
            return None
        return next((k for k, v in self.expanded_page._built.items()
                     if v is self.expanded_page.views.currentWidget()), None)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, station: Station, web_url: str | None = None):
        super().__init__()
        self.setWindowTitle("Raspberry Pi Security Station")
        footer = "RASPBERRY PI SECURITY STATION"
        if web_url:
            footer += f"     ·     WEB: {web_url}"
        self.dashboard = Dashboard(station, footer)
        self.setCentralWidget(self.dashboard)
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, activated=self.toggle_fullscreen)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
