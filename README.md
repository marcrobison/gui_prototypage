## Raspberry Pi Security Station

A PySide6 security dashboard (layout from [`docs/figures/guide.jpg`](docs/figures/guide.jpg)) that also serves
the same dashboard over HTTPS so it can be opened from a phone or laptop on the same network.
Sensor values (HC-SR04 ultrasonic, HC-SR501 PIR, DHT22) are simulated with realistic ranges.

## Requirements
 - Python 3.13 (matches Raspberry Pi OS Trixie)
 - `openssl` CLI, used once to generate the self-signed HTTPS certificate (installed by default on Pi OS)

## Setup
```bash
git clone https://github.com/marcrobison/gui_prototypage.git && cd gui_prototypage && make setup
```

## Run
```bash
make run              # desktop window + web UI
make run-fullscreen   # same, fullscreen for the Pi touchscreen (F11 toggles)
make run-headless     # web UI only, no display needed
```
The terminal (and the window footer) shows the address to open on other devices, e.g.
`https://192.168.1.42:8443`. The certificate is self-signed, so each browser asks you to accept it once.
If you type `http://` by mistake, you are redirected to `https://`.

Other options: `python main.py --help` (`--port`, `--host`, `--no-web`, `--insecure-http`).

## Password
On first start the password is **`1234`** and both UIs show a warning until you change it:
```bash
make set-password
```
The password is never stored in clear text. `data/config.json` holds a salted **scrypt** hash with file mode 600.
The running app picks up the new password without a restart.

The password is required on **every** action: arm, disarm, relay toggle and buzzer test. There are no
sessions or cookies. Failed attempts are logged as `AUTH_FAILED` (MEDIUM) with their source
(`Desktop` or `Web (<ip>)`).

## Using the dashboard
- **Click any tile** (or its ⤢ icon) to open a larger view. **← Back** or **Esc** returns to the tiles. On the
  web, the browser/phone back button also works, and each view has its own URL (`#ultrasonic`, `#logs`, …).
- Expanded views add detail:
  - Ultrasonic: min/avg/max and threshold crossings.
  - DHT: 10-minute temperature and humidity history.
  - PIR: per-zone counts and recent detections.
  - Logs: severity filter, up to 1000 rows.
- Alerts are only logged while the system is **armed**:
  - `PIR_MOTION_ALERT` (HIGH) when motion starts.
  - `ULTRASONIC_DISTANCE` (MEDIUM) when something comes closer than 30 cm.

  While an alert is active the status shows **ALERT** and the buzzer sounds.
- Logs are stored in SQLite (`data/security.db`) and capped at the 1000 most recent events.
  **Export CSV** opens a save dialog on the desktop and downloads a file on the web.
- The armed and relay states survive a restart, so cutting the power doesn't disarm the station.

## Architecture
```
main.py                       entry point (argument parsing in security_station/app.py)
security_station/
  station.py                  Station: single source of truth (state, alert logic, actions)
  simulator.py                simulated sensors feeding the Station
  auth.py, set_password.py    scrypt password store + CLI
  eventlog.py                 SQLite event log (+ persisted settings)
  network.py                  LAN IP discovery, self-signed certificate
  qt_ui/                      PySide6 desktop UI (tiles, expanded views, theme)
  web/server.py               HTTPS server (stdlib http.server on a background thread)
  web/static/                 HTML/CSS/JS dashboard (no external libraries, works offline)
tests/                        unittest suite: `make test`
```
Everything runs in one process, so the desktop and web dashboards always show the same state.
- The web server pushes live snapshots to browsers with Server-Sent Events.
- State changes requested from the web are executed on the Qt main thread.

PySide6's `QtHttpServer` binding was evaluated, but it can only return plain-text bodies. That rules out
HTML/JSON/CSV content types and custom headers, so the server uses Python's standard library instead.
No extra dependencies are needed.

## Data & reset
Runtime files live in `data/` (git-ignored): `config.json`, `security.db`, `tls/`.
`make clean` deletes them: you get the default password, an empty log and a new certificate.
