"""Reusable building blocks for the desktop UI.

Each component connects itself to the Station's signals, so the same component can be
placed both in a compact dashboard tile and in that tile's expanded view.
"""
import datetime
import math
import time

import pyqtgraph as pg
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen)

from .. import config
from ..station import ALERT, DISARMED, SECURE, Station
from . import theme

pg.setConfigOptions(antialias=True)


def set_prop(widget: QtWidgets.QWidget, name: str, value):
    """Change a dynamic property used by the stylesheet and re-apply styling."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def label(text: str = "", role: str | None = None, size: float | None = None, bold: bool = False,
          align: Qt.AlignmentFlag | None = None, color: str | None = None) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    if role:
        lbl.setProperty("role", role)
    if size or bold:
        font = lbl.font()
        if size:
            font.setPointSizeF(size)
        font.setBold(bold)
        lbl.setFont(font)
    if align is not None:
        lbl.setAlignment(align)
    if color:
        lbl.setStyleSheet(f"color: {color};")
    return lbl


def glow(widget: QtWidgets.QWidget, color: str, radius: float = 22):
    effect = QtWidgets.QGraphicsDropShadowEffect(widget)
    effect.setOffset(0, 0)
    effect.setBlurRadius(radius)
    effect.setColor(QColor(color))
    widget.setGraphicsEffect(effect)
    return effect


def fmt_clock(ts: float | None = None) -> str:
    """12-hour clock like the guide; built by hand because %p is empty in some locales."""
    t = datetime.datetime.fromtimestamp(ts or time.time())
    return f"{(t.hour % 12) or 12:02d}:{t.minute:02d}:{t.second:02d} {'AM' if t.hour < 12 else 'PM'}"


def fmt_cm(value: float | None) -> str:
    return "-- cm" if value is None else f"{value:.0f} cm"


# --------------------------------------------------------------------- tiles
class Tile(QtWidgets.QFrame):
    """Dashboard tile: a styled frame with a title row and an expand button.

    Clicking anywhere on the tile that isn't an interactive child (button, field, table)
    emits `expand_requested` with the tile's key.
    """

    expand_requested = Signal(str)

    def __init__(self, key: str, title: str = "", parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QtWidgets.QVBoxLayout(self)
        self.body.setContentsMargins(12, 8, 8, 10)
        self.body.setSpacing(6)

        self.header = QtWidgets.QHBoxLayout()
        self.header.setSpacing(8)
        self.title = label(title, role="title")
        self.header.addWidget(self.title)
        self.header.addStretch(1)
        self.expand_button = QtWidgets.QToolButton(text="⤢", objectName="expand")
        self.expand_button.setToolTip("Expand")
        self.expand_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_button.clicked.connect(lambda: self.expand_requested.emit(self.key))
        self.header.addWidget(self.expand_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(self.header)

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.expand_requested.emit(self.key)

    def enterEvent(self, event):
        set_prop(self, "hover", "true")
        super().enterEvent(event)

    def leaveEvent(self, event):
        set_prop(self, "hover", "false")
        super().leaveEvent(event)


class Fact(QtWidgets.QFrame):
    """Small label/value card used in expanded views."""

    def __init__(self, caption: str, value: str = "--", accent: bool = False):
        super().__init__(objectName="fact")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        layout.addWidget(label(caption, role="fact-label"))
        self.value = label(value, role="fact-value", color=theme.ACCENT if accent else None)
        layout.addWidget(self.value)

    def set(self, text: str):
        self.value.setText(text)


def fact_grid(facts: list[Fact], columns: int = 3) -> QtWidgets.QGridLayout:
    grid = QtWidgets.QGridLayout()
    grid.setSpacing(10)
    for i, fact in enumerate(facts):
        grid.addWidget(fact, i // columns, i % columns)
    return grid


# ------------------------------------------------------------ painted icons
class ShieldIcon(QtWidgets.QWidget):
    """Shield with a check (secure), cross (alert) or dash (disarmed)."""

    def __init__(self, size: int = 30):
        super().__init__()
        self.setFixedSize(size, size)
        self.status = SECURE

    def set_status(self, status: str):
        self.status = status
        self.update()

    def paintEvent(self, _):
        color = {SECURE: theme.GREEN, ALERT: theme.RED, DISARMED: theme.AMBER}[self.status]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 32, self.height() / 32)
        body = QPainterPath()
        body.moveTo(16, 2)
        body.lineTo(4, 7)
        body.lineTo(4, 15)
        body.cubicTo(4, 22.5, 9.1, 28.4, 16, 30)
        body.cubicTo(22.9, 28.4, 28, 22.5, 28, 15)
        body.lineTo(28, 7)
        body.closeSubpath()
        p.fillPath(body, QColor(color))
        pen = QPen(QColor("#06210f" if self.status == SECURE else "#2a0a0a"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self.status == SECURE:
            p.drawPolyline([QPointF(10, 16), QPointF(14, 20), QPointF(22, 11)])
        elif self.status == ALERT:
            p.drawLine(QPointF(11, 11), QPointF(21, 21))
            p.drawLine(QPointF(21, 11), QPointF(11, 21))
        else:
            p.drawLine(QPointF(11, 16), QPointF(21, 16))


class MotionIcon(QtWidgets.QWidget):
    """Person with sensor waves; turns red while motion is detected."""

    def __init__(self, width: int = 54, height: int = 46):
        super().__init__()
        self.setFixedSize(width, height)
        self.active = False

    def set_active(self, active: bool):
        self.active = active
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 48, self.height() / 40)
        main = QColor(theme.RED if self.active else "#58a6ff")
        wave = QColor(theme.RED if self.active else "#3b82c4")
        wave.setAlpha(180)
        p.setBrush(main)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(24, 8), 4, 4)
        pen = QPen(main, 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(24, 13), QPointF(24, 24))
        p.drawLine(QPointF(24, 24), QPointF(18, 35))
        p.drawLine(QPointF(24, 24), QPointF(30, 35))
        p.drawPolyline([QPointF(17, 18), QPointF(24, 15), QPointF(31, 18)])
        wave_pen = QPen(wave, 2.4)
        wave_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(wave_pen)
        for r, cx in ((8, 12), (14, 7)):
            p.drawArc(QRectF(cx - r * 0.55, 18 - r, r * 1.1, r * 2), 100 * 16, 160 * 16)
            p.drawArc(QRectF(48 - cx - r * 0.55, 18 - r, r * 1.1, r * 2), -80 * 16, 160 * 16)


class ArcGauge(QtWidgets.QWidget):
    """Arc gauge drawn over the top of a circle, like the guide's DHT gauges."""

    def __init__(self, caption: str, vmin: float, vmax: float, formatter):
        super().__init__()
        self.caption = caption
        self.vmin, self.vmax = vmin, vmax
        self.formatter = formatter
        self.value: float | None = None
        self.setMinimumSize(110, 70)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    def set_value(self, value: float):
        self.value = value
        self.update()

    def paintEvent(self, _):
        w, h = self.width(), self.height()
        # Fit the whole arc (ends dip 0.24 r below the centre) plus stroke inside the widget.
        r = max(10.0, min((w / 2 - 4) / 1.04, (h - 4) / 1.37))
        lw = max(5.0, r * 0.13)
        cx, cy = w / 2, h - 2 - 0.25 * r - lw / 2
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        start, span = 166.0, -152.0          # degrees, Qt counter-clockwise convention
        frac = 0.0 if self.value is None else max(0.0, min(1.0, (self.value - self.vmin) / (self.vmax - self.vmin)))

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QPen(QColor(143, 169, 191, 46), lw)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        p.drawArc(rect, int(start * 16), int(span * 16))

        grad = QLinearGradient(cx - r, 0, cx + r, 0)
        grad.setColorAt(0, QColor(theme.ACCENT_2))
        grad.setColorAt(1, QColor(theme.ACCENT))
        value_pen = QPen(QBrush(grad), lw)
        value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(value_pen)
        if frac > 0:
            p.drawArc(rect, int(start * 16), int(span * frac * 16))
        angle = math.radians(start + span * frac)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(cx + r * math.cos(angle), cy - r * math.sin(angle)), lw * 0.55, lw * 0.55)

        font = QFont(self.font())
        font.setPixelSize(max(10, int(r * 0.2)))
        p.setFont(font)
        p.setPen(QColor("#c9d7e3"))
        p.drawText(QRectF(0, cy - r * 0.32 - r * 0.3, w, r * 0.32), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, self.caption)
        font.setPixelSize(max(13, int(r * 0.36)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(theme.TEXT))
        text = "--" if self.value is None else self.formatter(self.value)
        p.drawText(QRectF(0, cy - r * 0.32, w, r * 0.45), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, text)


# --------------------------------------------------------------------- plots
class CompactPlotWidget(pg.PlotWidget):
    """PlotWidget's default size hint (~640x480) would starve neighbouring tiles."""

    def sizeHint(self):
        return QSize(240, 140)


def styled_plot(x_label: str, y_label: str, interactive: bool = False) -> pg.PlotWidget:
    plot = CompactPlotWidget(background=None)
    plot.setStyleSheet("background: transparent; border: none;")
    item = plot.getPlotItem()
    item.showGrid(x=True, y=True, alpha=0.15)
    label_style = {"color": theme.MUTED, "font-size": "9pt"}
    item.setLabel("bottom", x_label, **label_style)
    item.setLabel("left", y_label, **label_style)
    for name in ("left", "bottom"):
        axis = item.getAxis(name)
        axis.setPen(pg.mkPen(QColor(143, 169, 191, 110)))
        axis.setTextPen(pg.mkPen(theme.MUTED))
    item.setMouseEnabled(x=interactive, y=interactive)
    item.setMenuEnabled(interactive)
    if not interactive:
        item.hideButtons()
        plot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return plot


def filled_curve(plot: pg.PlotWidget, color: str = theme.ACCENT, fill_level: float = 0.0) -> pg.PlotDataItem:
    fill = QColor(color)
    fill.setAlpha(70)
    return plot.plot([], [], pen=pg.mkPen(color, width=2), fillLevel=fill_level, brush=QBrush(fill))


class DistancePlot(QtWidgets.QWidget):
    """Rolling 60 s ultrasonic chart with the alert threshold drawn in green."""

    def __init__(self, station: Station):
        super().__init__()
        self.station = station
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot = styled_plot("Time (s)", "Distance (cm)")
        layout.addWidget(self.plot)
        self.curve = filled_curve(self.plot)
        threshold = station.threshold
        self.plot.addItem(pg.InfiniteLine(pos=threshold, angle=0, pen=pg.mkPen(theme.GREEN, width=2)))
        self.threshold_text = pg.TextItem(f"{threshold:.0f} cm", color=theme.GREEN, anchor=(1, 1))
        self.plot.addItem(self.threshold_text)
        self.threshold_text.setPos(config.ULTRASONIC_WINDOW_S - 1, threshold)
        self.plot.setXRange(0, config.ULTRASONIC_WINDOW_S, padding=0)
        self.plot.setYRange(0, 200, padding=0)
        station.distance_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        history = self.station.distance_history
        if not history:
            return
        now = history[-1][0]
        window = config.ULTRASONIC_WINDOW_S
        xs = [window - (now - t) for t, _ in history]
        ys = [cm for _, cm in history]
        self.curve.setData(xs, ys)
        top = max(200.0, math.ceil(max(ys) / 50) * 50)
        self.plot.setYRange(0, top, padding=0)


class EnvironmentPlot(QtWidgets.QWidget):
    """Last 10 minutes of temperature (index 1) or humidity (index 2)."""

    def __init__(self, station: Station, index: int, y_label: str, min_span: float):
        super().__init__()
        self.station = station
        self.index = index
        self.min_span = min_span
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot = styled_plot("Minutes ago", y_label)
        layout.addWidget(self.plot)
        self.curve = filled_curve(self.plot)
        self.plot.setXRange(-config.DHT_HISTORY_S / 60, 0, padding=0)
        station.environment_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        history = self.station.env_history
        if not history:
            return
        now = history[-1][0]
        xs = [-(now - row[0]) / 60 for row in history]
        ys = [row[self.index] for row in history]
        lo, hi = min(ys), max(ys)
        mid, span = (lo + hi) / 2, max(self.min_span, (hi - lo) * 1.3)
        lo, hi = math.floor((mid - span / 2) * 2) / 2, math.ceil((mid + span / 2) * 2) / 2
        self.curve.setFillLevel(lo)
        self.curve.setData(xs, ys)
        self.plot.setYRange(lo, hi, padding=0)


# ------------------------------------------------------------ status views
class ClockLabel(QtWidgets.QLabel):
    def __init__(self, size: float):
        super().__init__(fmt_clock())
        font = self.font()
        font.setPointSizeF(size)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet("color: #d7e3ee;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.setText(fmt_clock()))
        self._timer.start(1000)


class ArmedWord(QtWidgets.QLabel):
    """ARMED (red, glowing) / DISARMED (amber)."""

    def __init__(self, station: Station, size: float):
        super().__init__()
        font = self.font()
        font.setPointSizeF(size)
        font.setBold(True)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._glow = glow(self, theme.RED, 26)
        station.armed_changed.connect(self.refresh)
        self.refresh(station.armed)

    def refresh(self, armed: bool):
        color = theme.RED if armed else theme.AMBER
        self.setText("ARMED" if armed else "DISARMED")
        self.setStyleSheet(f"color: {color};")
        self._glow.setColor(QColor(255, 77, 79, 200) if armed else QColor(245, 182, 56, 110))


class StatusBadge(QtWidgets.QWidget):
    """Shield icon + SECURE / ALERT / DISARMED; blinks while in ALERT."""

    COLORS = {SECURE: theme.GREEN, ALERT: theme.RED, DISARMED: theme.AMBER}

    def __init__(self, station: Station, size: float = 15, icon: int = 30):
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch(1)
        self.icon = ShieldIcon(icon)
        self.text = label("", size=size, bold=True)
        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        layout.addStretch(1)
        self._blink = QTimer(self)
        self._blink.setInterval(500)
        self._blink.timeout.connect(lambda: self.text.setVisible(not self.text.isVisible()))
        station.status_changed.connect(self.refresh)
        self.refresh(station.status)

    def refresh(self, status: str):
        self.icon.set_status(status)
        self.text.setText(status)
        self.text.setStyleSheet(f"color: {self.COLORS[status]};")
        self.text.setVisible(True)
        if status == ALERT:
            self._blink.start()
        else:
            self._blink.stop()


class PirStateView(QtWidgets.QWidget):
    """'● CLEAR' / '● MOTION' plus the PIR state description."""

    def __init__(self, station: Station, size: float = 22, icon: bool = True):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.state = label("", size=size, bold=True, align=Qt.AlignmentFlag.AlignCenter)
        self.detail = label("", align=Qt.AlignmentFlag.AlignCenter)
        self.detail.setStyleSheet("background: rgba(0,0,0,45); border-radius: 6px; padding: 4px 8px; color: #c9d7e3;")
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.state)
        layout.addWidget(self.detail)
        self.icon = None
        if icon:
            self.icon = MotionIcon()
            layout.addStretch(1)
            layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        station.motion_changed.connect(self.refresh)
        self.refresh(station.motion, station.motion_zone)

    def refresh(self, motion: bool, zone: str):
        self.state.setText("● MOTION" if motion else "● CLEAR")
        self.state.setStyleSheet(f"color: {theme.RED if motion else theme.TEXT};")
        if motion:
            self.detail.setText(f"PIR State: <span style='color:{theme.RED}'>Active</span><br>(Motion Detected: {zone})")
        else:
            self.detail.setText(f"PIR State: <span style='color:{theme.GREEN}'>Passive</span><br>(No Motion Detected)")
        if self.icon:
            self.icon.set_active(motion)


# ------------------------------------------------------------------ actions
class PasswordDialog(QtWidgets.QDialog):
    """Asks for the station password and runs `action` with it; stays open on failure."""

    def __init__(self, station: Station, action: str, title: str, parent=None):
        super().__init__(parent)
        self.station = station
        self.action = action
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label(f"{title}: password required", role="title"))
        self.field = QtWidgets.QLineEdit(echoMode=QtWidgets.QLineEdit.EchoMode.Password)
        self.field.setPlaceholderText("Station password")
        layout.addWidget(self.field)
        self.message = label("", role="msg-err")
        layout.addWidget(self.message)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setProperty("role", "ctl")
        confirm = QtWidgets.QPushButton("Confirm")
        confirm.setProperty("role", "primary")
        confirm.setDefault(True)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self._confirm)
        self.field.returnPressed.connect(self._confirm)

    def _confirm(self):
        result = self.station.perform(self.action, self.field.text(), "Desktop")
        self.field.clear()
        if result.ok:
            self.accept()
        else:
            self.message.setText(result.message)
            self.field.setFocus()


