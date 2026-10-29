import fcntl
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from helpers import SCRIPTS, SKILL_ROOT, cli_env

import suggestions  # noqa: E402

KST = timezone(timedelta(hours=9))
TODAY = date(2026, 10, 29)
NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=KST)
FIXTURE = SKILL_ROOT.parent.parent / "fixtures" / "suggestions.json"


def ev(day: str, line: str, source: str = "Claude session") -> dict:
    return {"date": day, "source": source, "line": line}


ENOUGH = [ev("2026-10-27", "a"), ev("2026-10-28", "b"), ev("2026-10-28", "c")]


def record(**over) -> dict:
    base = {
        "id": "s1", "type": "new_project", "name": "Topic", "description": "old",
        "evidence": [ev("2026-10-01", "old")], "status": "pending", "neverSuggest": False,
        "createdAt": "2026-10-02T10:00:00+09:00", "updatedAt": "2026-10-02T10:00:00+09:00",
        "pendingAnswer": None, "history": [],
    }
    base.update(over)
    return base


class SuggestionsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.path = self.tmp / "suggestions.json"

    def store(self, *records):
        self.path.write_text(json.dumps({"version": 1, "suggestions": list(records)}), encoding="utf-8")

    def load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))["suggestions"]

    def propose(self, **payload):
        payload.setdefault("name", "Topic")
        payload.setdefault("description", "new")
        payload.setdefault("evidence", ENOUGH)
        return suggestions.propose(self.path, payload, TODAY, NOW)


class ProposeDecisionTest(SuggestionsCase):
    def test_creates_when_threshold_met(self):
        result = self.propose()
        self.assertEqual(result["action"], "created")
        saved = self.load()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["id"], result["id"])
        self.assertEqual(saved[0]["status"], "pending")
        self.assertEqual(saved[0]["createdAt"], "2026-10-29T12:00:00+09:00")
        self.assertEqual(saved[0]["updatedAt"], "2026-10-29T12:00:00+09:00")
        self.assertFalse(saved[0]["neverSuggest"])
        self.assertIsNone(saved[0]["pendingAnswer"])
        self.assertEqual(saved[0]["history"], [])

    def test_skips_below_threshold_without_record(self):
        result = self.propose(evidence=[ev("2026-10-27", "a"), ev("2026-10-27", "b"), ev("2026-10-27", "c")])
        self.assertEqual(result, {"action": "skipped", "id": None, "reason": "below threshold"})
        self.assertFalse(self.path.exists())

    def test_skips_when_fewer_than_three_items(self):
        result = self.propose(evidence=[ev("2026-10-27", "a"), ev("2026-10-28", "b")])
        self.assertEqual(result["reason"], "below threshold")

    def test_never_suggest_skips(self):
        self.store(record(neverSuggest=True, status="applied"))
        result = self.propose(id="s1")
        self.assertEqual(result, {"action": "skipped", "id": "s1", "reason": "never suggest"})

    def test_pending_is_updated_with_merged_evidence(self):
        self.store(record(evidence=[ev("2026-09-15", "out of window"), ev("2026-10-27", "a")]))
        result = self.propose(id="s1", evidence=[ev("2026-10-27", "a"), ev("2026-10-28", "z")], description="fresh")
        self.assertEqual(result["action"], "updated")
        saved = self.load()[0]
        self.assertEqual(saved["description"], "old")
        self.assertEqual([(e["date"], e["line"]) for e in saved["evidence"]],
                         [("2026-10-27", "a"), ("2026-10-28", "z")])
        self.assertEqual(saved["updatedAt"], "2026-10-29T12:00:00+09:00")
        self.assertEqual(saved["createdAt"], "2026-10-02T10:00:00+09:00")

    def test_answered_awaits_apply(self):
        self.store(record(status="answered", pendingAnswer={"answer": "accept", "answeredAt": "x", "description": "d"}))
        result = self.propose(id="s1")
        self.assertEqual(result, {"action": "skipped", "id": "s1", "reason": "awaiting apply"})

    def test_rejected_resuggested_with_evidence_after_rejection(self):
        history = [{"answer": "reject", "answeredAt": "2026-10-20T23:30:00+09:00", "appliedAt": "x", "result": "r"}]
        self.store(record(status="applied", history=history))
        fresh = [ev("2026-10-20", "same day"), ev("2026-10-21", "a"), ev("2026-10-22", "b"), ev("2026-10-22", "c")]
        result = self.propose(id="s1", evidence=fresh)
        self.assertEqual(result["action"], "resuggested")
        saved = self.load()[0]
        self.assertEqual(saved["status"], "pending")
        self.assertEqual([e["line"] for e in saved["evidence"]], ["a", "b", "c"])
        self.assertEqual(saved["history"], history)
        self.assertEqual(saved["updatedAt"], "2026-10-29T12:00:00+09:00")

    def test_rejected_below_threshold_after_rejection(self):
        history = [{"answer": "reject", "answeredAt": "2026-10-26T09:00:00+09:00", "appliedAt": "x", "result": "r"}]
        self.store(record(status="applied", history=history))
        before = self.path.read_bytes()
        result = self.propose(id="s1", evidence=[ev("2026-10-25", "old"), ev("2026-10-27", "a"), ev("2026-10-28", "b")])
        self.assertEqual(result, {"action": "skipped", "id": "s1", "reason": "below threshold after rejection"})
        self.assertEqual(self.path.read_bytes(), before)

    def test_rejection_day_uses_local_time_zone(self):
        history = [{"answer": "reject", "answeredAt": "2026-10-28T16:30:00Z", "appliedAt": "x", "result": "r"}]
        self.store(record(status="applied", history=history))
        fresh = [ev("2026-10-29", "same day"), ev("2026-10-30", "a"), ev("2026-10-30", "b"), ev("2026-10-31", "c")]
        with mock.patch.object(suggestions, "system_timezone", return_value=ZoneInfo("Asia/Seoul")):
            result = suggestions.propose(
                self.path, {"id": "s1", "name": "Topic", "description": "d", "evidence": fresh},
                date(2026, 10, 31), NOW)
        self.assertEqual(result["action"], "resuggested")
        self.assertEqual([e["line"] for e in self.load()[0]["evidence"]], ["a", "b", "c"])

    def test_idless_proposal_matches_name_case_insensitively(self):
        self.store(record(neverSuggest=True, status="applied", name="Work Automation"))
        before = self.path.read_bytes()
        result = self.propose(name="work automation")
        self.assertEqual(result, {"action": "skipped", "id": "s1", "reason": "never suggest"})
        self.assertEqual(self.path.read_bytes(), before)

    def test_accepted_already_accepted(self):
        history = [{"answer": "accept", "answeredAt": "2026-10-20T09:00:00+09:00", "appliedAt": "x", "result": "r"}]
        self.store(record(status="applied", history=history))
        result = self.propose(id="s1")
        self.assertEqual(result, {"action": "skipped", "id": "s1", "reason": "already accepted"})

    def test_unknown_id_raises(self):
        self.store(record())
        with self.assertRaises(suggestions.StoreError):
            self.propose(id="missing")

    def test_invalid_evidence_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.propose(evidence=[{"date": "not-a-date", "source": "s", "line": "l"}])

    def test_window_drops_old_evidence(self):
        today = date(2026, 11, 2)
        payload = {"name": "Topic", "description": "d", "evidence": [
            ev("2026-10-16", "dropped"), ev("2026-10-17", "kept1"), ev("2026-10-30", "kept2"), ev("2026-11-02", "kept3")]}
        result = suggestions.propose(self.path, payload, today, NOW)
        self.assertEqual(result["action"], "created")
        self.assertEqual([e["line"] for e in self.load()[0]["evidence"]], ["kept1", "kept2", "kept3"])


