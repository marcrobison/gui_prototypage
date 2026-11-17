"""Paths and tunable constants shared by every part of the station."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Runtime data (password hash, SQLite log, TLS certificate) lives outside git.
DATA_DIR = Path(os.environ.get("SECURITY_STATION_DATA", PROJECT_ROOT / "data"))
CONFIG_PATH = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "security.db"
TLS_DIR = DATA_DIR / "tls"
CERT_PATH = TLS_DIR / "cert.pem"
KEY_PATH = TLS_DIR / "key.pem"

DEFAULT_PASSWORD = "1234"

# Web server
WEB_HOST = "0.0.0.0"
WEB_PORT = 8443

# Event log
LOG_CAP = 1000          # oldest rows are pruned beyond this
LOG_TABLE_ROWS = 100    # rows shown on the compact logs tile

# Ultrasonic sensor (HC-SR04: 2-400 cm range)
ULTRASONIC_PERIOD_MS = 500
ULTRASONIC_WINDOW_S = 60
DISTANCE_THRESHOLD_CM = 30.0
DISTANCE_HYSTERESIS_CM = 10.0   # must rise above threshold + this to re-trigger

# PIR sensor (HC-SR501)
PIR_GAP_S = (20.0, 90.0)        # time between motion bursts
PIR_BURST_S = (2.0, 6.0)        # how long a burst lasts
PIR_ZONES = ("Zone A", "Zone B")
PIR_HISTORY = 50                # detections kept for the expanded view

# DHT22 temperature / humidity sensor (one read every 2 s at most)
DHT_PERIOD_MS = 2000
DHT_HISTORY_S = 600
TEMP_RANGE_C = (19.0, 25.0)
HUMIDITY_RANGE = (35.0, 60.0)

# Alerts
ALERT_HOLD_S = 5.0              # status stays "ALERT" this long after the last trigger
BUZZER_TEST_S = 2.0
