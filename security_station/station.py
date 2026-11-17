"""The single source of truth for the station.

`Station` lives on the Qt main thread. The desktop widgets connect to its signals.
The web server reads `snapshot()` and asks for actions through `perform()`/`apply()`,
which it always runs on the main thread (see web/server.py).
"""
import time
from collections import deque
from typing import NamedTuple

from PySide6.QtCore import QObject, QTimer, Signal

from . import config
from .auth import PasswordStore
from .eventlog import EventLog

ACTIONS = {
    "arm": "arm",
    "disarm": "disarm",
    "relay": "relay toggle",
    "buzzer": "buzzer test",
}

SECURE, ALERT, DISARMED = "SECURE", "ALERT", "DISARMED"


class ActionResult(NamedTuple):
    ok: bool
    message: str


class Station(QObject):
    armed_changed = Signal(bool)
    status_changed = Signal(str)
    distance_changed = Signal(float)
    motion_changed = Signal(bool, str)
    environment_changed = Signal(float, float)
    controls_changed = Signal(bool, bool)   # relay_on, buzzer_active
    event_logged = Signal(dict)
    changed = Signal()                       # anything at all (drives web publishing)

    def __init__(self, passwords: PasswordStore, log: EventLog, parent: QObject | None = None):
        super().__init__(parent)
        self.passwords = passwords
        self.log = log
        self.started_at = time.time()

        # Restored from the database so a power cycle can't be used to disarm the station.
        self.armed = log.get_setting("armed") == "1"
        self.relay_on = log.get_setting("relay") == "1"
        self._buzzer_test = False

        self.distance: float | None = None
        self.distance_history: deque[tuple[float, float]] = deque()
        self.threshold = config.DISTANCE_THRESHOLD_CM
        self.breaches = 0
        self._below = False

        self.motion = False
        self.motion_zone = ""
        self.detections: deque[dict] = deque(maxlen=config.PIR_HISTORY)
        self.zone_counts = {z: 0 for z in config.PIR_ZONES}

        self.temperature: float | None = None
        self.humidity: float | None = None
        self.env_history: deque[tuple[float, float, float]] = deque()

        self.status = SECURE if self.armed else DISARMED
        self._trigger_active = False
        self._last_trigger = 0.0
        self._log_version = 0

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(500)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        self._log("SYSTEM_STARTED", f"Security station booted ({'armed' if self.armed else 'disarmed'})", "INFO")

    # ------------------------------------------------------------------ actions
    @property
    def buzzer_active(self) -> bool:
        return self._buzzer_test or self.status == ALERT

    def perform(self, action: str, password: str, source: str) -> ActionResult:
        """Verify the password and run an action. Main thread only."""
        if action not in ACTIONS:
            return ActionResult(False, "Unknown action")
        if not self.passwords.verify(password):
            return self.reject(action, source)
        return self.apply(action, source)

    def reject(self, action: str, source: str) -> ActionResult:
        self._log("AUTH_FAILED", f"Failed {ACTIONS.get(action, action)} attempt via {source}", "MEDIUM")
        return ActionResult(False, "Incorrect password")

    def apply(self, action: str, source: str) -> ActionResult:
        """Run an already-authorised action. Main thread only."""
        if action == "arm":
            if self.armed:
                return ActionResult(True, "System already armed")
            self._set_armed(True)
            self._log("SYSTEM_ARMED", f"via {source}", "INFO")
            return ActionResult(True, "System armed")
        if action == "disarm":
            if not self.armed:
                return ActionResult(True, "System already disarmed")
            self._set_armed(False)
            self._log("SYSTEM_DISARMED", f"via {source}", "INFO")
            return ActionResult(True, "System disarmed")
        if action == "relay":
            self.relay_on = not self.relay_on
            self.log.set_setting("relay", "1" if self.relay_on else "0")
            self._log("RELAY_ON" if self.relay_on else "RELAY_OFF", f"via {source}", "INFO")
            self._emit_controls()
            return ActionResult(True, f"Relay {'ON' if self.relay_on else 'OFF'}")
        if action == "buzzer":
            self._buzzer_test = True
            self._log("BUZZER_TEST", f"via {source}", "INFO")
            self._emit_controls()
            QTimer.singleShot(int(config.BUZZER_TEST_S * 1000), self._end_buzzer_test)
            return ActionResult(True, "Buzzer test running")
        return ActionResult(False, "Unknown action")

    def _end_buzzer_test(self):
        self._buzzer_test = False
        self._emit_controls()

    def _set_armed(self, armed: bool):
        self.armed = armed
        self.log.set_setting("armed", "1" if armed else "0")
        self._trigger_active = False
        self._last_trigger = 0.0
        self.armed_changed.emit(armed)
        self._refresh_status()
        self.changed.emit()

    def _emit_controls(self):
        self.controls_changed.emit(self.relay_on, self.buzzer_active)
        self.changed.emit()

    # ------------------------------------------------------------ sensor input
    def update_distance(self, cm: float, ts: float | None = None):
        ts = time.time() if ts is None else ts
        self.distance = cm
        self.distance_history.append((ts, cm))
        while self.distance_history and ts - self.distance_history[0][0] > config.ULTRASONIC_WINDOW_S:
            self.distance_history.popleft()

        if not self._below and cm < self.threshold:
            self._below = True
            self.breaches += 1
            if self.armed:
                self._log("ULTRASONIC_DISTANCE", f"{cm:.0f} cm < {self.threshold:.0f} cm", "MEDIUM")
                self._trigger(ts)
        elif self._below and cm > self.threshold + config.DISTANCE_HYSTERESIS_CM:
            self._below = False

        self.distance_changed.emit(cm)
        self.changed.emit()

    def update_motion(self, motion: bool, zone: str = "", ts: float | None = None):
        ts = time.time() if ts is None else ts
        if motion == self.motion:
            return
        self.motion = motion
        if motion:
            self.motion_zone = zone
            self.zone_counts[zone] = self.zone_counts.get(zone, 0) + 1
            self.detections.appendleft({"ts": ts, "zone": zone, "duration": None, "armed": self.armed})
            if self.armed:
                self._log("PIR_MOTION_ALERT", zone, "HIGH")
                self._trigger(ts)
        else:
            if self.detections and self.detections[0]["duration"] is None:
                self.detections[0]["duration"] = round(ts - self.detections[0]["ts"], 1)
        self.motion_changed.emit(self.motion, self.motion_zone)
        self.changed.emit()

    def update_environment(self, temperature: float, humidity: float, ts: float | None = None):
        ts = time.time() if ts is None else ts
        self.temperature = temperature
        self.humidity = humidity
        self.env_history.append((ts, temperature, humidity))
        while self.env_history and ts - self.env_history[0][0] > config.DHT_HISTORY_S:
            self.env_history.popleft()
        self.environment_changed.emit(temperature, humidity)
        self.changed.emit()

    # ------------------------------------------------------------------ status
    def _trigger(self, ts: float):
        self._trigger_active = True
        self._last_trigger = ts
        self._refresh_status()

    def _refresh_status(self):
        now = time.time()
        if self._trigger_active and not (self.motion or self._below):
            self._trigger_active = False
            self._last_trigger = now
        if not self.armed:
            status = DISARMED
        elif self._trigger_active or now - self._last_trigger < config.ALERT_HOLD_S:
            status = ALERT
        else:
            status = SECURE
        if status != self.status:
            self.status = status
            self.status_changed.emit(status)
            self._emit_controls()

    # -------------------------------------------------------------------- logs
    def _log(self, event_type: str, details: str, severity: str):
        row = self.log.add(event_type, details, severity)
        self._log_version += 1
        self.event_logged.emit(row)
        self.changed.emit()

    def distance_stats(self) -> dict:
        values = [cm for _, cm in self.distance_history]
        if not values:
            return {"min": None, "avg": None, "max": None}
        return {"min": min(values), "avg": round(sum(values) / len(values), 1), "max": max(values)}

    def snapshot(self) -> dict:
        """JSON-serialisable view of everything a client needs to render."""
        return {
            "server_time": time.time(),
            "started_at": self.started_at,
            "armed": self.armed,
            "status": self.status,
            "default_password": self.passwords.is_default,
            "distance": {
                "current": self.distance,
                "threshold": self.threshold,
                "window": config.ULTRASONIC_WINDOW_S,
                "history": [[round(t, 2), cm] for t, cm in self.distance_history],
                "stats": self.distance_stats(),
                "breaches": self.breaches,
            },
            "pir": {
                "motion": self.motion,
                "zone": self.motion_zone,
                "detections": list(self.detections),
                "counts": dict(self.zone_counts),
            },
            "env": {
                "temperature": self.temperature,
                "humidity": self.humidity,
                "temp_range": config.TEMP_RANGE_C,
                "humidity_range": config.HUMIDITY_RANGE,
                "history": [[round(t, 1), te, hu] for t, te, hu in self.env_history],
            },
            "controls": {"relay": self.relay_on, "buzzer": self.buzzer_active},
            "logs": {"total": self.log.count(), "version": self._log_version},
        }
