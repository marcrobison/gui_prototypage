import unittest
from unittest import mock

from helpers import TempStation, qt_app
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from security_station.qt_ui.dashboard import DETAIL_VIEWS, MainWindow
from security_station.qt_ui.theme import STYLESHEET
from security_station.qt_ui.widgets import AuthForm, PasswordDialog


class DesktopUiTest(unittest.TestCase):
    def setUp(self):
        self.app = qt_app()
        self.app.setStyleSheet(STYLESHEET)
        self.t = TempStation()
        self.window = MainWindow(self.t.station, "https://192.168.1.10:8443")
        self.window.resize(1024, 600)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        self.dashboard = self.window.dashboard

    def tearDown(self):
        self.window.close()
        self.t.close()

    def test_footer_shows_web_url(self):
        self.assertIn("https://192.168.1.10:8443", self.dashboard.footer.text())

    def test_every_tile_expands_and_collapses(self):
        for tile in self.dashboard.tiles:
            QTest.mouseClick(tile, Qt.MouseButton.LeftButton, pos=QPoint(10, tile.height() // 2))
            self.assertEqual(self.dashboard.expanded_key, tile.key, tile.key)
            QTest.mouseClick(self.dashboard.expanded_page.back, Qt.MouseButton.LeftButton)
            self.assertIsNone(self.dashboard.expanded_key)
        self.assertEqual(set(self.dashboard.expanded_page._built), set(DETAIL_VIEWS))

    def test_escape_returns_to_dashboard(self):
        self.dashboard.expand("ultrasonic")
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertIsNone(self.dashboard.expanded_key)

    def test_clicking_button_inside_tile_does_not_expand(self):
        form = self.dashboard.user_auth.findChild(AuthForm)
        form.field.setText("wrong")
        QTest.mouseClick(form.button, Qt.MouseButton.LeftButton)
        self.assertIsNone(self.dashboard.expanded_key)
        self.assertFalse(self.t.station.armed)
        self.assertEqual(form.message.text(), "Incorrect password")

    def test_auth_form_arms_and_disarms(self):
        form = self.dashboard.user_auth.findChild(AuthForm)
        form.field.setText("1234")
        QTest.keyClick(form.field, Qt.Key.Key_Return)
        self.assertTrue(self.t.station.armed)
        self.assertEqual(form.button.text(), "DISARM SYSTEM")
        self.assertEqual(form.field.text(), "")
        form.field.setText("1234")
        form.button.click()
        self.assertFalse(self.t.station.armed)

    def test_password_dialog_for_relay(self):
        dialog = PasswordDialog(self.t.station, "relay", "Toggle relay", self.window)
        dialog.field.setText("bad")
        dialog._confirm()
        self.assertFalse(self.t.station.relay_on)
        self.assertEqual(dialog.message.text(), "Incorrect password")
        dialog.field.setText("1234")
        dialog._confirm()
        self.assertTrue(self.t.station.relay_on)

    def test_log_table_follows_new_events_and_exports(self):
        table = self.dashboard.security_logs.table
        before = table.rowCount()
        self.t.station.update_motion(True, "Zone A")  # disarmed: no log
        self.t.station.perform("arm", "1234", "Desktop")
        self.assertEqual(table.rowCount(), before + 1)
        self.assertEqual(table.item(0, 1).text(), "SYSTEM_ARMED")
        self.assertIn("Total Events", table.horizontalHeaderItem(3).text())

        out = self.t.path / "export.csv"
        with mock.patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(out), "")):
            from security_station.qt_ui.widgets import export_logs_csv
            export_logs_csv(self.t.station, self.window)
        self.assertIn("SYSTEM_ARMED", out.read_text())


if __name__ == "__main__":
    unittest.main()
