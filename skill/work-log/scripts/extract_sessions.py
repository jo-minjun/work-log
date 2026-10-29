#!/usr/bin/env python3
"""Extract factual info about one day of work sessions from Claude session logs (~/.claude/projects/*/*.jsonl).

Output (JSON): date, skippedLines, sessions[] (sessionId, repo, cwd, branches, start, end,
title, prompts, commits, prs). Does no summarising or classification.

Exit codes: 0 success, 2 input error
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, time
from pathlib import Path

from settings import DEFAULT_SETTINGS_PATH, Settings, SettingsError, load_settings

DEFAULT_PROJECTS_ROOT = Path("~/.claude/projects").expanduser()
PROMPT_MAX_CHARS = 300
PROMPTS_PER_SESSION_MAX = 30
WORK_LOG_SKILL = "work-log"
WORK_LOG_COMMAND = "/work-log"
# Codex invokes skills as `$name`
CODEX_WORK_LOG_COMMAND = "$work-log"
# Text the user pasted is a real request even if it starts with `<`
USER_TAG_PREFIXES = ("<pasted_content",)
PR_URL_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
GIT_COMMIT_RE = re.compile(r"git(?:\s+-C\s+\S+)?\s+commit\b")
# Both `-m "$(cat <<'EOF'` and `-F - <<'EOF'` start the heredoc on the same line as the commit command
SAME_LINE_HEREDOC_RE = re.compile(r"""\A[^\n]*<<-?\s*['"]?\w+['"]?\s*\n\s*(.+)""")
M_FLAG_RE = re.compile(r"""-\w*m\s+(["'])(.+?)\1""", re.S)
INTERRUPT_PREFIX = "[Request interrupted"
# Markers for user events a human did not type, such as compaction summaries
NON_HUMAN_PROMPT_FLAGS = ("isMeta", "isCompactSummary", "isVisibleInTranscriptOnly")
# Programmatic sessions (Orca branch-name generation, `claude -p`) are not human work
PROGRAMMATIC_ENTRYPOINT_PREFIX = "sdk"

EXIT_OK, EXIT_INPUT = 0, 2


def commit_message(command: str) -> str | None:
    match = GIT_COMMIT_RE.search(command)
    if match is None:
        return None
    segment = command[match.start():]
    heredoc = SAME_LINE_HEREDOC_RE.search(segment)
    if heredoc:
        return heredoc.group(1).strip()
    m_flag = M_FLAG_RE.search(segment)
    if m_flag:
        return m_flag.group(2).strip().splitlines()[0]
    return None


