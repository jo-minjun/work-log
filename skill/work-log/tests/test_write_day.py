import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from helpers import SCRIPTS, cli_env, write_settings_json

from logformat import FORMATS
from monthdoc import parse
from state import load_last, load_last_warned, load_last_written

KST = ZoneInfo("Asia/Seoul")
KO = FORMATS["ko"]
EN = FORMATS["en"]
SESSION_ITEM = {
    "source": "claude_session",
    "time": "22:43–23:50",
    "feature": "환불",
    "location": "checkout `feat/x`",
    "text": "환불 API 구현",
    "links": [{"label": "PR #1240", "url": "https://github.com/example/repo/pull/1240"}],
    "sessionId": "37fa99d1-c83d-4d68-a212-d91a62f9ca8b",
}
DECISION_ITEM = {"source": "decision", "time": "20:02", "text": "주문 목록은 내부 API로 조회 — 제안: 나, 확정: Alex"}
SLACK_ITEM = {"source": "slack", "time": "14:43", "location": "#team-channel", "text": "API 사용 문의"}


def payload(d="2026-10-29", projects=None, warnings=None):
    p = {"date": d, "projects": projects if projects is not None else [{"name": "쿠폰", "items": [SLACK_ITEM]}]}
    if warnings is not None:
        p["warnings"] = warnings
    return p


class WriteDayBase(unittest.TestCase):
    language = "ko"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.settings = write_settings_json(self.base, [], self.language)
        self.state = self.base / "state.json"
        self.month = self.base / "out" / "2026년 10월 업무 로그.md"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "write_day.py"), *args, "--settings", str(self.settings)],
            capture_output=True, text=True, input=stdin, env=cli_env(self.base),
        )

    def write_day(self, p):
        path = self.base / f"day-{p['date']}.json"
        path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        return self.run_cmd("day", "--json", str(path), "--state", str(self.state))

    def read(self):
        return self.month.read_text(encoding="utf-8")


