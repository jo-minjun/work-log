import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from helpers import SCRIPTS, TEST_TZ, cli_env, make_settings, write_settings_json

from daily_context import (GhAccounts, build, done_range, github_context, local_git_context, open_questions,
                           previous_daily, read_sections)
from logformat import FORMATS
from monthdoc import new_doc, serialize
from settings import DailySettings

KO = FORMATS["ko"]
SINCE = datetime(2026, 10, 30, tzinfo=ZoneInfo(TEST_TZ))
TODAY = date(2026, 11, 2)


def pr(repo: str, number: int, updated: str = "2026-11-01T09:00:00Z") -> dict:
    return {"repository": {"name": repo.split("/")[1], "nameWithOwner": repo}, "number": number,
            "title": f"PR {number}", "url": f"https://github.com/{repo}/pull/{number}", "updatedAt": updated}


class FakeGh:
    """Stands in for the gh CLI and records each call; git and everything else run for real."""

    def __init__(self, tokens: dict, searches: dict | None = None, pr_lists: dict | None = None):
        self.tokens = tokens
        self.searches = searches or {}
        self.pr_lists = pr_lists or {}
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, args, **kwargs):
        if args[0] != "gh":
            return subprocess.run(args, **kwargs)
        token = (kwargs.get("env") or {}).get("GH_TOKEN")
        self.calls.append((list(args), token))
        if args[1:3] == ["auth", "token"]:
            account = args[args.index("--user") + 1]
            if account not in self.tokens:
                return subprocess.CompletedProcess(args, 1, "", f"no oauth token found for {account}\n")
            return subprocess.CompletedProcess(args, 0, self.tokens[account] + "\n", "")
        if args[1:3] == ["search", "prs"]:
            kind = [a for a in args[3:args.index("--json")] if not a.startswith("--owner") and a != "--state=open"][-1]
            return subprocess.CompletedProcess(args, 0, json.dumps(self.searches.get((token, kind), [])), "")
        if args[1:3] == ["pr", "list"]:
            key = (token, Path(kwargs["cwd"]).name)
            if key not in self.pr_lists:
                return subprocess.CompletedProcess(args, 1, "", "Could not resolve to a Repository\n")
            return subprocess.CompletedProcess(args, 0, json.dumps(self.pr_lists[key]), "")
        raise AssertionError(f"unexpected gh call: {args}")


def month_text(days: dict[date, str]) -> str:
    first = min(days)
    doc = new_doc(first, datetime(2026, 10, 1, 9, 0), KO)
    for d, body in days.items():
        doc.days[d] = f"{KO.day_heading(d)}\n\n{body}"
    return serialize(doc)


class DoneRangeTest(unittest.TestCase):
    def test_ranges(self):
        cases = [
            ("monday after a weekend", date(2026, 11, 2), [date(2026, 10, 29), date(2026, 10, 30), date(2026, 11, 1)],
             (date(2026, 10, 30), date(2026, 11, 1))),
            ("friday", date(2026, 10, 30), [date(2026, 10, 28), date(2026, 10, 29)],
             (date(2026, 10, 29), date(2026, 10, 29))),
            ("tuesday after a quiet weekend", date(2026, 10, 27), [date(2026, 10, 23), date(2026, 10, 26)],
             (date(2026, 10, 26), date(2026, 10, 26))),
            ("back from a long break", date(2026, 10, 26), [date(2026, 10, 14)],
             (date(2026, 10, 14), date(2026, 10, 25))),
            ("only weekend work", date(2026, 11, 2), [date(2026, 11, 1)], (date(2026, 11, 1), date(2026, 11, 1))),
        ]
        for name, today, days, expected in cases:
            with self.subTest(name):
                self.assertEqual(done_range(set(days), today), expected)

    def test_a_later_daily_moves_the_start(self):
        days = {date(2026, 10, 29), date(2026, 10, 30)}
        # Monday's stand-up was saved but Monday was never collected: Friday must not come back on Tuesday
        self.assertEqual(done_range(days, date(2026, 11, 3), date(2026, 11, 2)), (date(2026, 11, 2), date(2026, 11, 2)))
        self.assertEqual(done_range(days, date(2026, 11, 3), date(2026, 10, 29)), (date(2026, 10, 30), date(2026, 11, 2)))

    def test_previous_daily_is_the_newest_before_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            dailies = Path(tmp)
            self.assertIsNone(previous_daily(dailies / "missing", TODAY))
            for name in ("2026-10-29.json", "2026-10-30.json", "2026-11-02.json", "last-run.json"):
                (dailies / name).write_text("{}", encoding="utf-8")
            self.assertEqual(previous_daily(dailies, TODAY), date(2026, 10, 30))

    def test_no_section_in_three_weeks_gives_none(self):
        self.assertIsNone(done_range({date(2026, 10, 11)}, date(2026, 11, 2)))
        self.assertIsNone(done_range({date(2026, 11, 2)}, date(2026, 11, 2)))


class LogSectionsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.settings = make_settings(self.tmp, [])
        self.settings.log_folder.mkdir()

    def write_month(self, d: date, days: dict[date, str]) -> None:
        (self.settings.log_folder / KO.month_file_name(d)).write_text(month_text(days), encoding="utf-8")

    def test_both_month_files_are_read(self):
        self.write_month(date(2026, 10, 1), {date(2026, 10, 30): "### 결제\n\n#### Claude 세션\n- 10:00 · a"})
        self.write_month(date(2026, 11, 1), {date(2026, 11, 1): "### 결제\n\n#### Slack\n- 11:00 · b"})
        sections, errors = read_sections(self.settings, date(2026, 11, 2))
        self.assertEqual(sorted(sections), [date(2026, 10, 30), date(2026, 11, 1)])
        self.assertEqual(errors, {})

    def test_broken_month_file_is_reported_and_the_other_still_read(self):
        (self.settings.log_folder / KO.month_file_name(date(2026, 10, 1))).write_text("no frontmatter", encoding="utf-8")
        self.write_month(date(2026, 11, 1), {date(2026, 11, 1): "### 결제\n\n#### Slack\n- 11:00 · b"})
        sections, errors = read_sections(self.settings, date(2026, 11, 2))
        self.assertEqual(list(sections), [date(2026, 11, 1)])
        self.assertEqual(list(errors), ["2026년 10월 업무 로그.md"])

    def test_open_questions_from_the_last_14_days(self):
        sections = {
            date(2026, 10, 29): f"{KO.day_heading(date(2026, 10, 29))}\n\n### 결제\n\n#### 확인 필요\n- 22:00 · 환불 기준 확인 대기",
            date(2026, 10, 19): f"{KO.day_heading(date(2026, 10, 19))}\n\n### 결제\n\n#### 확인 필요\n- 09:00 · 오래된 질문",
            date(2026, 10, 20): f"{KO.day_heading(date(2026, 10, 20))}\n\n### 결제\n\n#### 확인 필요\n- 09:00 · 14일째 질문",
            date(2026, 10, 30): f"{KO.day_heading(date(2026, 10, 30))}\n\n### 기타\n\n#### Slack\n- 10:00 · 확인 필요 아님",
        }
        self.assertEqual(open_questions(sections, KO, date(2026, 11, 2)),
                         [{"date": "2026-10-20", "project": "결제", "text": "09:00 · 14일째 질문"},
                          {"date": "2026-10-29", "project": "결제", "text": "22:00 · 환불 기준 확인 대기"}])


