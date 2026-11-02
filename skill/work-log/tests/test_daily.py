import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers import SCRIPTS, TEST_TZ, cli_env

from daily import render_text, save, validate

NOW = datetime(2026, 11, 2, 10, 5, tzinfo=ZoneInfo(TEST_TZ))


def payload(**overrides) -> dict:
    base = {
        "date": "2026-11-02",
        "doneRange": ["2026-10-30", "2026-11-01"],
        "done": [{"project": "결제", "items": ["웹훅 재시도 PR 머지 및 dev 배포 확인 (api#1234)"]}],
        "todo": [{"project": "결제", "items": ["환불 API PR 생성"]}],
        "evidence": [{"task": "환불 API PR 생성", "reason": "Branch has 3 commits, no PR", "sources": ["git"],
                      "weak": False, "links": []}],
        "notes": ["The 10/30 log ends at 10:00"],
        "sourceStatus": {"slack": "ok", "jira": "notConfigured"},
    }
    base.update(overrides)
    return base


class RenderTest(unittest.TestCase):
    def test_korean_text(self):
        self.assertEqual(render_text(payload(), "ko"), (
            "한 일 (10/30~11/1)\n"
            "- 결제\n"
            "  - 웹훅 재시도 PR 머지 및 dev 배포 확인 (api#1234)\n"
            "\n"
            "할 일 (11/2)\n"
            "- 결제\n"
            "  - 환불 API PR 생성"
        ))

    def test_english_text_with_two_projects(self):
        p = payload(
            done=[{"project": "Payments", "items": ["Merged the webhook retry PR (api#1234)", "Designed refunds"]},
                  {"project": "Other", "items": ["Answered a data question"]}],
            todo=[{"project": "Payments", "items": ["Open the refund API PR"]}],
        )
        self.assertEqual(render_text(p, "en"), (
            "Done (10/30–11/1)\n"
            "- Payments\n"
            "  - Merged the webhook retry PR (api#1234)\n"
            "  - Designed refunds\n"
            "- Other\n"
            "  - Answered a data question\n"
            "\n"
            "To do (11/2)\n"
            "- Payments\n"
            "  - Open the refund API PR"
        ))

    def test_one_day_range_and_empty_lists(self):
        p = payload(date="2026-10-30", doneRange=["2026-10-29", "2026-10-29"], done=[], todo=[])
        self.assertEqual(render_text(p, "ko"), "한 일 (10/29)\n- (없음)\n\n할 일 (10/30)\n- (없음)")
        self.assertEqual(render_text(payload(doneRange=None, done=[]), "en").splitlines()[:2], ["Done", "- (none)"])


class FixtureTest(unittest.TestCase):
    def test_fixture_matches_what_save_writes(self):
        fixture = json.loads((Path(__file__).resolve().parents[3] / "fixtures" / "daily.json").read_text(encoding="utf-8"))
        payload = {k: v for k, v in fixture.items() if k not in ("sources", "generatedAt", "trigger", "text")}
        payload["sourceStatus"] = fixture["sources"]
        self.assertEqual(validate(payload), [])
        self.assertEqual(fixture["text"], render_text(payload, "en"))
        with tempfile.TemporaryDirectory() as tmp:
            saved = json.loads(save(payload, "app", NOW, Path(tmp), "en").read_text(encoding="utf-8"))
        self.assertEqual(sorted(saved), sorted(fixture))


class ValidateTest(unittest.TestCase):
    def test_valid_payload(self):
        self.assertEqual(validate(payload()), [])
        self.assertEqual(validate(payload(doneRange=None, sourceStatus=None)), [])

    def test_errors_name_the_field(self):
        cases = [
            (payload(date="11/2"), "date"),
            (payload(date="20261102"), "date"),
            (payload(doneRange=["2026-W44-1", "2026-11-01"]), "doneRange"),
            (payload(doneRange=["2026-10-30"]), "doneRange"),
            (payload(todo=[{"project": "결제", "items": ["ok", ""]}]), "todo[0].items[1]"),
            (payload(done=[{"items": ["x"]}]), "done[0].project"),
            (payload(evidence=[{"task": "t", "reason": "r", "sources": ["git"], "weak": "no", "links": []}]),
             "evidence[0].weak"),
            (payload(notes="one note"), "notes"),
            (payload(sourceStatus={"slack": 1}), "sourceStatus.slack"),
        ]
        for p, field in cases:
            with self.subTest(field=field):
                self.assertIn(field, " ".join(validate(p)))


class SaveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.dir = self.tmp / "dailies"

    def test_save_adds_fields_and_replaces_the_same_day(self):
        save(payload(notes=["first"]), "app", NOW, self.dir, "ko")
        path = save(payload(), "interactive", NOW, self.dir, "ko")
        self.assertEqual(path, self.dir / "2026-11-02.json")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["notes"], ["The 10/30 log ends at 10:00"])
        self.assertEqual((saved["generatedAt"], saved["trigger"]), ("2026-11-02T10:05:00+09:00", "interactive"))
        self.assertEqual(saved["sources"], {"slack": "ok", "jira": "notConfigured"})
        self.assertNotIn("sourceStatus", saved)
        self.assertTrue(saved["text"].startswith("한 일 (10/30~11/1)\n"))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["2026-11-02.json"])

    def test_files_older_than_30_days_are_removed(self):
        self.dir.mkdir()
        for name in ("2026-10-02.json", "2026-10-03.json", "last-run.json", "notes.txt"):
            (self.dir / name).write_text("{}", encoding="utf-8")
        save(payload(), "app", NOW, self.dir, "ko")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ["2026-10-03.json", "2026-11-02.json", "last-run.json", "notes.txt"])


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.env = cli_env(self.tmp)
        self.dailies = self.tmp / "home" / "dailies"

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "daily.py"), *args], capture_output=True, text=True,
                              env=self.env)

    def write_payload(self, p: dict) -> Path:
        path = self.tmp / "payload.json"
        path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        return path

    def test_save_then_show(self):
        r = self.cli("save", "--json", str(self.write_payload(payload())), "--trigger", "app")
        self.assertEqual(r.returncode, 0, r.stderr)
        shown = self.cli("show")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        # settings.json is absent, so the log language is the default (en) and headings follow it
        self.assertTrue(shown.stdout.startswith("Done (10/30–11/1)\n- 결제\n"), shown.stdout)
        self.assertEqual(os.stat(self.dailies).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.dailies / "2026-11-02.json").st_mode & 0o777, 0o600)

    def test_invalid_payload_exits_2_and_writes_nothing(self):
        r = self.cli("save", "--json", str(self.write_payload(payload(todo=[{"project": "x", "items": [3]}]))))
        self.assertEqual(r.returncode, 2)
        self.assertIn("todo[0].items[0]", r.stderr)
        self.assertFalse(self.dailies.exists())

    def test_secret_exits_4_and_writes_nothing(self):
        p = payload(notes=["see https://example.com/x?access_token=abc123"])
        r = self.cli("save", "--json", str(self.write_payload(p)))
        self.assertEqual(r.returncode, 4)
        self.assertIn("notes[0]", r.stderr)
        self.assertNotIn("abc123", r.stderr)
        self.assertFalse(self.dailies.exists())

    def test_show_without_a_daily_exits_2(self):
        self.assertEqual(self.cli("show").returncode, 2)

    def test_record_run(self):
        r = self.cli("record-run", "--started-at", "2026-11-02T10:00:00+09:00", "--ended-at",
                     "2026-11-02T10:04:00+09:00", "--result", "noOutput", "--reason", "No daily was saved")
        self.assertEqual(r.returncode, 0, r.stderr)
        record = json.loads((self.dailies / "last-run.json").read_text(encoding="utf-8"))
        self.assertEqual(record, {"startedAt": "2026-11-02T10:00:00+09:00", "endedAt": "2026-11-02T10:04:00+09:00",
                                  "trigger": "app", "result": "noOutput", "reason": "No daily was saved"})
        ok = self.cli("record-run", "--started-at", "a", "--ended-at", "b", "--result", "ok")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIsNone(json.loads((self.dailies / "last-run.json").read_text(encoding="utf-8"))["reason"])
        self.assertNotEqual(self.cli("record-run", "--started-at", "a", "--ended-at", "b", "--result", "x").returncode, 0)


if __name__ == "__main__":
    unittest.main()
