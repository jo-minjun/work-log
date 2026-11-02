# Daily Stand-up Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `daily` skill, its scripts and runner, and the app's Daily tab as specified.

**Architecture:** Python scripts in `skill/work-log/scripts/` gather facts (`daily_context.py`) and save/render the result (`daily.py`). `run_daily.sh` runs the `daily` skill headless with a strict allowlist. The app reads `dailies/` and starts `run_daily.sh` through a second `Runner`.

**Tech Stack:** Python 3.11+ (`unittest`), zsh, Swift 5.10 / SwiftUI (macOS 14), `WorkLogChecks`.

**Spec:** `docs/2026-11-02-daily-design.md`

## Global Constraints

- English only in code, comments, SKILL.md, UI strings (`en` and `ko` UI tables both filled), README.
- No personal data: no real names, company names, Slack IDs, accounts or home paths in the repo.
- Python scripts follow the existing style: `argparse`, exit codes `0` / `2` (input) / `4` (secret), `atomic_write_text`, `DATA_DIR` from `settings.py`.
- Files under the data and log folders are private (`umask 077`, folders `0700`).
- Never run `gh auth switch`; tokens go into one subprocess's `GH_TOKEN` only and are never printed.
- `run.sh` behavior and its tests stay unchanged.

## Review Focus

1. A settings file without a `daily` group (every existing install) loads with defaults in both Python and Swift.
2. A broken month file must not stop the daily: its status is reported and the other month is still read.
3. `gh` installed but logged out (no token for a configured account) gives `github: failed: ...`, not a crash.
4. A daily file from another day, or none at all, renders a usable Daily tab (title with that date, or the empty state).
5. Stopping a daily run from the app removes only the daily lock, never the collection lock.

---

### Task 1: `daily` settings in Python

**Files:** Modify `skill/work-log/scripts/settings.py`; Test `skill/work-log/tests/test_settings.py`

**Produces:** `Settings.daily: DailySettings` with `github_accounts: list[str]`, `github_owners: list[str]`, `standup_channel: str | None`, `jira_mcp_server: str | None`. `settings.py show` adds `"daily": {"githubAccounts", "githubOwners", "standupChannel", "jiraMcpServer"}`.

- [ ] Test: missing `daily` gives empty lists and `None`; wrong types exit `2`; `show` prints the group.
- [ ] Implement with `_typed` checks; `DailySettings` is a frozen dataclass with defaults so existing `Settings(...)` calls keep working.
- [ ] Run `python3 -m unittest discover -s tests`; commit `feat: 데일리 설정 항목 추가`.

### Task 2: `daily_context.py`

**Files:** Create `skill/work-log/scripts/daily_context.py`; Test `skill/work-log/tests/test_daily_context.py`

**Consumes:** `load_settings`, `FORMATS`, `monthdoc.parse`, `daysection.split`, `extract_sessions.extract`.

**Produces:**
- `done_range(days: set[date], today: date) -> tuple[date, date] | None`
- `read_sections(settings, today) -> tuple[dict[date, str], dict[str, str]]` (sections, file errors)
- `open_questions(sections, fmt, today) -> list[dict]` (`{"date", "project", "text"}`)
- `github_context(accounts, owners, since, today, run=subprocess.run) -> dict`
- `local_git_context(repos: list[Path], accounts, run=subprocess.run) -> dict`
- `build(settings, today, projects_root) -> dict` (the JSON of spec §4.1)
- Constants: `LOOKBACK_DAYS = 21`, `OPEN_QUESTION_DAYS = 14`, `TEAM_REVIEW_DAYS = 14`, `COMMAND_TIMEOUT_SEC = 60`.

- [ ] Tests (literal expected dates):
  - Monday 2026-11-02 with sections 10-29, 10-30, 11-01 → `(10-30, 11-01)`; sections from both month files.
  - Friday 2026-10-30 with 10-28, 10-29 → `(10-29, 10-29)`.
  - Tuesday 2026-10-27 with 10-23, 10-26 → `(10-26, 10-26)`.
  - Gap: Monday 2026-10-26 with only 10-14 → `(10-14, 10-25)`.
  - No section in 21 days → `None`, empty `doneSections`.
  - Needs Confirmation items within 14 days are returned with date and project; older ones are not.
  - `gh` stub records its env and args: one call per account carries that account's token, `--owner` per owner, direct review requests always kept, team requests older than 14 days dropped, results deduplicated by URL.
  - A `gh` stub that fails `auth token` for one account → `status` starts with `failed:` and the other account's PRs remain.
  - Real temp git repo with a bare remote: commits not pushed, changed files, branch without PR (`gh pr list` stub returns `[]`), missing folder is noted.
  - Broken month file → `sourceStatus["log"]` starts with `failed:` and the other file is read.
  - CLI: missing log folder exits `2`.
- [ ] Implement. Merged search uses `--merged-at=>=<start>`; direct review requests use the query `user-review-requested:@me`; team requests use `--review-requested=@me`. Local git uses `git rev-list --count HEAD --not --remotes` and `git status --porcelain`; PR lookup is skipped on `main`/`master`/detached HEAD.
- [ ] Run tests; commit `feat: 데일리 사실 수집 스크립트 추가`.