class GithubTest(unittest.TestCase):
    def test_each_account_uses_its_own_token_and_owner_filters(self):
        fake = FakeGh(
            {"work": "token-w", "side": "token-s"},
            {
                ("token-w", "--author=@me"): [pr("acme/api", 1), pr("acme/api", 1)],
                ("token-s", "--author=@me"): [pr("side/app", 7)],
                ("token-w", "--merged-at=>=2026-10-30T00:00:00+09:00"): [pr("acme/api", 2)],
                ("token-w", "user-review-requested:@me"): [pr("acme/web", 3, "2026-09-01T00:00:00Z")],
                ("token-w", "--review-requested=@me"): [
                    pr("acme/web", 3, "2026-09-01T00:00:00Z"),
                    pr("acme/web", 4, "2026-10-25T00:00:00Z"),
                    pr("acme/web", 5, "2026-10-10T00:00:00Z"),
                ],
            },
        )
        result = github_context(GhAccounts(["work", "side"], fake), ["acme", "acme-labs"],
                                SINCE, TODAY)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([p["url"] for p in result["authoredOpen"]],
                         ["https://github.com/acme/api/pull/1", "https://github.com/side/app/pull/7"])
        self.assertEqual([p["number"] for p in result["mergedInRange"]], [2])
        self.assertEqual([(p["number"], p["team"]) for p in result["reviewRequested"]], [(3, False), (4, True)])
        searches = [(args, token) for args, token in fake.calls if args[1:3] == ["search", "prs"]]
        self.assertTrue(searches)
        for args, token in searches:
            self.assertIn(token, ("token-w", "token-s"))
            self.assertIn("--owner=acme", args)
            self.assertIn("--owner=acme-labs", args)
        self.assertEqual(sum(1 for args, _ in fake.calls if args[1:3] == ["auth", "token"]), 2)

    def test_a_direct_request_in_one_account_wins_over_a_team_request_in_another(self):
        fake = FakeGh(
            {"a": "token-a", "b": "token-b"},
            {
                ("token-a", "--review-requested=@me"): [pr("acme/web", 4, "2026-10-31T00:00:00Z")],
                ("token-b", "user-review-requested:@me"): [pr("acme/web", 4, "2026-10-31T00:00:00Z")],
                ("token-b", "--review-requested=@me"): [pr("acme/web", 4, "2026-10-31T00:00:00Z")],
            },
        )
        result = github_context(GhAccounts(["a", "b"], fake), [], SINCE, TODAY)
        self.assertEqual([(p["number"], p["team"]) for p in result["reviewRequested"]], [(4, False)])

    def test_an_account_without_a_token_fails_and_the_other_still_counts(self):
        fake = FakeGh({"work": "token-w"}, {("token-w", "--author=@me"): [pr("acme/api", 1)]})
        result = github_context(GhAccounts(["work", "gone"], fake), [], SINCE, TODAY)
        self.assertTrue(result["status"].startswith("failed: gone: "), result["status"])
        self.assertNotIn("token-w", result["status"])
        self.assertEqual([p["number"] for p in result["authoredOpen"]], [1])

    def test_no_accounts_uses_the_active_account_without_a_token(self):
        fake = FakeGh({}, {(None, "--author=@me"): [pr("me/tool", 9)]})
        with mock.patch.dict(os.environ):
            os.environ.pop("GH_TOKEN", None)
            result = github_context(GhAccounts([], fake), [], SINCE, TODAY)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([p["number"] for p in result["authoredOpen"]], [9])
        self.assertFalse(any(args[1:3] == ["auth", "token"] for args, _ in fake.calls))

    def test_missing_gh_fails(self):
        def run(args, **kwargs):
            raise FileNotFoundError(args[0])
        result = github_context(GhAccounts([], run), [], SINCE, TODAY)
        self.assertEqual(result["status"], "failed: gh not found")


class LocalGitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def git(self, cwd: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                            "PATH": "/usr/bin:/bin", "HOME": str(self.tmp)})

    def repo(self, name: str) -> Path:
        remote = self.tmp / f"{name}.git"
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(remote))
        path = self.tmp / name
        self.git(self.tmp, "clone", "-q", str(remote), str(path))
        (path / "a.txt").write_text("a", encoding="utf-8")
        self.git(path, "add", "a.txt")
        self.git(path, "commit", "-q", "-m", "init")
        self.git(path, "push", "-q", "origin", "HEAD:main")
        return path

    def test_branch_state_and_pr_lookup(self):
        feature = self.repo("api")
        self.git(feature, "switch", "-q", "-c", "feature/refund")
        for i in range(2):
            (feature / f"f{i}.txt").write_text("x", encoding="utf-8")
            self.git(feature, "add", ".")
            self.git(feature, "commit", "-q", "-m", f"c{i}")
        (feature / "a.txt").write_text("changed", encoding="utf-8")
        (feature / "sub").mkdir()
        clean = self.repo("web")
        fake = FakeGh({"side": "token-s", "work": "token-w"}, pr_lists={("token-w", "api"): []})
        result = local_git_context([str(feature / "sub"), str(feature), str(clean), str(self.tmp / "gone")],
                                   GhAccounts(["side", "work"], fake), fake)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["repos"], [{
            "path": str(feature.resolve()), "branch": "feature/refund", "unpushedCommits": 2, "changedFiles": 1,
            "pr": None, "prChecked": True,
        }])
        self.assertEqual(result["notes"], [f"{self.tmp / 'gone'}: folder not found"])

    def test_pr_state_is_reported_and_a_clean_merged_branch_is_left_out(self):
        api = self.repo("api")
        self.git(api, "switch", "-q", "-c", "feature/x")
        web = self.repo("web")
        self.git(web, "switch", "-q", "-c", "feature/done")
        fake = FakeGh({"work": "token-w"}, pr_lists={
            ("token-w", "api"): [{"number": 12, "url": "u", "state": "OPEN"}],
            ("token-w", "web"): [{"number": 13, "url": "v", "state": "MERGED"}],
        })
        repos = local_git_context([str(api), str(web)], GhAccounts(["work"], fake), fake)["repos"]
        self.assertEqual([(r["branch"], r["pr"], r["prChecked"]) for r in repos],
                         [("feature/x", {"number": 12, "url": "u", "state": "OPEN"}, True)])
        lookups = [args for args, _ in fake.calls if args[1:3] == ["pr", "list"]]
        self.assertTrue(all("--state" in a and a[a.index("--state") + 1] == "all" for a in lookups))

    def test_the_remotes_default_branch_is_not_reported_when_clean(self):
        repo = self.repo("api")
        self.git(repo, "switch", "-q", "-c", "develop")
        self.git(repo, "push", "-q", "origin", "develop")
        self.git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
        fake = FakeGh({})
        self.assertEqual(local_git_context([str(repo)], GhAccounts([], fake), fake)["repos"], [])
        self.assertFalse(any(args[1:3] == ["pr", "list"] for args, _ in fake.calls))

    def test_repository_config_cannot_run_commands(self):
        repo = self.repo("api")
        marker = self.tmp / "fsmonitor-ran"
        self.git(repo, "config", "core.fsmonitor", f"touch {marker}; false")
        (repo / "a.txt").write_text("changed", encoding="utf-8")
        result = local_git_context([str(repo)], GhAccounts([], FakeGh({})))
        self.assertEqual([r["changedFiles"] for r in result["repos"]], [1])
        self.assertFalse(marker.exists())


class BuildTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_output_shape(self):
        settings = replace(make_settings(self.tmp, []),
                           daily=DailySettings(standup_channel="standup", jira_mcp_server=None))
        settings.log_folder.mkdir()
        (settings.log_folder / KO.month_file_name(date(2026, 10, 1))).write_text(
            month_text({date(2026, 10, 30): "### 결제\n\n#### 확인 필요\n- 10:00 · 질문"}), encoding="utf-8")

        def run(args, **kwargs):
            if args[0] == "gh":
                return subprocess.CompletedProcess(args, 0, "[]", "")
            return subprocess.run(args, **kwargs)

        out = build(settings, TODAY, self.tmp / "projects", self.tmp / "dailies", run)
        self.assertEqual(list(out), ["today", "logLanguage", "doneRange", "doneSections", "todaySection",
                                     "openQuestions", "github", "localGit", "slack", "jira", "sourceStatus"])
        self.assertEqual(out["doneRange"], ["2026-10-30", "2026-11-01"])
        self.assertEqual(list(out["doneSections"]), ["2026-10-30"])
        self.assertIsNone(out["todaySection"])
        self.assertEqual(out["slack"], {"userId": "U0TEST", "sinceTs": 1793286000, "standupChannel": "standup"})
        self.assertIsNone(out["jira"])
        self.assertEqual(out["sourceStatus"], {"log": "ok", "github": "ok", "localGit": "ok", "jira": "notConfigured"})


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "daily_context.py"), "--today", "2026-11-02", *args],
            capture_output=True, text=True,
            env={**cli_env(self.tmp), "PATH": "/usr/bin:/bin", "WORKLOG_CLAUDE_PROJECTS": str(self.tmp / "projects")},
        )

    def test_missing_log_folder_exits_2(self):
        write_settings_json(self.home, [])
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("log folder", r.stderr.lower())

    def test_path_options_are_refused(self):
        # The agent can call this script; letting it choose the sessions would let it choose where git runs
        for option in ("--settings", "--projects-root"):
            with self.subTest(option=option):
                self.assertEqual(self.run_cli(option, str(self.tmp)).returncode, 2)

    def test_reads_settings_and_sessions_from_the_environment(self):
        write_settings_json(self.home, [])
        (self.home / "out").mkdir()
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["today"], "2026-11-02")


if __name__ == "__main__":
    unittest.main()
