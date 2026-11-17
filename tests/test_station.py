import random
import time
import unittest

from helpers import TempStation, qt_app

from security_station import config
from security_station.simulator import EnvironmentModel, UltrasonicModel
from security_station.station import ALERT, DISARMED, SECURE, Station


def event_types(log):
    return [e["event_type"] for e in log.recent(100)]


class StationActionsTest(unittest.TestCase):
    def setUp(self):
        self.t = TempStation()
        self.station = self.t.station

    def tearDown(self):
        self.t.close()

    def test_boot_is_logged_and_disarmed(self):
        self.assertFalse(self.station.armed)
        self.assertEqual(self.station.status, DISARMED)
        self.assertEqual(event_types(self.t.log), ["SYSTEM_STARTED"])

    def test_password_required_to_arm_and_disarm(self):
        result = self.station.perform("arm", "wrong", "Desktop")
        self.assertFalse(result.ok)
        self.assertFalse(self.station.armed)

        self.assertTrue(self.station.perform("arm", "1234", "Desktop").ok)
        self.assertTrue(self.station.armed)
        self.assertEqual(self.station.status, SECURE)

        self.assertFalse(self.station.perform("disarm", "", "Desktop").ok)
        self.assertTrue(self.station.armed)

        self.assertTrue(self.station.perform("disarm", "1234", "Desktop").ok)
        self.assertFalse(self.station.armed)
        self.assertEqual(event_types(self.t.log)[:5],
                         ["SYSTEM_DISARMED", "AUTH_FAILED", "SYSTEM_ARMED", "AUTH_FAILED", "SYSTEM_STARTED"][:5])

    def test_failed_attempt_logged_as_medium_with_source(self):
        self.station.perform("relay", "nope", "Web (192.168.1.20)")
        event = self.t.log.recent(1)[0]
        self.assertEqual(event["event_type"], "AUTH_FAILED")
        self.assertEqual(event["severity"], "MEDIUM")
        self.assertIn("relay toggle", event["details"])
        self.assertIn("192.168.1.20", event["details"])

    def test_manual_controls_need_password(self):
        self.assertFalse(self.station.perform("relay", "bad", "Desktop").ok)
        self.assertFalse(self.station.relay_on)
        self.assertTrue(self.station.perform("relay", "1234", "Desktop").ok)
        self.assertTrue(self.station.relay_on)
        self.assertTrue(self.station.perform("buzzer", "1234", "Desktop").ok)
        self.assertTrue(self.station.buzzer_active)
        self.assertIn("BUZZER_TEST", event_types(self.t.log))

    def test_unknown_action_rejected(self):
        self.assertFalse(self.station.perform("self_destruct", "1234", "Desktop").ok)

    def test_armed_and_relay_state_survive_restart(self):
        self.station.perform("arm", "1234", "Desktop")
        self.station.perform("relay", "1234", "Desktop")
        restarted = Station(self.t.passwords, self.t.log)
        self.assertTrue(restarted.armed)
        self.assertTrue(restarted.relay_on)
        self.assertEqual(restarted.status, SECURE)
        self.assertIn("(armed)", self.t.log.recent(1)[0]["details"])


