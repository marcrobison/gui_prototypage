import http.client
import json
import socket
import ssl
import time
import unittest

from helpers import TempStation, run_with_event_loop

from security_station.network import ensure_certificate
from security_station.web.server import WebServer


class WebServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = TempStation()
        cert = ensure_certificate(cls.t.path / "cert.pem", cls.t.path / "key.pem")
        cls.server = WebServer(cls.t.station, "127.0.0.1", 0, cert)
        cls.server.start()
        cls.port = cls.server.port
        cls.ctx = ssl.create_default_context()
        cls.ctx.check_hostname = False
        cls.ctx.verify_mode = ssl.CERT_NONE

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.t.close()

    def request(self, method, path, body=None, headers=None):
        def go():
            conn = http.client.HTTPSConnection("127.0.0.1", self.port, context=self.ctx, timeout=10)
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            return resp, data
        return run_with_event_loop(go)

    def action(self, action, password):
        resp, data = self.request("POST", "/api/action", json.dumps({"action": action, "password": password}),
                                  {"Content-Type": "application/json"})
        return resp.status, json.loads(data)

    def test_serves_dashboard_with_security_headers(self):
        resp, data = self.request("GET", "/")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"ULTRASONIC DISTANCE", data)
        self.assertIn("default-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        for path in ("/static/app.js", "/static/app.css", "/favicon.svg"):
            self.assertEqual(self.request("GET", path)[0].status, 200, path)

    def test_no_path_traversal(self):
        for path in ("/static/../server.py", "/../../config.json", "/static/%2e%2e/server.py"):
            self.assertEqual(self.request("GET", path)[0].status, 404, path)

    def test_state_snapshot(self):
        resp, data = self.request("GET", "/api/state")
        snap = json.loads(data)
        self.assertIn("armed", snap)
        self.assertIn("distance", snap)

    def test_arm_disarm_over_web_requires_password(self):
        status, body = self.action("arm", "wrong")
        self.assertEqual(status, 401)
        self.assertFalse(body["ok"])
        self.assertFalse(self.t.station.armed)

        status, body = self.action("arm", "1234")
        self.assertEqual(status, 200)
        self.assertTrue(self.t.station.armed)

        status, _ = self.action("disarm", "1234")
        self.assertEqual(status, 200)
        self.assertFalse(self.t.station.armed)

        events = self.t.log.recent(5)
        self.assertEqual(events[0]["event_type"], "SYSTEM_DISARMED")
        self.assertIn("Web (127.0.0.1)", events[0]["details"])
        self.assertTrue(any(e["event_type"] == "AUTH_FAILED" for e in events))

    def test_rejects_non_json_and_bad_input(self):
        resp, _ = self.request("POST", "/api/action", "action=arm&password=1234",
                               {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(resp.status, 415)
        resp, _ = self.request("POST", "/api/action", "{not json", {"Content-Type": "application/json"})
        self.assertEqual(resp.status, 400)
        status, _ = self.action("format_disk", "1234")
        self.assertEqual(status, 400)
        resp, _ = self.request("POST", "/api/action", "x" * 10000, {"Content-Type": "application/json"})
        self.assertEqual(resp.status, 413)

    def test_logs_and_csv(self):
        self.t.log.add("PIR_MOTION_ALERT", "Zone A", "HIGH")
        resp, data = self.request("GET", "/api/logs?limit=5&severity=HIGH")
        body = json.loads(data)
        self.assertTrue(all(e["severity"] == "HIGH" for e in body["events"]))
        self.assertGreaterEqual(body["total"], 1)
        resp, data = self.request("GET", "/api/logs.csv")
        self.assertEqual(resp.status, 200)
        self.assertIn("attachment", resp.getheader("Content-Disposition"))
        self.assertTrue(data.startswith(b"id,timestamp,event_type,details,severity"))

    def test_plain_http_is_redirected_to_https(self):
        def go():
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
                s.sendall(b"GET /api/state HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % self.port)
                return s.recv(1024)
        reply = run_with_event_loop(go)
        self.assertIn(b"301", reply.split(b"\r\n")[0])
        self.assertIn(b"Location: https://127.0.0.1:%d/api/state" % self.port, reply)

    def test_event_stream_pushes_snapshots(self):
        def go():
            conn = http.client.HTTPSConnection("127.0.0.1", self.port, context=self.ctx, timeout=10)
            conn.request("GET", "/api/events")
            resp = conn.getresponse()
            self.assertEqual(resp.getheader("Content-Type"), "text/event-stream")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                line = resp.fp.readline()
                if line.startswith(b"data: "):
                    conn.close()
                    return json.loads(line[6:])
            conn.close()
        snap = run_with_event_loop(go)
        self.assertIsNotNone(snap)
        self.assertIn("status", snap)


if __name__ == "__main__":
    unittest.main()
