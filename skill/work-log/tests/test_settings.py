import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from helpers import SCRIPTS, cli_env

from settings import SettingsError, load_settings, set_slack


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.path = self.base / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_gives_defaults(self):
        s = load_settings(self.path)
        self.assertEqual(s.log_folder, Path.home() / "WorkLog")
        self.assertTrue(s.log_folder_is_default)
        self.assertEqual(s.log_language, "en")
        self.assertEqual(s.session_folders, [])
        self.assertEqual(s.provider, "claude")
        self.assertIsNone(s.slack_user_id)

    def test_settings_fixture_loads(self):
        fixture = Path(__file__).resolve().parents[3] / "fixtures" / "settings.json"
        s = load_settings(fixture)
        self.assertEqual(s.log_language, "ko")
        self.assertEqual(s.provider, "codex")
        self.assertEqual(s.session_folders, [Path.home() / "Projects/alpha", Path.home() / "Projects/beta"])

    def test_app_language_is_ignored_by_the_collector(self):
        self.path.write_text(json.dumps({"appLanguage": "ko", "logLanguage": "en"}), encoding="utf-8")
        self.assertEqual(load_settings(self.path).log_language, "en")

    def test_broken_file_exits_2(self):
        self.path.write_text("{broken", encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPTS / "settings.py"), "show", "--settings", str(self.path)],
                           capture_output=True, text=True, env=cli_env(self.base))
        self.assertEqual(r.returncode, 2)
        self.assertIn("settings.json", r.stderr)

    def test_invalid_language_raises(self):
        self.path.write_text(json.dumps({"logLanguage": "fr"}), encoding="utf-8")
        with self.assertRaises(SettingsError):
            load_settings(self.path)

    def test_set_slack_preserves_other_keys(self):
        self.path.write_text(json.dumps({"schedule": {"mode": "interval"}, "custom": 1}), encoding="utf-8")
        set_slack(self.path, "U1", "Name", datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["schedule"], {"mode": "interval"})
        self.assertEqual(data["custom"], 1)
        self.assertEqual(data["slack"]["userId"], "U1")
        self.assertEqual(data["slack"]["displayName"], "Name")
        self.assertEqual(load_settings(self.path).slack_user_id, "U1")

    def test_set_slack_on_a_fresh_install_never_writes_app_keys(self):
        # The app decodes a file without "version" as one it never saved, and keeps the schedule off.
        set_slack(self.path, "U1", "Name", datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(set(json.loads(self.path.read_text(encoding="utf-8"))), {"slack"})

    def test_show_says_whether_the_log_folder_is_the_default(self):
        for raw, expected in ({}, True), ({"logFolder": "~/WorkLog"}, True), ({"logFolder": "~/Notes"}, False):
            with self.subTest(raw=raw):
                self.path.write_text(json.dumps(raw), encoding="utf-8")
                r = subprocess.run([sys.executable, str(SCRIPTS / "settings.py"), "show", "--settings", str(self.path)],
                                   capture_output=True, text=True, env=cli_env(self.base))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIs(json.loads(r.stdout)["logFolderIsDefault"], expected)

    def test_log_folder_with_spaces_and_tilde(self):
        self.path.write_text(json.dumps({"logFolder": "~/Library/Mobile Documents/x y"}), encoding="utf-8")
        self.assertEqual(load_settings(self.path).log_folder, Path.home() / "Library/Mobile Documents/x y")


if __name__ == "__main__":
    unittest.main()