class ControlButtons(QtWidgets.QWidget):
    """[RELAY: ON/OFF] and [BUZZER TEST], both password protected."""

    def __init__(self, station: Station, big: bool = False):
        super().__init__()
        self.station = station
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24 if big else 8)
        layout.addStretch(1)
        self.relay = QtWidgets.QPushButton()
        self.buzzer = QtWidgets.QPushButton()
        for button in (self.relay, self.buzzer):
            button.setProperty("role", "ctl")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if big:
                button.setStyleSheet("font-size: 15pt; padding: 16px 26px;")
            layout.addWidget(button)
        layout.addStretch(1)
        self.relay.clicked.connect(lambda: self._ask("relay", "Toggle relay"))
        self.buzzer.clicked.connect(lambda: self._ask("buzzer", "Buzzer test"))
        station.controls_changed.connect(self.refresh)
        self.refresh(station.relay_on, station.buzzer_active)

    def _ask(self, action: str, title: str):
        PasswordDialog(self.station, action, title, self.window()).exec()

    def refresh(self, relay_on: bool, buzzer: bool):
        self.relay.setText(f"[RELAY: {'ON' if relay_on else 'OFF'}]")
        set_prop(self.relay, "state", "on" if relay_on else "")
        self.buzzer.setText("[BUZZER: ON]" if buzzer else "[BUZZER TEST]")
        set_prop(self.buzzer, "state", "ringing" if buzzer else "")


