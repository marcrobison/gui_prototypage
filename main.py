"""Entry point: `make run` or `python main.py [--fullscreen] [--headless] [--no-web] [--port N]`."""
import sys

from security_station.app import main

if __name__ == "__main__":
    sys.exit(main())