class StoreTest(SuggestionsCase):
    def test_mark_applied_moves_pending_answer(self):
        answer = {"answer": "reject", "answeredAt": "2026-10-28T09:00:00+09:00", "description": "d"}
        self.store(record(status="answered", pendingAnswer=answer))
        suggestions.mark_applied(self.path, "s1", "Recorded rejection", NOW)
        saved = self.load()[0]
        self.assertEqual(saved["status"], "applied")
        self.assertIsNone(saved["pendingAnswer"])
        self.assertEqual(saved["history"], [{
            "answer": "reject", "answeredAt": "2026-10-28T09:00:00+09:00", "description": "d",
            "appliedAt": "2026-10-29T12:00:00+09:00", "result": "Recorded rejection"}])

    def test_mark_applied_requires_answered(self):
        self.store(record())
        with self.assertRaises(suggestions.StoreError):
            suggestions.mark_applied(self.path, "s1", "r", NOW)

    def test_answered_lists_only_answered(self):
        self.store(record(), record(id="s2", status="answered", pendingAnswer={"answer": "accept"}))
        self.assertEqual([s["id"] for s in suggestions.answered(self.path)], ["s2"])

    def test_broken_file_raises_store_error(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(suggestions.StoreError):
            suggestions.list_all(self.path)

    def test_missing_file_is_empty(self):
        self.assertEqual(suggestions.list_all(self.path), [])

    def test_propose_preserves_pending_answer_written_by_app(self):
        answer = {"answer": "accept", "answeredAt": "2026-10-28T09:00:00+09:00", "description": "edited"}
        self.store(record(status="answered", pendingAnswer=answer))
        result = self.propose(id="s1")
        self.assertEqual(result["action"], "skipped")
        saved = self.load()[0]
        self.assertEqual(saved["pendingAnswer"], answer)
        self.assertEqual(saved["status"], "answered")

    def test_invalid_record_is_skipped_not_fatal(self):
        broken = [record(evidence=None), record(status="weird"), record(history="x", status="applied")]
        for bad in broken:
            with self.subTest(bad=bad):
                self.store(bad, record(id="s2", name="Other topic"))
                before = self.path.read_bytes()
                self.assertEqual(self.propose(id="s1"), {"action": "skipped", "id": "s1", "reason": "invalid record"})
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.propose(name="Other topic")["action"], "updated")

    def test_name_match_ignores_malformed_entries(self):
        self.store(42, record(name=None, id="s0"), record())
        self.assertEqual(self.propose(name="topic")["id"], "s1")

    def test_created_record_has_fixture_keys(self):
        self.propose()
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["suggestions"]
        self.assertEqual(set(self.load()[0]), set(fixture[0]))

    def test_history_entry_covers_fixture_history_keys(self):
        self.store(record(status="answered", pendingAnswer={"answer": "reject", "answeredAt": "2026-10-28T09:00:00+09:00",
                                                            "description": "d"}))
        suggestions.mark_applied(self.path, "s1", "Recorded rejection", NOW)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["suggestions"]
        fixture_keys = {k for r in fixture for h in r["history"] for k in h}
        self.assertLessEqual(fixture_keys, set(self.load()[0]["history"][0]))
        self.assertIn("description", fixture_keys)

    def test_fixture_roundtrip(self):
        records = suggestions.list_all(FIXTURE)
        self.assertEqual([r["id"] for r in records], ["fx-pending-1", "fx-answered-1", "fx-rejected-1"])