class AuthForm(QtWidgets.QWidget):
    """Password field plus ARM / DISARM button. The password is required both ways."""

    def __init__(self, station: Station, big: bool = False):
        super().__init__()
        self.station = station
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label("Enter Password:", color="#c9d7e3"))
        self.field = QtWidgets.QLineEdit(echoMode=QtWidgets.QLineEdit.EchoMode.Password)
        self.field.setPlaceholderText("••••")
        layout.addWidget(self.field)
        self.button = QtWidgets.QPushButton()
        self.button.setProperty("role", "primary")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        if big:
            self.button.setStyleSheet("font-size: 14pt; padding: 14px;")
        layout.addWidget(self.button)
        self.message = label("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self._clear = QTimer(self, singleShot=True, interval=4000)
        self._clear.timeout.connect(lambda: self.message.setText(""))

        self.button.clicked.connect(self._submit)
        self.field.returnPressed.connect(self._submit)
        station.armed_changed.connect(self.refresh)
        self.refresh(station.armed)

    def refresh(self, armed: bool):
        self.button.setText("DISARM SYSTEM" if armed else "ARM SYSTEM")

    def _submit(self):
        action = "disarm" if self.station.armed else "arm"
        result = self.station.perform(action, self.field.text(), "Desktop")
        self.field.clear()
        self.message.setText(result.message)
        set_prop(self.message, "role", "msg-ok" if result.ok else "msg-err")
        self._clear.start()


class DefaultPasswordWarning(QtWidgets.QLabel):
    def __init__(self, station: Station):
        super().__init__("⚠ Default password in use:\nrun  make set-password")
        self.setProperty("role", "warn")
        self.setWordWrap(True)
        self.station = station
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)
        self.refresh()

    def refresh(self):
        self.setVisible(self.station.passwords.is_default)


