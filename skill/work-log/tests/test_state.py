import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from unittest import mock

from helpers import SCRIPTS, cli_env, make_settings, write_settings_json

from settings import load_settings
from write_day import month_file
from state import load_last, load_last_written, mark_complete, record_write, resolve_dates

TODAY = date(2026, 10, 29)


class ResolveDatesTest(unittest.TestCase):
    def test_dates_default_without_state(self):
        self.assertEqual(resolve_dates(None, None, TODAY), [TODAY])

    def test_dates_empty_string_is_default(self):
        self.assertEqual(resolve_dates("", None, TODAY), [TODAY])

    def test_dates_default_starts_after_last_completed_day(self):
        self.assertEqual(resolve_dates(None, date(2026, 10, 27), TODAY), [date(2026, 10, 28), TODAY])
        self.assertEqual(resolve_dates(None, date(2026, 10, 28), TODAY), [TODAY])

    def test_dates_default_refreshes_today_when_today_is_done(self):
        self.assertEqual(resolve_dates("", TODAY, TODAY), [TODAY])

    def test_dates_single(self):
        self.assertEqual(resolve_dates("2026-10-22", TODAY, TODAY), [date(2026, 10, 22)])

    def test_dates_range_inclusive(self):
        dates = resolve_dates("2026-10-23..2026-10-29", None, TODAY)
        self.assertEqual(len(dates), 7)
        self.assertEqual((dates[0], dates[-1]), (date(2026, 10, 23), TODAY))

    def test_dates_invalid(self):
        for arg in ["2026-10-30", "2026-10-29..2026-10-23", "10/22", "2026-10-01..2026-10-31"]:
            with self.subTest(arg=arg), self.assertRaises(ValueError):
                resolve_dates(arg, None, TODAY)

    def test_cli_prints_dates_and_rejects_invalid(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        env = cli_env(base)
        ok = subprocess.run(
            [sys.executable, str(SCRIPTS / "state.py"), "dates", "2026-10-27..2026-10-28"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout.split(), ["2026-10-27", "2026-10-28"])
        bad = subprocess.run(
            [sys.executable, str(SCRIPTS / "state.py"), "dates", "nope"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(bad.returncode, 2)


class BrokenStateTest(unittest.TestCase):
    def test_cli_broken_state_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text("{broken", encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "state.py"), "dates", "--state", str(state)],
                               capture_output=True, text=True, env=cli_env(Path(tmp)))
            self.assertEqual(r.returncode, 2)
            self.assertIn("state.json", r.stderr)


class MarkCompleteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _set_last(self, d: date):
        self.path.write_text(json.dumps({"lastCompletedDate": d.isoformat()}), encoding="utf-8")

    def test_mark_complete_first_time(self):
        mark_complete(self.path, date(2026, 10, 28))
        self.assertEqual(load_last(self.path), date(2026, 10, 28))

    def test_mark_complete_contiguous_advances(self):
        self._set_last(date(2026, 10, 27))
        mark_complete(self.path, date(2026, 10, 28))
        self.assertEqual(load_last(self.path), date(2026, 10, 28))

    def test_mark_complete_gap_does_not_advance(self):
        self._set_last(date(2026, 10, 27))
        mark_complete(self.path, date(2026, 10, 29))
        self.assertEqual(load_last(self.path), date(2026, 10, 27))

    def test_mark_complete_backfill_does_not_regress(self):
        self._set_last(date(2026, 10, 29))
        mark_complete(self.path, date(2026, 10, 22))
        self.assertEqual(load_last(self.path), date(2026, 10, 29))

    def test_record_write_and_mark_complete_keep_each_other(self):
        written = datetime(2026, 10, 29, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        mark_complete(self.path, date(2026, 10, 28))
        record_write(self.path, written)
        mark_complete(self.path, date(2026, 10, 29))
        self.assertEqual(load_last(self.path), date(2026, 10, 29))
        self.assertEqual(load_last_written(self.path), written)

    def test_load_last_written_missing(self):
        self.assertIsNone(load_last_written(self.path))
        mark_complete(self.path, date(2026, 10, 28))
        self.assertIsNone(load_last_written(self.path))

    def test_load_last_missing_file(self):
        self.assertIsNone(load_last(self.path))


class SettingsTest(unittest.TestCase):
    def test_month_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_settings(Path(tmp), [])
            self.assertEqual(month_file(cfg, date(2026, 3, 5)).name, "2026년 03월 업무 로그.md")

    def test_load_settings_expands_paths(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {"TZ": "Asia/Seoul"}):
            path = write_settings_json(Path(tmp), [Path("~/Projects/work")])
            settings = load_settings(path)
            self.assertEqual(settings.session_folders, [Path.home() / "Projects/work"])
            self.assertEqual(settings.log_folder, Path(tmp) / "out")
            self.assertEqual(str(settings.tz), "Asia/Seoul")


if __name__ == "__main__":
    unittest.main()
