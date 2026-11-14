# assign python3 to PY unless explicitly assigned otherwise by the shell
PY ?= python3

.PHONY: setup freeze clean

# Checks python version and creates virtual environment
setup:
	$(PY) -c 'import sys; assert sys.version_info[:2] == (3,13), "needs python 3.13"'
	$(PY) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

freeze:
	.venv/bin/pip freeze > requirements.txt
	
	
run:
	.venv/bin/python3 main.py