class DayCommandTest(WriteDayBase):
    def test_creates_file_with_frontmatter(self):
        r = self.write_day(payload())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(self.month))
        text = self.read()
        self.assertTrue(text.startswith("---\ntype: Area\n"))
        for expected in ["title: 2026년 10월 업무 로그", "status: active", "  - 업무로그", "  - 커리어",
                         "year: 2026", "month: 10", "createdAt: ", "updatedAt: ",
                         "\n# 2026년 10월 업무 로그\n", "\n## 2026-10-29 (목)\n", "\n### 쿠폰\n"]:
            self.assertIn(expected, text)

    def test_groups_items_by_source_under_project(self):
        self.write_day(payload(projects=[{"name": "쿠폰", "items": [SESSION_ITEM, DECISION_ITEM, SLACK_ITEM]}]))
        self.assertIn(
            "### 쿠폰\n\n"
            "#### Claude 세션\n"
            "- `환불` 22:43–23:50 · checkout `feat/x` — 환불 API 구현 "
            "([PR #1240](https://github.com/example/repo/pull/1240))\n\n"
            "#### Slack\n"
            "- 14:43 · #team-channel — API 사용 문의\n\n"
            "#### 결정\n"
            "- 20:02 · 주문 목록은 내부 API로 조회 — 제안: 나, 확정: Alex\n", self.read())

    def test_other_project_always_last(self):
        self.write_day(payload(projects=[{"name": "기타", "items": [SLACK_ITEM]},
                                         {"name": "쿠폰", "items": [SLACK_ITEM]},
                                         {"name": "온보딩", "items": []}]))
        text = self.read()
        self.assertLess(text.index("### 쿠폰"), text.index("### 기타"))
        self.assertNotIn("### 온보딩", text)

    def test_replaces_only_target_day(self):
        self.write_day(payload("2026-10-28"))
        self.write_day(payload("2026-10-29"))
        before = parse(self.read(), KO).days[date(2026, 10, 28)]
        self.write_day(payload("2026-10-29", projects=[{"name": "기타", "items": [DECISION_ITEM]}]))
        doc = parse(self.read(), KO)
        self.assertEqual(doc.days[date(2026, 10, 28)], before)
        self.assertIn("#### 결정", doc.days[date(2026, 10, 29)])
        self.assertNotIn("#### Slack", doc.days[date(2026, 10, 29)])

    def test_inserts_in_descending_order(self):
        for d in ["2026-10-27", "2026-10-29", "2026-10-28"]:
            self.write_day(payload(d))
        text = self.read()
        positions = [text.index(f"## 2026-10-{n}") for n in (29, 28, 27)]
        self.assertEqual(positions, sorted(positions))

    def test_empty_payload_removes_section(self):
        self.write_day(payload("2026-10-28"))
        self.write_day(payload("2026-10-29"))
        self.write_day(payload("2026-10-29", projects=[]))
        text = self.read()
        self.assertNotIn("## 2026-10-29", text)
        self.assertIn("## 2026-10-28", text)

    def test_warning_only_section_is_kept(self):
        self.write_day(payload(projects=[], warnings=["Slack 수집 실패: x"]))
        self.assertIn("## 2026-10-29 (목)\n\n> Slack 수집 실패: x\n", self.read())

    def test_empty_payload_without_file_creates_nothing(self):
        r = self.write_day(payload(projects=[]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.month.exists())

    def test_invalid_payload_exit_2_and_file_untouched(self):
        self.write_day(payload())
        original = self.month.read_bytes()
        bad_items = [
            {**SLACK_ITEM, "source": "email"},
            {**SLACK_ITEM, "text": "요약\n## 2026-10-01"},
            {**SLACK_ITEM, "links": [{"label": "x", "url": "javascript:alert(1)"}]},
            {k: v for k, v in SLACK_ITEM.items() if k != "time"},
        ]
        cases = [payload(projects=[{"name": "쿠폰", "items": [item]}]) for item in bad_items]
        cases.append(payload(projects=[{"name": "쿠폰", "items": [SLACK_ITEM]},
                                       {"name": "쿠폰", "items": [SLACK_ITEM]}]))
        cases.append(payload(d="2026-13-01"))
        for case in cases:
            with self.subTest(case=case):
                r = self.write_day(case)
                self.assertEqual(r.returncode, 2)
                self.assertTrue(r.stderr.strip())
                self.assertEqual(self.month.read_bytes(), original)

    def test_updates_updated_at_keeps_created_at(self):
        self.write_day(payload())
        first = self.read()
        created = [l for l in first.splitlines() if l.startswith("createdAt:")]
        self.month.write_text(first.replace("updatedAt: ", "updatedAt: 2000-01-01T00:00:00+09:00 #"), encoding="utf-8")
        self.write_day(payload("2026-10-28"))
        second = self.read()
        self.assertEqual([l for l in second.splitlines() if l.startswith("createdAt:")], created)
        updated = [l for l in second.splitlines() if l.startswith("updatedAt:")]
        self.assertEqual(len(updated), 1)
        self.assertNotIn("2000-01-01", updated[0])

    def test_records_write_time_even_with_warnings(self):
        before = datetime.now(KST).replace(microsecond=0)
        self.write_day(payload("2026-10-20", warnings=["Slack 수집 실패: x"]))
        self.assertGreaterEqual(load_last_written(self.state), before)
        self.assertIsNone(load_last(self.state))

    def test_records_warning_time_only_with_warnings(self):
        self.write_day(payload("2026-10-28"))
        self.assertIsNone(load_last_warned(self.state))
        before = datetime.now(KST).replace(microsecond=0)
        self.write_day(payload("2026-10-29", warnings=["Slack 수집 실패: x"]))
        warned = load_last_warned(self.state)
        self.assertGreaterEqual(warned, before)
        self.write_day(payload("2026-10-29"))
        self.assertEqual(load_last_warned(self.state), warned)

    def test_marks_state_only_without_warnings(self):
        self.write_day(payload("2026-10-28", warnings=["Slack 수집 실패: x"]))
        self.assertIsNone(load_last(self.state))
        self.write_day(payload("2026-10-28"))
        self.assertEqual(load_last(self.state), date(2026, 10, 28))

    def test_unreadable_month_file_exit_3(self):
        self.write_day(payload())
        self.month.write_text(self.read() + "\n## 메모\n내용\n", encoding="utf-8")
        original = self.month.read_bytes()
        r = self.write_day(payload("2026-10-28"))
        self.assertEqual(r.returncode, 3)
        self.assertEqual(self.month.read_bytes(), original)

    def test_non_string_project_name_exit_2(self):
        r = self.write_day(payload(projects=[{"name": ["쿠폰"], "items": [SLACK_ITEM]}]))
        self.assertEqual(r.returncode, 2)
        self.assertIn("projects[0].name", r.stderr)

    def test_empty_optional_fields_are_omitted(self):
        r = self.write_day(payload(projects=[{"name": "기타", "items": [{**SLACK_ITEM, "feature": "", "sessionId": ""}]}]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("#### Slack\n- 14:43 · #team-channel — API 사용 문의\n", self.read())

    def test_broken_state_exit_2_before_writing(self):
        self.state.write_text("{broken", encoding="utf-8")
        r = self.write_day(payload())
        self.assertEqual(r.returncode, 2)
        self.assertIn("state", r.stderr)
        self.assertFalse(self.month.exists())

    def test_secret_like_values_exit_4_without_echoing_them(self):
        self.write_day(payload())
        original = self.month.read_bytes()
        cases = {
            "projects[0].items[0].text": {**SLACK_ITEM, "text": "Rotated xoxb-1234-abcd"},
            "projects[0].items[0].location": {**SLACK_ITEM, "location": "ghp_abcdefghijklmnop"},
            "projects[0].items[0].feature": {**SLACK_ITEM, "feature": "AKIAABCDEFGHIJKLMNOP"},
            "projects[0].items[0].links[0].url": {**SLACK_ITEM, "links": [
                {"label": "link", "url": "https://files.example.com/a.png?sig=abc123&x=1"}]},
            "projects[0].items[0].links[0].label": {**SLACK_ITEM, "links": [
                {"label": "eyJhbGciOi.eyJzdWIiOjF9.c2lnbmF0dXJl", "url": "https://example.com"}]},
        }
        for field, item in cases.items():
            with self.subTest(field=field):
                r = self.write_day(payload(projects=[{"name": "쿠폰", "items": [item]}]))
                self.assertEqual(r.returncode, 4, r.stderr)
                self.assertIn(field, r.stderr)
                for secret in ("xoxb-1234", "ghp_abc", "AKIAABC", "sig=abc123", "eyJhbGciOi"):
                    self.assertNotIn(secret, r.stderr)
                self.assertEqual(self.month.read_bytes(), original)
        warning = self.write_day(payload(warnings=["Slack failed: sk-abcdefghijklmnopqrstuvwx"]))
        self.assertEqual((warning.returncode, "warnings[0]" in warning.stderr), (4, True))

    def test_ordinary_urls_and_words_are_not_secrets(self):
        item = {**SLACK_ITEM, "text": "Reviewed the task-abcdefghijklmnopqrstuvwxyz ticket and the key=value doc",
                "links": [{"label": "thread", "url": "https://x.slack.com/archives/C1/p1?thread_ts=1.2&cid=C1"}]}
        r = self.write_day(payload(projects=[{"name": "기타", "items": [item]}]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_data_dir_is_created(self):
        env = {**cli_env(self.base), "WORKLOG_HOME": str(self.base / "fresh" / "data")}
        path = self.base / "day.json"
        path.write_text(json.dumps(payload(), ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPTS / "write_day.py"), "day", "--json", str(path),
                            "--settings", str(self.settings)], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(load_last(self.base / "fresh" / "data" / "state.json"), date(2026, 10, 29))

    def test_reads_payload_from_stdin(self):
        r = self.run_cmd("day", "--json", "-", "--state", str(self.state),
                         stdin=json.dumps(payload(), ensure_ascii=False))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## 2026-10-29 (목)", self.read())


class OtherCommandsTest(WriteDayBase):
    def test_others_uses_whole_current_month_even_for_backfill(self):
        self.write_day(payload("2026-10-20", projects=[{"name": "기타", "items": [SLACK_ITEM]}]))
        rows = json.loads(self.run_cmd("others", "--date", "2026-10-03").stdout)
        self.assertEqual([row["date"] for row in rows], ["2026-10-20"])

    def test_others_window_includes_last_15_days_of_previous_month(self):
        other = lambda d: payload(d, projects=[{"name": "기타", "items": [{**SLACK_ITEM, "text": f"기타 {d}"}]}])
        for d in ["2026-09-15", "2026-09-16"]:
            self.write_day(other(d))
        self.write_day(other("2026-10-03"))
        self.write_day(payload("2026-10-04"))
        r = self.run_cmd("others", "--date", "2026-10-29")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual([row["date"] for row in rows], ["2026-09-16", "2026-10-03"])
        self.assertEqual(rows[1]["source"], "Slack")
        self.assertEqual(rows[1]["line"], "- 14:43 · #team-channel — 기타 2026-10-03")

    def test_others_without_previous_month_file(self):
        self.write_day(payload("2026-10-03", projects=[{"name": "기타", "items": [SLACK_ITEM]}]))
        rows = json.loads(self.run_cmd("others", "--date", "2026-10-29").stdout)
        self.assertEqual([row["date"] for row in rows], ["2026-10-03"])


def item(text, time="10:00", source="slack"):
    base = {"source": source, "time": time, "text": text}
    if source == "slack":
        base["location"] = "#team"
    return base


class ReclassifyTest(WriteDayBase):
    other = "기타"

    def other_rows(self):
        return json.loads(self.run_cmd("others", "--date", "2026-10-29").stdout)

    def reclassify(self, project, evidence):
        path = self.base / "evidence.json"
        path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        return self.run_cmd("reclassify", "--project", project, "--json", str(path))

    def day(self, d):
        return parse(self.read(), self.fmt).days[date.fromisoformat(d)]

    @property
    def fmt(self):
        return FORMATS[self.language]

    def test_moves_only_matching_lines_and_keeps_their_subsection(self):
        self.write_day(payload("2026-10-28", projects=[{"name": self.other, "items": [
            item("keep me", "09:00"), item("move slack", "11:00"),
            item("move session", "08:00–09:00", "claude_session")]}]))
        rows = [r for r in self.other_rows() if "move" in r["line"]]
        r = self.reclassify("Checkout", rows)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"moved": 2, "missing": []})
        h = self.fmt.source_headings
        self.assertEqual(self.day("2026-10-28"),
                         f"## 2026-10-28 ({self.fmt.weekday_name(date(2026, 10, 28))})\n\n"
                         f"### Checkout\n\n#### {h['claude_session']}\n- 08:00–09:00 · move session\n\n"
                         f"#### {h['slack']}\n- 11:00 · #team — move slack\n\n"
                         f"### {self.other}\n\n#### {h['slack']}\n- 09:00 · #team — keep me")

    def test_new_section_goes_before_fallback_and_merges_in_time_order(self):
        self.write_day(payload("2026-10-29", projects=[
            {"name": "Billing", "items": [item("billing work", "10:00")]},
            {"name": "Checkout", "items": [item("early", "08:00"), item("late", "18:00")]},
            {"name": self.other, "items": [item("to billing", "12:00"), item("to new", "13:00")]}]))
        rows = self.other_rows()
        self.reclassify("Billing", [r for r in rows if "to billing" in r["line"]])
        self.reclassify("Refunds", [r for r in rows if "to new" in r["line"]])
        section = self.day("2026-10-29")
        order = [section.index(f"### {n}") for n in ("Billing", "Checkout", "Refunds")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn(f"### {self.other}", section)
        self.assertIn("- 10:00 · #team — billing work\n- 12:00 · #team — to billing", section)

    def test_missing_evidence_is_reported_and_nothing_is_written(self):
        self.write_day(payload("2026-10-29", projects=[{"name": self.other, "items": [item("present")]}]))
        before = self.read()
        evidence = [{"date": "2026-10-29", "source": "Slack", "line": "- 10:00 · #team — gone"},
                    {"date": "2026-10-27", "source": "Slack", "line": "- 10:00 · #team — no section"},
                    {"date": "2026-08-01", "source": "Slack", "line": "- no file"}]
        r = self.reclassify("Checkout", evidence)
        self.assertEqual(r.returncode, 0, r.stderr)
        result = json.loads(r.stdout)
        self.assertEqual(result["moved"], 0)
        self.assertEqual(sorted(m["date"] for m in result["missing"]), ["2026-08-01", "2026-10-27", "2026-10-29"])
        self.assertEqual(self.read(), before)

    def test_rejects_fallback_or_invalid_input(self):
        self.write_day(payload("2026-10-29", projects=[{"name": self.other, "items": [item("x")]}]))
        self.assertEqual(self.reclassify(self.other, self.other_rows()).returncode, 2)
        self.assertEqual(self.reclassify("Checkout", [{"date": "nope", "line": "x"}]).returncode, 2)
        self.assertEqual(self.reclassify("Checkout", {"date": "2026-10-29"}).returncode, 2)


class EnglishReclassifyTest(ReclassifyTest):
    language = "en"
    other = "Other"

    def setUp(self):
        super().setUp()
        self.month = self.base / "out" / "2026-10 Work Log.md"


class ProjectListTest(WriteDayBase):
    language = "en"

    def init(self):
        r = self.run_cmd("init-project-list")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_creates_heading_only_file_once(self):
        path = self.base / "out" / "Active Projects.md"
        self.assertEqual(self.init(), {"path": str(path), "created": True, "copiedFrom": None})
        self.assertEqual(path.read_text(encoding="utf-8"), "# Active Projects\n")
        path.write_text("# Active Projects\n\n## Checkout\nOrders.\n", encoding="utf-8")
        self.assertEqual(self.init()["created"], False)
        self.assertEqual(path.read_text(encoding="utf-8"), "# Active Projects\n\n## Checkout\nOrders.\n")

    def test_copies_the_other_language_list(self):
        ko = self.base / "out" / "진행 중인 프로젝트.md"
        ko.parent.mkdir(parents=True)
        ko.write_text("# 진행 중인 프로젝트\n\n## 체크아웃\n주문 API\n", encoding="utf-8")
        result = self.init()
        self.assertEqual((result["created"], result["copiedFrom"]), (True, str(ko)))
        self.assertEqual((self.base / "out" / "Active Projects.md").read_text(encoding="utf-8"), ko.read_text(encoding="utf-8"))


class MonthDocTest(unittest.TestCase):
    def test_parse_serialize_roundtrip(self):
        from monthdoc import new_doc, serialize
        doc = new_doc(date(2026, 10, 29), datetime(2026, 10, 29, 18, 0, tzinfo=KST), KO)
        doc.days[date(2026, 10, 29)] = "## 2026-10-29 (목)\n\n### 기타\n\n#### Slack\n- 10:00 · x"
        text = serialize(doc)
        self.assertEqual(serialize(parse(text, KO)), text)
        self.assertIn("createdAt: 2026-10-29T18:00:00+09:00", text)


ALL_SOURCES = [
    {**SESSION_ITEM, "source": "claude_session"},
    SLACK_ITEM,
    DECISION_ITEM,
    {"source": "needs_confirmation", "time": "09:10", "text": "unclear owner"},
]


class EnglishFormatTest(WriteDayBase):
    language = "en"

    def setUp(self):
        super().setUp()
        self.month = self.base / "out" / "2026-10 Work Log.md"

    def test_en_day_renders_exact_headings(self):
        r = self.write_day(payload(projects=[{"name": "Other", "items": ALL_SOURCES},
                                             {"name": "Ads", "items": ALL_SOURCES}]))
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.read()
        ordered = ["## 2026-10-29 (Thu)", "### Ads", "#### Claude Sessions", "#### Slack",
                   "#### Decisions", "#### Needs Confirmation", "### Other"]
        positions = [text.index(h) for h in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("\n# 2026-10 Work Log\n", text)
        self.assertIn("  - work-log\n  - career\n", text)

    def test_others_ignores_other_language_file(self):
        ko_file = self.base / "out" / "2026년 10월 업무 로그.md"
        ko_file.parent.mkdir(parents=True)
        ko_file.write_text(
            "---\ntype: Area\n---\n# t\n\n## 2026-10-02 (금)\n\n### 기타\n\n#### Slack\n- 10:00 · ko row\n",
            encoding="utf-8")
        self.write_day(payload("2026-10-03", projects=[{"name": "Other", "items": [SLACK_ITEM]}]))
        r = self.run_cmd("others", "--date", "2026-10-29")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([row["date"] for row in json.loads(r.stdout)], ["2026-10-03"])

class KoreanFormatTest(WriteDayBase):
    def test_ko_needs_confirmation_after_decisions(self):
        self.write_day(payload(projects=[{"name": "쿠폰", "items": ALL_SOURCES}]))
        text = self.read()
        self.assertLess(text.index("#### 결정"), text.index("#### 확인 필요"))

    def test_legacy_candidates_section_dropped_on_write(self):
        self.write_day(payload("2026-10-28"))
        self.month.write_text(self.read() + "\n## 새 프로젝트 후보\n\n- **A** — b\n", encoding="utf-8")
        before = parse(self.read(), KO).days[date(2026, 10, 28)]
        r = self.write_day(payload("2026-10-29"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"legacy candidates section removed from {self.month}", r.stderr)
        self.assertNotIn("새 프로젝트 후보", self.read())
        self.assertEqual(parse(self.read(), KO).days[date(2026, 10, 28)], before)

    def test_init_project_list_uses_korean_name_and_heading(self):
        r = self.run_cmd("init-project-list")
        path = self.base / "out" / "진행 중인 프로젝트.md"
        self.assertEqual(json.loads(r.stdout)["path"], str(path))
        self.assertEqual(path.read_text(encoding="utf-8"), "# 진행 중인 프로젝트\n")


if __name__ == "__main__":
    unittest.main()
