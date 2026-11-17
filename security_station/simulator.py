"""Simulated sensors producing realistic readings until real hardware is wired in.

Each `next_*` method is a pure step of its model so it can be unit-tested without timers.
"""
import random

from PySide6.QtCore import QObject, QTimer

from . import config
from .station import Station


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class UltrasonicModel:
    """HC-SR04 aimed across a room: ~120-200 cm with noise, plus occasional close approaches."""

    BASE = 160.0
    APPROACH_PROBABILITY = 1 / 90   # per 0.5 s tick, roughly one approach every 45 s

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.base = self.BASE
        self._approach: list[float] = []   # scripted samples for an ongoing approach

    def _start_approach(self, start: float):
        target = self.rng.uniform(12.0, 28.0)
        down = [start + (target - start) * i / 4 for i in range(1, 5)]
        hold = [target + self.rng.gauss(0, 1.5) for _ in range(self.rng.randint(3, 6))]
        up = [target + (self.base - target) * i / 4 for i in range(1, 5)]
        self._approach = down + hold + up

    def next(self) -> float:
        self.base += (self.BASE - self.base) * 0.08 + self.rng.gauss(0, 4.0)
        self.base = _clamp(self.base, 125.0, 195.0)
        if not self._approach and self.rng.random() < self.APPROACH_PROBABILITY:
            self._start_approach(self.base)
        if self._approach:
            value = self._approach.pop(0)
        else:
            value = self.base + self.rng.gauss(0, 5.0)
        return round(_clamp(value, 2.0, 400.0), 1)


class EnvironmentModel:
    """DHT22 indoors: slow mean-reverting drift, 0.1 resolution."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.temp_mid = 22.0
        self.hum_mid = 45.0
        self.temperature = rng.uniform(21.0, 23.5)
        self.humidity = rng.uniform(40.0, 50.0)

    def next(self) -> tuple[float, float]:
        t_lo, t_hi = config.TEMP_RANGE_C
        h_lo, h_hi = config.HUMIDITY_RANGE
        self.temp_mid = _clamp(self.temp_mid + self.rng.gauss(0, 0.03), 20.5, 23.5)
        self.hum_mid = _clamp(self.hum_mid + self.rng.gauss(0, 0.2), 40.0, 55.0)
        self.temperature += (self.temp_mid - self.temperature) * 0.05 + self.rng.gauss(0, 0.05)
        self.humidity += (self.hum_mid - self.humidity) * 0.05 + self.rng.gauss(0, 0.3)
        self.temperature = _clamp(self.temperature, t_lo, t_hi)
        self.humidity = _clamp(self.humidity, h_lo, h_hi)
        return round(self.temperature, 1), round(self.humidity, 1)


class SensorSimulator(QObject):
    def __init__(self, station: Station, rng: random.Random | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.station = station
        self.rng = rng or random.Random()
        self.ultrasonic = UltrasonicModel(self.rng)
        self.environment = EnvironmentModel(self.rng)

        self._distance_timer = QTimer(self)
        self._distance_timer.setInterval(config.ULTRASONIC_PERIOD_MS)
        self._distance_timer.timeout.connect(self._tick_distance)

        self._env_timer = QTimer(self)
        self._env_timer.setInterval(config.DHT_PERIOD_MS)
        self._env_timer.timeout.connect(self._tick_environment)

        self._pir_timer = QTimer(self)
        self._pir_timer.setSingleShot(True)
        self._pir_timer.timeout.connect(self._toggle_pir)

    def start(self):
        self._tick_distance()
        self._tick_environment()
        self._distance_timer.start()
        self._env_timer.start()
        self._schedule_pir(*config.PIR_GAP_S)

    def stop(self):
        for timer in (self._distance_timer, self._env_timer, self._pir_timer):
            timer.stop()

    def _tick_distance(self):
        self.station.update_distance(self.ultrasonic.next())

    def _tick_environment(self):
        self.station.update_environment(*self.environment.next())

    def _schedule_pir(self, lo: float, hi: float):
        self._pir_timer.start(int(self.rng.uniform(lo, hi) * 1000))

    def _toggle_pir(self):
        if self.station.motion:
            self.station.update_motion(False)
            self._schedule_pir(*config.PIR_GAP_S)
        else:
            self.station.update_motion(True, self.rng.choice(config.PIR_ZONES))
            self._schedule_pir(*config.PIR_BURST_S)