# ---------------------------------------------------------------------- logs
class PaddedDelegate(QtWidgets.QStyledItemDelegate):
    """Horizontal cell padding that keeps the full-width severity background.

    (Styling QTableWidget::item in QSS would add padding too, but it disables per-item backgrounds.)
    """

    PAD = 8

    def paint(self, painter, option, index):
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        if background is not None:
            painter.fillRect(option.rect, background)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)
        opt.rect = option.rect.adjusted(self.PAD, 0, -self.PAD, 0)
        widget = option.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width() + 2 * self.PAD, size.height())


def setup_table(table: QtWidgets.QTableWidget):
    table.setItemDelegate(PaddedDelegate(table))
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(22)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


class LogTable(QtWidgets.QTableWidget):
    """Security log table coloured by severity; follows new events live."""

    HEADERS = ["Timestamp", "Event Type", "Details"]

    def __init__(self, station: Station, limit: int = config.LOG_TABLE_ROWS):
        super().__init__(0, 4)
        self.station = station
        self.limit = limit
        self.severity: str | None = None
        setup_table(self)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.setHorizontalHeaderLabels(self.HEADERS + [""])
        station.event_logged.connect(self._on_event)
        self.reload()

    def set_severity(self, severity: str | None):
        self.severity = severity or None
        self.reload()

    def reload(self):
        events = self.station.log.recent(self.limit, self.severity)
        self.setRowCount(0)
        for event in reversed(events):
            self._insert(event)
        self._update_total()

    def _on_event(self, event: dict):
        if self.severity and event["severity"] != self.severity:
            self._update_total()
            return
        self._insert(event)
        while self.rowCount() > self.limit:
            self.removeRow(self.rowCount() - 1)
        self._update_total()

    def _insert(self, event: dict):
        self.insertRow(0)
        bg = QColor(theme.SEVERITY_BG[event["severity"]])
        values = [event["timestamp"], event["event_type"], event["details"], event["severity"]]
        for col, value in enumerate(values):
            item = QtWidgets.QTableWidgetItem(value)
            item.setBackground(bg)
            if col == 3:
                item.setForeground(QColor(theme.SEVERITY_FG[event["severity"]]))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(0, col, item)

    def _update_total(self):
        item = QtWidgets.QTableWidgetItem(f"Total Events: {self.station.log.count()}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setHorizontalHeaderItem(3, item)


def export_logs_csv(station: Station, parent: QtWidgets.QWidget):
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        parent, "Export security logs", "security_logs.csv", "CSV files (*.csv);;All files (*)")
    if not path:
        return
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(station.log.to_csv())
    except OSError as exc:
        QtWidgets.QMessageBox.warning(parent, "Export failed", str(exc))


def log_buttons(station: Station, table: LogTable, parent: QtWidgets.QWidget) -> list[QtWidgets.QPushButton]:
    refresh = QtWidgets.QPushButton("[ Refresh Logs ]")
    export = QtWidgets.QPushButton("[ Export CSV ]")
    for button in (refresh, export):
        button.setProperty("role", "ctl")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    refresh.clicked.connect(table.reload)
    export.clicked.connect(lambda: export_logs_csv(station, parent))
    return [refresh, export]
