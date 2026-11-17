import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from security_station import config
from security_station.auth import PasswordStore
from security_station.eventlog import EventLog


class PasswordStoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_first_run_creates_default_password_hash_only(self):
        store = PasswordStore(self.path)
        self.assertTrue(store.is_default)
        self.assertTrue(store.verify(config.DEFAULT_PASSWORD))
        raw = self.path.read_text()
        self.assertNotIn(config.DEFAULT_PASSWORD, json.loads(raw)["password"]["hash"])
        record = json.loads(raw)["password"]
        self.assertEqual(record["algo"], "scrypt")
        self.assertEqual(len(bytes.fromhex(record["salt"])), 16)

    def test_config_file_is_private(self):
        PasswordStore(self.path)
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)

    def test_wrong_and_empty_passwords_rejected(self):
        store = PasswordStore(self.path)
        for bad in ("", "12345", "123", None, 1234):
            self.assertFalse(store.verify(bad), bad)

    def test_set_password_replaces_default_and_reloads_elsewhere(self):
        store = PasswordStore(self.path)
        other = PasswordStore(self.path)          # e.g. the running app
        store.set_password("correct horse")
        self.assertFalse(store.is_default)
        self.assertTrue(store.verify("correct horse"))
        self.assertFalse(store.verify(config.DEFAULT_PASSWORD))
        self.assertTrue(other.verify("correct horse"))  # picked up via mtime check
        self.assertFalse(other.is_default)

    def test_same_password_gets_different_salt(self):
        a = PasswordStore(self.path)
        a.set_password("abcd")
        first = json.loads(self.path.read_text())["password"]
        a.set_password("abcd")
        second = json.loads(self.path.read_text())["password"]
        self.assertNotEqual(first["salt"], second["salt"])
        self.assertNotEqual(first["hash"], second["hash"])


class EventLogTest(unittest.TestCase):
    def setUp(self):
        self.log = EventLog(":memory:", cap=10)

    def tearDown(self):
        self.log.close()

    def test_add_and_recent_newest_first(self):
        self.log.add("A", "first", "INFO")
        self.log.add("B", "second", "HIGH")
        events = self.log.recent()
        self.assertEqual([e["event_type"] for e in events], ["B", "A"])
        self.assertEqual(events[0]["severity"], "HIGH")
        self.assertRegex(events[0]["timestamp"], r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d")

    def test_cap_prunes_oldest(self):
        for i in range(25):
            self.log.add("E", str(i), "INFO")
        self.assertEqual(self.log.count(), 10)
        details = [e["details"] for e in self.log.recent(100)]
        self.assertEqual(details, [str(i) for i in range(24, 14, -1)])

    def test_severity_filter_and_validation(self):
        self.log.add("A", "x", "INFO")
        self.log.add("B", "y", "MEDIUM")
        self.assertEqual([e["event_type"] for e in self.log.recent(severity="MEDIUM")], ["B"])
        with self.assertRaises(ValueError):
            self.log.add("C", "z", "CRITICAL")

    def test_csv_export(self):
        self.log.add("PIR_MOTION_ALERT", "Zone, A", "HIGH")
        lines = self.log.to_csv().strip().splitlines()
        self.assertEqual(lines[0], "id,timestamp,event_type,details,severity")
        self.assertIn('"Zone, A"', lines[1])

    def test_settings_roundtrip(self):
        self.assertIsNone(self.log.get_setting("armed"))
        self.log.set_setting("armed", "1")
        self.log.set_setting("armed", "0")
        self.assertEqual(self.log.get_setting("armed"), "0")


if __name__ == "__main__":
    unittest.main()