def _text_blocks(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


def _prompt_text(event: dict) -> str | None:
    if any(event.get(flag) for flag in NON_HUMAN_PROMPT_FLAGS):
        return None
    texts = [t.strip() for t in _text_blocks(event.get("message", {}).get("content"))]
    text = "\n".join(t for t in texts if t)
    if not text:
        return None
    if text.startswith("<") and not text.startswith(USER_TAG_PREFIXES):
        return None
    if text.startswith(INTERRUPT_PREFIX):
        return None
    return text


def _is_work_log_event(event: dict) -> bool:
    content = event.get("message", {}).get("content")
    # Conversation summaries describe this skill and may quote command strings, so they are not evidence of execution
    if event.get("type") == "user" and not event.get("isCompactSummary"):
        for text in _text_blocks(content):
            text = text.strip()
            if text.startswith((WORK_LOG_COMMAND, CODEX_WORK_LOG_COMMAND)) or f"<command-name>{WORK_LOG_COMMAND}</command-name>" in text:
                return True
    if event.get("type") == "assistant" and isinstance(content, list):
        for block in content:
            if (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"
                    and block.get("input", {}).get("skill") == WORK_LOG_SKILL):
                return True
    return False


def _is_programmatic(event: dict) -> bool:
    return event.get("entrypoint", "").startswith(PROGRAMMATIC_ENTRYPOINT_PREFIX)


def _included_root(cwd: str | None, include: list[Path]) -> Path | None:
    if not cwd:
        return None
    path = Path(cwd)
    if not include:
        # All-sessions mode: using the parent as root makes the repo name the cwd's basename
        return path.parent
    for root in include:
        if path.is_relative_to(root):
            return root
    return None


def _repo(cwd: str, root: Path) -> str:
    rel = Path(cwd).relative_to(root)
    return rel.parts[0] if rel.parts else root.name


def _tool_result_texts(content) -> list[tuple[str, str]]:
    results = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results.append((block.get("tool_use_id", ""), "\n".join(_text_blocks(block.get("content")))))
    return results


def _summarize(session_id: str, events: list[dict], title: str | None, settings: Settings) -> dict | None:
    first_cwd = next((e["cwd"] for e in events if _included_root(e.get("cwd"), settings.session_folders)), None)
    if first_cwd is None or any(_is_work_log_event(e) or _is_programmatic(e) for e in events):
        return None
    times = [e["_local"] for e in events]
    branches, prompts, commits, prs = [], [], [], []
    pr_tool_ids = set()
    for e in events:
        branch = e.get("gitBranch")
        if branch and branch not in branches:
            branches.append(branch)
        content = e.get("message", {}).get("content")
        if e.get("type") == "user":
            prompt = _prompt_text(e)
            if prompt and len(prompts) < PROMPTS_PER_SESSION_MAX:
                prompts.append(prompt[:PROMPT_MAX_CHARS])
            for tool_id, text in _tool_result_texts(content):
                if tool_id in pr_tool_ids:
                    prs.extend({"url": url} for url in PR_URL_RE.findall(text) if {"url": url} not in prs)
        elif e.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash"):
                    continue
                command = block.get("input", {}).get("command", "")
                message = commit_message(command)
                if message and {"message": message} not in commits:
                    commits.append({"message": message})
                if "gh pr create" in command:
                    pr_tool_ids.add(block.get("id"))
    return {
        "sessionId": session_id,
        "repo": _repo(first_cwd, _included_root(first_cwd, settings.session_folders)),
        "cwd": first_cwd,
        "branches": branches,
        "start": min(times).strftime("%H:%M"),
        "end": max(times).strftime("%H:%M"),
        "title": title,
        "prompts": prompts,
        "commits": commits,
        "prs": prs,
    }


def _birthtime(path: Path) -> float:
    st = path.stat()
    return getattr(st, "st_birthtime", st.st_mtime)


def extract(settings: Settings, d: date, projects_root: Path) -> dict:
    day_start = datetime.combine(d, time.min, settings.tz)
    skipped = 0
    sessions = []
    # A forked session copies parent events with the same uuid, so the file created first owns the event
    seen_uuids: set[str] = set()
    paths = sorted(projects_root.glob("*/*.jsonl"), key=lambda p: (_birthtime(p), str(p)))
    for path in paths:
        # A file last modified before the target day cannot contain events from that day
        if path.stat().st_mtime < day_start.timestamp():
            continue
        events, title = [], None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if not isinstance(e, dict):
                    skipped += 1
                    continue
                if e.get("type") == "ai-title" and e.get("aiTitle"):
                    title = e["aiTitle"]
                if e.get("isSidechain") or not e.get("timestamp"):
                    continue
                try:
                    local = datetime.fromisoformat(e["timestamp"]).astimezone(settings.tz)
                except (TypeError, ValueError):
                    skipped += 1
                    continue
                if local.date() != d or e.get("uuid") in seen_uuids:
                    continue
                if e.get("uuid"):
                    seen_uuids.add(e["uuid"])
                e["_local"] = local
                events.append(e)
        if events:
            summary = _summarize(path.stem, events, title, settings)
            if summary:
                sessions.append(summary)
    sessions.sort(key=lambda s: s["start"])
    return {"date": d.isoformat(), "skippedLines": skipped, "sessions": sessions}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    parser.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT)
    args = parser.parse_args()
    try:
        d = date.fromisoformat(args.date)
    except ValueError:
        print(f"not a valid date: {args.date} (YYYY-MM-DD)", file=sys.stderr)
        return EXIT_INPUT
    try:
        result = extract(load_settings(args.settings), d, args.projects_root)
    except SettingsError as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