class CliTest(SuggestionsCase):
    def run_cli(self, *args, stdin="", extra_env=None):
        env = {**cli_env(self.tmp), **(extra_env or {})}
        return subprocess.run([sys.executable, str(SCRIPTS / "suggestions.py"), *args],
                              input=stdin, capture_output=True, text=True, env=env)

    def home_path(self) -> Path:
        return self.tmp / "home" / "suggestions.json"

    def test_list_and_propose_via_cli(self):
        today = datetime.now().astimezone().date()
        evidence = [ev((today - timedelta(days=d)).isoformat(), f"l{i}") for i, d in enumerate((0, 0, 1))]
        proc = self.run_cli("propose", "--json", "-",
                            stdin=json.dumps({"name": "N", "description": "D", "evidence": evidence}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["action"], "created")
        listed = json.loads(self.run_cli("list").stdout)
        self.assertEqual([s["name"] for s in listed], ["N"])

    def test_propose_invalid_json_exits_2(self):
        proc = self.run_cli("propose", "--json", "-", stdin="{bad")
        self.assertEqual(proc.returncode, 2)

    def test_propose_secret_exits_4_and_leaves_store_alone(self):
        self.home_path().parent.mkdir(parents=True)
        self.home_path().write_text(json.dumps({"version": 1, "suggestions": [record()]}), encoding="utf-8")
        before = self.home_path().read_bytes()
        payload = {"name": "Topic", "description": "uses -----BEGIN RSA PRIVATE KEY", "evidence": ENOUGH}
        proc = self.run_cli("propose", "--json", "-", stdin=json.dumps(payload))
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertIn("description", proc.stderr)
        self.assertNotIn("BEGIN RSA", proc.stderr)
        self.assertEqual(self.home_path().read_bytes(), before)

    def test_mark_applied_wrong_status_exits_2(self):
        self.home_path().parent.mkdir(parents=True)
        self.home_path().write_text(json.dumps({"version": 1, "suggestions": [record()]}), encoding="utf-8")
        proc = self.run_cli("mark-applied", "--id", "s1", "--result", "r")
        self.assertEqual(proc.returncode, 2)

    def test_mark_applied_invalid_record_exits_2_without_traceback(self):
        self.home_path().parent.mkdir(parents=True)
        bad = record(status="answered", pendingAnswer=["not", "an", "object"])
        self.home_path().write_text(json.dumps({"version": 1, "suggestions": [bad]}), encoding="utf-8")
        proc = self.run_cli("mark-applied", "--id", "s1", "--result", "r")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid record s1", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_propose_lock_timeout_leaves_file_unchanged(self):
        self.home_path().parent.mkdir(parents=True)
        self.home_path().write_text(json.dumps({"version": 1, "suggestions": [record()]}), encoding="utf-8")
        before = self.home_path().read_bytes()
        lock_path = self.home_path().with_name("suggestions.json.lock")
        with open(lock_path, "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            proc = self.run_cli("propose", "--json", "-", extra_env={"WORKLOG_LOCK_TIMEOUT": "0.2"},
                                stdin=json.dumps({"id": "s1", "name": "Topic", "description": "d", "evidence": ENOUGH}))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(self.home_path().read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