### Task 3: `daily.py`

**Files:** Create `skill/work-log/scripts/daily.py`; Test `skill/work-log/tests/test_daily.py`

**Produces:**
- `DAILIES_DIR = DATA_DIR / "dailies"`, `LAST_RUN_NAME = "last-run.json"`, `RETENTION_DAYS = 30`
- `validate(payload) -> list[str]` (field paths)
- `render_text(payload, language) -> str`
- `save(payload, trigger, now, dailies_dir, language) -> Path`
- CLI: `save --json PATH [--trigger app|interactive]`, `show [--date]`, `record-run --started-at --ended-at --result --reason [--trigger]`.

- [ ] Tests: the `ko` and `en` texts of spec §4.2 exactly; one-day range `(10/29)`; empty done `- (없음)` / `- (none)`; shape errors give exit `2` with the path (`todo[0].items[1]`); a token-like string gives exit `4` and no file; same date replaced; files older than 30 days removed, `last-run.json` kept; `record-run` writes the spec keys.
- [ ] Implement; commit `feat: 데일리 저장·렌더링 스크립트 추가`.

### Task 4: exclude `/daily` sessions

**Files:** Modify `skill/work-log/scripts/extract_sessions.py`; Test `test_extract_sessions.py`

- [ ] Test: a session that starts with `/daily`, `$daily` or calls `Skill(daily)` is excluded.
- [ ] Implement by turning the single-skill constants into `EXCLUDED_SKILLS = ("work-log", "daily")`; commit `feat: 데일리 실행 세션을 수집에서 제외`.

### Task 5: `run_daily.sh`

**Files:** Modify `skill/work-log/scripts/env.sh`, `run.sh`; Create `skill/work-log/scripts/run_daily.sh`; Test `test_runlog.py`

**Produces:** `env.sh` functions `iso_now`, `log_folder_is_dedicated DATA_DIR FOLDER`. `run_daily.sh` uses `$LOG_DIR/.daily-lock`, `DAILY_TIMEOUT_SEC=900`, writes `dailies/last-run.json` via `daily.py record-run`.

- [ ] Tests (stub `claude`): allowlist has `Read`, `Skill(daily)`, both script rules, 4 Slack tools, `Edit(/<cwd>/**)`, no `Bash`/`Edit`; Jira rules appear only with `jiraMcpServer`; held lock → `busy` and `claude` not called; stub that writes nothing → `noOutput`; stub that saves today's daily → `ok`; stub exiting `3` → `failed`.
- [ ] Implement; run the whole suite (run.sh tests unchanged); commit `feat: 데일리 headless 실행 스크립트 추가`.

### Task 6: skill and install

**Files:** Create `skill/daily/SKILL.md`; Modify `install.sh`, `test_install.py`

- [ ] Test: four links; `daily` links point to `skill/daily`.
- [ ] Write SKILL.md per spec §4.3 and §9; install links via a `link → target` map; commit `feat: daily 스킬과 설치 링크 추가`.

### Task 7: app core

**Files:** Modify `Settings.swift`, `UIStrings.swift`; Create `app/Sources/WorkLogCore/Daily.swift`, `fixtures/daily.json`; Test `WorkLogChecks`

**Produces:** `AppSettings.Daily` (`githubAccounts`, `githubOwners`, `standupChannel`, `jiraMcpServer`); `Daily` and `DailyRun` (Codable), `DailyStore.latest(_ dir: URL) -> Daily?`, `DailyStore.lastRun(_ dir: URL) -> DailyRun?`, `DailyFormat.title(_ date: String, strings:) -> String`.

- [ ] Checks: fixture decodes; settings without `daily` give defaults and a save writes it; `latest` picks the newest date file and ignores `last-run.json`; title `11/2 (Mon) Daily` / `11/2 (월) 데일리`.
- [ ] Implement; commit `feat: 앱 데일리 모델 추가`.

### Task 8: app UI

**Files:** Modify `Runner.swift`, `AppPaths.swift`, `AppModel.swift`, `MainWindow.swift`, `SettingsTab.swift`; Create `Views/DailyTab.swift`

- [ ] `Runner(paths:script:lockDir:)`; `AppPaths.dailyScript`, `dailyLockDir`, `dailies`.
- [ ] `AppModel`: `daily`, `dailyRun`, `isGeneratingDaily`, `generateDaily()`, `stopDaily()`, `copyDaily()`; watcher on `dailies/` (name `.`); notifications; quit confirmation covers both runners.
- [ ] Daily tab and Settings section per spec §4.5.
- [ ] `swift build` and `swift run WorkLogChecks`; commit `feat: 앱에 데일리 탭 추가`.

### Task 9: docs and final check

- [ ] README.md / README.ko.md: Daily section, settings, uninstall links.
- [ ] Full Python suite and Swift checks; squash; manual Generate now on real data (read-only).
