#!/usr/bin/env python3
"""Collect the facts a daily stand-up draft needs: log sections, open questions, GitHub PRs and local git state.

Usage: daily_context.py [--today YYYY-MM-DD]

Output (JSON): today, logLanguage, doneRange, doneSections, todaySection, openQuestions, github, localGit,
slack, jira, sourceStatus. A source that fails is reported in sourceStatus; the others still run.
GitHub tokens are passed to one gh call at a time through GH_TOKEN and never printed.

It takes no path options: it runs git in the folders of past sessions, so the agent must not be able to point
it at sessions or settings of its own making. Tests set WORKLOG_HOME and WORKLOG_CLAUDE_PROJECTS instead.

Exit codes: 0 success (also when a source failed), 2 invalid settings or missing log folder
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from daily import DAILIES_DIR, DAILY_NAME_RE
from daysection import split
from extract_sessions import DEFAULT_PROJECTS_ROOT, extract
from logformat import FORMATS, LogFormat
from monthdoc import parse
from settings import DEFAULT_SETTINGS_PATH, Settings, SettingsError, load_settings

PROJECTS_ROOT_ENV = "WORKLOG_CLAUDE_PROJECTS"

# A long holiday still finds the last stand-up day
LOOKBACK_DAYS = 21
OPEN_QUESTION_DAYS = 14
# Older team review requests are usually picked up by someone else
TEAM_REVIEW_DAYS = 14
COMMAND_TIMEOUT_SEC = 60
SEARCH_LIMIT = "50"
PR_FIELDS = "repository,number,title,url,updatedAt"
# Work on these branches has no PR of its own, so no lookup is made. The remote's default branch is added per repo.
DEFAULT_BRANCHES = ("main", "master", "HEAD")
# A repository's own config can name commands that git status runs (fsmonitor); session folders are not trusted
GIT = ("git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false")
CLOSED_PR_STATES = ("MERGED", "CLOSED")
WEEKEND_START = 5

EXIT_OK, EXIT_INPUT = 0, 2


class CommandError(Exception):
    pass


class CommandNotFound(CommandError):
    pass


def _output(run, args: list[str], **kwargs) -> str:
    try:
        r = run(args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SEC, **kwargs)
    except FileNotFoundError:
        raise CommandNotFound(f"{args[0]} not found") from None
    except subprocess.TimeoutExpired:
        raise CommandError(f"{args[0]} timed out") from None
    if r.returncode != 0:
        message = next((line.strip() for line in r.stderr.splitlines() if line.strip()), f"exit code {r.returncode}")
        raise CommandError(message)
    return r.stdout


class GhAccounts:
    """The gh environments to try, one per configured account. No account means the active gh account."""

    def __init__(self, accounts: list[str], run=subprocess.run):
        self.accounts: list[str | None] = list(accounts) or [None]
        self.run = run
        self._envs: dict[str | None, dict] = {}
        # A logged-out account fails once; asking again for every repository would only add timeouts
        self._failures: dict[str | None, CommandError] = {}

    def env(self, account: str | None) -> dict:
        if account in self._failures:
            raise self._failures[account]
        if account not in self._envs:
            env = dict(os.environ)
            if account is not None:
                # gh auth switch would change gh for every other shell, so the token goes to this call only
                try:
                    token = _output(self.run, ["gh", "auth", "token", "--user", account]).strip()
                    if not token:
                        raise CommandError("no token")
                except CommandError as e:
                    self._failures[account] = e
                    raise
                env["GH_TOKEN"] = token
            self._envs[account] = env
        return self._envs[account]

    def gh(self, account: str | None, args: list[str], **kwargs) -> str:
        return _output(self.run, ["gh", *args], env=self.env(account), **kwargs)


def done_range(days: set[date], today: date, previous_daily: date | None = None) -> tuple[date, date] | None:
    """From the latest weekday before today that has a section, through yesterday; weekend days in between count.

    A daily saved on a later day than that start marks the last stand-up, so the range starts there instead:
    a day without a collection must not bring back work that was already reported.
    """
    past = sorted(d for d in days if today - timedelta(days=LOOKBACK_DAYS) <= d < today)
    weekdays = [d for d in past if d.weekday() < WEEKEND_START]
    start = weekdays[-1] if weekdays else (past[-1] if past else None)
    if start is None:
        return None
    if previous_daily is not None and start < previous_daily < today:
        start = previous_daily
    return start, today - timedelta(days=1)


def previous_daily(dailies_dir: Path, today: date) -> date | None:
    if not dailies_dir.is_dir():
        return None
    dates = [date.fromisoformat(m.group(1)) for p in dailies_dir.iterdir() if (m := DAILY_NAME_RE.match(p.name))]
    earlier = [d for d in dates if d < today]
    return max(earlier) if earlier else None


def read_sections(settings: Settings, today: date) -> tuple[dict[date, str], dict[str, str]]:
    fmt = FORMATS[settings.log_language]
    oldest = today - timedelta(days=LOOKBACK_DAYS)
    sections: dict[date, str] = {}
    errors: dict[str, str] = {}
    for year, month in sorted({(oldest.year, oldest.month), (today.year, today.month)}):
        path = settings.log_folder / fmt.month_file_name(date(year, month, 1))
        if not path.exists():
            continue
        try:
            sections.update(parse(path.read_text(encoding="utf-8"), fmt).days)
        except (OSError, ValueError) as e:
            errors[path.name] = str(e)
    return sections, errors


def open_questions(sections: dict[date, str], fmt: LogFormat, today: date) -> list[dict]:
    heading = fmt.source_headings["needs_confirmation"]
    since = today - timedelta(days=OPEN_QUESTION_DAYS - 1)
    found = []
    for d in sorted(sections):
        if not since <= d <= today:
            continue
        for project in split(sections[d]).projects:
            for name, lines in project.subsections:
                if name == heading:
                    found.extend({"date": d.isoformat(), "project": project.name, "text": line[2:]}
                                 for line in lines if line.startswith("- "))
    return found


def _pr(item: dict) -> dict:
    return {"repo": item["repository"]["nameWithOwner"], "number": item["number"], "title": item["title"],
            "url": item["url"], "updatedAt": item["updatedAt"]}


def _search(gh: GhAccounts, account: str | None, owners: list[str], *query: str) -> list[dict]:
    args = ["search", "prs", *query, *(f"--owner={o}" for o in owners), "--json", PR_FIELDS, "--limit", SEARCH_LIMIT]
    return [_pr(item) for item in json.loads(gh.gh(account, args))]


def github_context(gh: GhAccounts, owners: list[str], since: datetime, today: date) -> dict:
    """since is local midnight of the range start; GitHub reads a date without an offset as UTC."""
    result: dict = {"status": "ok", "authoredOpen": [], "mergedInRange": [], "reviewRequested": []}
    seen: dict[tuple[str, str], dict] = {}

    def add(key: str, prs: list[dict]) -> None:
        for p in prs:
            if (key, p["url"]) not in seen:
                seen[(key, p["url"])] = p
                result[key].append(p)
            elif "team" in p and not p["team"]:
                # Requested directly through one account and through a team in another: direct wins
                seen[(key, p["url"])]["team"] = False

    team_cutoff = datetime.combine(today - timedelta(days=TEAM_REVIEW_DAYS - 1), time.min, since.tzinfo)
    errors = []
    for account in gh.accounts:
        try:
            authored = _search(gh, account, owners, "--author=@me", "--state=open")
            merged = _search(gh, account, owners, "--author=@me", f"--merged-at=>={since.isoformat()}")
            direct = _search(gh, account, owners, "user-review-requested:@me", "--state=open")
            requested = _search(gh, account, owners, "--review-requested=@me", "--state=open")
        except (CommandError, ValueError, KeyError, TypeError) as e:
            errors.append(f"{account}: {e}" if account else str(e))
            continue
        direct_urls = {p["url"] for p in direct}
        add("authoredOpen", authored)
        add("mergedInRange", merged)
        add("reviewRequested", [{**p, "team": False} for p in direct])
        add("reviewRequested", [{**p, "team": True} for p in requested
                                if p["url"] not in direct_urls and _updated(p) >= team_cutoff])
    if errors:
        result["status"] = "failed: " + "; ".join(errors)
    return result


def _updated(pr: dict) -> datetime:
    return datetime.fromisoformat(pr["updatedAt"])


def _branch_pr(gh: GhAccounts, repo: str, branch: str) -> tuple[dict | None, bool]:
    """The newest PR of the branch in any state, and whether any account could look.

    An account that cannot see the repository is skipped.
    """
    for account in gh.accounts:
        try:
            prs = json.loads(gh.gh(account, ["pr", "list", "--head", branch, "--state", "all", "--limit", "1",
                                             "--json", "number,url,state"], cwd=repo))
        except (CommandError, ValueError):
            continue
        return (prs[0] if prs else None), True
    return None, False


def _default_branch(run, top: str) -> str | None:
    try:
        ref = _output(run, [*GIT, "-C", top, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]).strip()
    except CommandError:
        return None
    return ref.split("/", 1)[1] if "/" in ref else None


def local_git_context(cwds: list[str], gh: GhAccounts, run=subprocess.run) -> dict:
    """State of the repositories the sessions worked in.

    A clean default branch, and a clean branch whose PR is already merged or closed, have nothing to report.
    """
    repos, notes, seen = [], [], set()
    for cwd in cwds:
        if not Path(cwd).is_dir():
            notes.append(f"{cwd}: folder not found")
            continue
        try:
            top = _output(run, [*GIT, "-C", cwd, "rev-parse", "--show-toplevel"]).strip()
        except CommandNotFound as e:
            return {"status": f"failed: {e}", "repos": [], "notes": notes}
        except CommandError:
            continue
        if top in seen:
            continue
        seen.add(top)
        try:
            branch = _output(run, [*GIT, "-C", top, "rev-parse", "--abbrev-ref", "HEAD"]).strip()
            unpushed = int(_output(run, [*GIT, "-C", top, "rev-list", "--count", "HEAD", "--not", "--remotes"]))
            status = _output(run, [*GIT, "-C", top, "status", "--porcelain", "--ignore-submodules=all"])
        except (CommandError, ValueError) as e:
            notes.append(f"{top}: {e}")
            continue
        changed = sum(1 for line in status.splitlines() if line.strip())
        clean = not unpushed and not changed
        if branch in DEFAULT_BRANCHES or branch == _default_branch(run, top):
            if clean:
                continue
            pr, checked = None, False
        else:
            pr, checked = _branch_pr(gh, top, branch)
            if clean and pr is not None and pr.get("state") in CLOSED_PR_STATES:
                continue
        repos.append({"path": top, "branch": branch, "unpushedCommits": unpushed, "changedFiles": changed,
                      "pr": pr, "prChecked": checked})
    return {"status": "ok", "repos": repos, "notes": notes}


def session_cwds(settings: Settings, days: list[date], projects_root: Path) -> list[str]:
    cwds: list[str] = []
    for d in days:
        for session in extract(settings, d, projects_root)["sessions"]:
            if session["cwd"] not in cwds:
                cwds.append(session["cwd"])
    return cwds


def build(settings: Settings, today: date, projects_root: Path, dailies_dir: Path, run=subprocess.run) -> dict:
    fmt = FORMATS[settings.log_language]
    sections, file_errors = read_sections(settings, today)
    span = done_range(set(sections), today, previous_daily(dailies_dir, today))
    since = span[0] if span else today
    since_at = datetime.combine(since, time.min, settings.tz)
    gh = GhAccounts(settings.daily.github_accounts, run)
    github = github_context(gh, settings.daily.github_owners, since_at, today)
    days = [since + timedelta(days=n) for n in range((today - since).days + 1)]
    local = local_git_context(session_cwds(settings, days, projects_root), gh, run)
    status = {
        "log": "failed: " + "; ".join(f"{name}: {e}" for name, e in file_errors.items()) if file_errors else "ok",
        "github": github.pop("status"),
        "localGit": local.pop("status"),
    }
    if not settings.daily.standup_channel:
        status["standup"] = "notConfigured"
    if not settings.daily.jira_mcp_server:
        status["jira"] = "notConfigured"
    return {
        "today": today.isoformat(),
        "logLanguage": settings.log_language,
        "doneRange": [span[0].isoformat(), span[1].isoformat()] if span else None,
        "doneSections": {d.isoformat(): sections[d] for d in sorted(sections) if span and span[0] <= d < today},
        "todaySection": sections.get(today),
        "openQuestions": open_questions(sections, fmt, today),
        "github": github,
        "localGit": local,
        "slack": {
            "userId": settings.slack_user_id,
            "sinceTs": int(since_at.timestamp()),
            "standupChannel": settings.daily.standup_channel,
        },
        "jira": {"server": settings.daily.jira_mcp_server} if settings.daily.jira_mcp_server else None,
        "sourceStatus": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today")
    args = parser.parse_args()
    projects_root = Path(os.environ.get(PROJECTS_ROOT_ENV) or DEFAULT_PROJECTS_ROOT).expanduser()
    try:
        settings = load_settings(DEFAULT_SETTINGS_PATH)
    except SettingsError as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    try:
        today = date.fromisoformat(args.today) if args.today else datetime.now(settings.tz).date()
    except ValueError:
        print(f"not a valid date: {args.today} (YYYY-MM-DD)", file=sys.stderr)
        return EXIT_INPUT
    if not settings.log_folder.is_dir():
        print(f"Log folder not found: {settings.log_folder}", file=sys.stderr)
        return EXIT_INPUT
    json.dump(build(settings, today, projects_root, DAILIES_DIR), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
