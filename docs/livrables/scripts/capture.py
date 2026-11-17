"""Takes every screenshot used in the report and the slides (Qt + web, 4 states).

Needs Playwright (`pip install playwright`) and a Chromium binary.
Usage: python capture.py <project_python> <chromium> <out_dir> <data_dir>
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

project_python, chromium, out_dir, data_dir = sys.argv[1:5]
out = Path(out_dir)
out.mkdir(parents=True, exist_ok=True)
shutil.rmtree(data_dir, ignore_errors=True)
PORT = 18443
URL = f"https://127.0.0.1:{PORT}/"
script = Path(__file__).with_name("capture_station.py")

env = {"QT_QPA_PLATFORM": "offscreen", "PATH": "/usr/bin:/bin"}
proc = subprocess.Popen([project_python, str(script), data_dir, str(PORT), str(out)],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)


def wait_for(word: str):
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("station process exited")
        if line.strip() == word:
            return


def cmd(command: str):
    proc.stdin.write(command + "\n")
    proc.stdin.flush()
    wait_for("ok")


def step(msg: str):
    print(f"[capture] {msg}", flush=True)


wait_for("ready")
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
    desk = browser.new_context(viewport={"width": 1280, "height": 760}, device_scale_factor=1.5,
                               ignore_https_errors=True)
    phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                is_mobile=True, has_touch=True, ignore_https_errors=True)
    web = desk.new_page()
    mobile = phone.new_page()

    step("1/4 startup")
    time.sleep(1.0)
    cmd("shot qt_1_demarrage")
    web.goto(URL)
    web.wait_for_timeout(1200)
    web.screenshot(path=out / "web_1_demarrage.png")

    step("2/4 normal reading (60 s of data)")
    time.sleep(55)
    cmd("badpw")
    cmd("arm")
    time.sleep(6)
    cmd("shot qt_2_normal")
    web.wait_for_timeout(500)
    web.screenshot(path=out / "web_2_normal.png")
    mobile.goto(URL)
    mobile.wait_for_timeout(1500)
    mobile.screenshot(path=out / "mobile_2_normal.png")

    step("expanded views")
    cmd("expand ultrasonic")
    cmd("shot qt_5_vue_agrandie")
    cmd("collapse")
    web.click('.tile[data-tile="environment"] .expand')
    web.wait_for_timeout(800)
    web.screenshot(path=out / "web_5_vue_agrandie.png")
    web.click("#back")
    web.wait_for_timeout(300)

    step("3/4 alarm")
    cmd("alarm")
    time.sleep(1.5)
    cmd("shot qt_3_alarme")
    web.screenshot(path=out / "web_3_alarme.png")
    mobile.screenshot(path=out / "mobile_3_alarme.png")
    cmd("resume")
    time.sleep(1)

    step("4/4 disconnection (station stopped)")
    cmd("quit")
    proc.wait(timeout=15)
    web.wait_for_timeout(4000)
    web.screenshot(path=out / "web_4_deconnexion.png")
    mobile.wait_for_timeout(500)
    mobile.screenshot(path=out / "mobile_4_deconnexion.png")
    browser.close()

step("done")
