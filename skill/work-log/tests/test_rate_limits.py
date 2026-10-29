import json
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers import SCRIPTS, cli_env

from rate_limits import save_from_statusline

SAVE_SH = SCRIPTS / "save_rate_limits.sh"
NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
FIVE_HOUR = {"used_percentage": 5.0, "resets_at": 1793270000}
SEVEN_DAY = {"used_percentage": 14.0, "resets_at": 1793600000}


class SaveFromStatuslineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "data" / "claude-rate-limits.json"

    def test_saves_both_windows(self):
        text = json.dumps({"model": "x", "rate_limits": {"five_hour": FIVE_HOUR, "seven_day": SEVEN_DAY}})
        self.assertTrue(save_from_statusline(text, self.path, NOW))
        self.assertEqual(json.loads(self.path.read_text()), {
            "five_hour": FIVE_HOUR,
            "seven_day": SEVEN_DAY,
            "updatedAt": "2026-10-29T12:00:00+09:00",
        })
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])

    def test_missing_window_is_null(self):
        text = json.dumps({"rate_limits": {"five_hour": FIVE_HOUR}})
        self.assertTrue(save_from_statusline(text, self.path, NOW))
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["five_hour"], FIVE_HOUR)
        self.assertIsNone(saved["seven_day"])

    def test_absent_rate_limits_keeps_previous_file(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("previous")
        self.assertFalse(save_from_statusline(json.dumps({"model": "x"}), self.path, NOW))
        self.assertEqual(self.path.read_text(), "previous")

    def test_invalid_json_returns_false(self):
        for text in ("not json", "", "[1]"):
            self.assertFalse(save_from_statusline(text, self.path, NOW))
        self.assertFalse(self.path.exists())


class SaveScriptTest(unittest.TestCase):
    def test_invalid_input_exits_zero_and_prints_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        result = subprocess.run(
            ["zsh", str(SAVE_SH)], input="not json", capture_output=True, text=True, env=cli_env(tmp),
        )
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_valid_input_writes_file_silently(self):
        tmp = Path(tempfile.mkdtemp())
        text = json.dumps({"rate_limits": {"five_hour": FIVE_HOUR}})
        result = subprocess.run(
            ["zsh", str(SAVE_SH)], input=text, capture_output=True, text=True, env=cli_env(tmp),
        )
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        saved = json.loads((tmp / "home" / "claude-rate-limits.json").read_text())
        self.assertEqual(saved["five_hour"], FIVE_HOUR)