class StationSensorsTest(unittest.TestCase):
    def setUp(self):
        self.t = TempStation()
        self.station = self.t.station

    def tearDown(self):
        self.t.close()

    def test_no_alerts_logged_while_disarmed(self):
        self.station.update_motion(True, "Zone A")
        self.station.update_motion(False)
        self.station.update_distance(15)
        self.assertEqual(event_types(self.t.log), ["SYSTEM_STARTED"])
        self.assertEqual(self.station.status, DISARMED)
        self.assertEqual(self.station.breaches, 1)
        self.assertEqual(self.station.zone_counts["Zone A"], 1)

    def test_pir_alert_when_armed(self):
        self.station.perform("arm", "1234", "Desktop")
        self.station.update_motion(True, "Zone B")
        event = self.t.log.recent(1)[0]
        self.assertEqual((event["event_type"], event["details"], event["severity"]),
                         ("PIR_MOTION_ALERT", "Zone B", "HIGH"))
        self.assertEqual(self.station.status, ALERT)
        self.assertTrue(self.station.buzzer_active)

    def test_distance_alert_edge_triggered_with_hysteresis(self):
        self.station.perform("arm", "1234", "Desktop")
        for cm in (150, 20, 18, 25, 35, 22):      # 35 < threshold + hysteresis: no re-trigger
            self.station.update_distance(cm)
        alerts = [e for e in self.t.log.recent(100) if e["event_type"] == "ULTRASONIC_DISTANCE"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["details"], "20 cm < 30 cm")
        self.assertEqual(alerts[0]["severity"], "MEDIUM")
        self.station.update_distance(60)
        self.station.update_distance(10)
        alerts = [e for e in self.t.log.recent(100) if e["event_type"] == "ULTRASONIC_DISTANCE"]
        self.assertEqual(len(alerts), 2)

    def test_alert_clears_after_hold(self):
        self.station.perform("arm", "1234", "Desktop")
        self.station.update_motion(True, "Zone A")
        self.station.update_motion(False)
        self.station._refresh_status()
        self.assertEqual(self.station.status, ALERT)       # still within hold time
        self.station._last_trigger = time.time() - config.ALERT_HOLD_S - 1
        self.station._refresh_status()
        self.assertEqual(self.station.status, SECURE)

    def test_disarm_clears_alert(self):
        self.station.perform("arm", "1234", "Desktop")
        self.station.update_motion(True, "Zone A")
        self.station.perform("disarm", "1234", "Desktop")
        self.assertEqual(self.station.status, DISARMED)
        self.assertFalse(self.station.buzzer_active)

    def test_histories_are_windowed(self):
        now = time.time()
        for i in range(400):
            self.station.update_distance(150, ts=now - 200 + i * 0.5)
        span = self.station.distance_history[-1][0] - self.station.distance_history[0][0]
        self.assertLessEqual(span, config.ULTRASONIC_WINDOW_S)
        for i in range(500):
            self.station.update_environment(22, 45, ts=now - 1000 + i * 2)
        span = self.station.env_history[-1][0] - self.station.env_history[0][0]
        self.assertLessEqual(span, config.DHT_HISTORY_S)

    def test_snapshot_is_json_serialisable(self):
        import json
        self.station.update_distance(120)
        self.station.update_environment(22.1, 44.0)
        self.station.update_motion(True, "Zone A")
        snap = json.loads(json.dumps(self.station.snapshot()))
        self.assertEqual(snap["distance"]["current"], 120)
        self.assertTrue(snap["pir"]["motion"])
        self.assertTrue(snap["default_password"])


class SimulatorModelTest(unittest.TestCase):
    def test_ultrasonic_stays_in_sensor_range_and_dips_below_threshold(self):
        qt_app()
        model = UltrasonicModel(random.Random(1))
        values = [model.next() for _ in range(20000)]
        self.assertTrue(all(2.0 <= v <= 400.0 for v in values))
        normal = [v for v in values if v > 60]
        self.assertGreater(sum(normal) / len(normal), 140)
        self.assertLess(sum(normal) / len(normal), 180)
        self.assertTrue(any(v < config.DISTANCE_THRESHOLD_CM for v in values))

    def test_environment_stays_realistic(self):
        model = EnvironmentModel(random.Random(2))
        readings = [model.next() for _ in range(20000)]
        temps = [t for t, _ in readings]
        hums = [h for _, h in readings]
        self.assertGreaterEqual(min(temps), config.TEMP_RANGE_C[0])
        self.assertLessEqual(max(temps), config.TEMP_RANGE_C[1])
        self.assertGreaterEqual(min(hums), config.HUMIDITY_RANGE[0])
        self.assertLessEqual(max(hums), config.HUMIDITY_RANGE[1])
        # DHT22 drifts slowly: consecutive readings never jump by more than a degree.
        self.assertLess(max(abs(a - b) for a, b in zip(temps, temps[1:])), 1.0)


if __name__ == "__main__":
    unittest.main()
