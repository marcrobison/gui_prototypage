# assign python3 to PY unless explicitly assigned otherwise by the shell
PY ?= python3
VENV_PY = .venv/bin/python3

.PHONY: setup freeze run run-fullscreen run-headless set-password test clean

# Checks python version and creates virtual environment
setup:
	$(PY) -c 'import sys; assert sys.version_info[:2] == (3,13), "needs python 3.13"'
	$(PY) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

freeze:
	.venv/bin/pip freeze > requirements.txt

# Desktop window + web UI on https://<lan-ip>:8443
run:
	$(VENV_PY) main.py

# Pi touchscreen
run-fullscreen:
	$(VENV_PY) main.py --fullscreen

# Web UI only (no display needed)
run-headless:
	$(VENV_PY) main.py --headless

# Store a new station password (salted scrypt hash in data/config.json)
set-password:
	$(VENV_PY) -m security_station.set_password

test:
	QT_QPA_PLATFORM=offscreen $(VENV_PY) -m unittest discover -s tests -v

# Removes runtime data: event log, password hash, TLS certificate
clean:
	rm -rf data __pycache__ security_station/__pycache__
