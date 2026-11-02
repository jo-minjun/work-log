#!/usr/bin/env python3
"""Save, show and record dailies (stand-up drafts) in the WorkLog data folder.

Usage: daily.py save --json PATH [--trigger app|interactive] [--settings PATH]
       daily.py show [--date YYYY-MM-DD]
       daily.py record-run --started-at T --ended-at T --result R [--reason TEXT]   (run_daily.sh only)

save checks the payload, refuses secret-like values, adds generatedAt, trigger, sources and the copy text,
then replaces dailies/<date>.json and removes dailies older than 30 days.

Exit codes: 0 success, 2 invalid input or no daily, 4 a value looks like a secret (on 2 or 4 nothing is written)
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from fsutil import atomic_write_text
from secretscan import secret_fields, secret_message
from settings import DATA_DIR, DEFAULT_SETTINGS_PATH, SettingsError, load_settings, system_timezone

DAILIES_DIR = DATA_DIR / "dailies"
LAST_RUN_NAME = "last-run.json"
RETENTION_DAYS = 30
TRIGGERS = ("app", "interactive")
RUN_RESULTS = ("ok", "noOutput", "failed", "timeout", "busy")
DAILY_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
PRIVATE_DIR_MODE = 0o700

HEADINGS = {
    "en": {"done": "Done", "todo": "To do", "range": "–", "none": "(none)"},
    "ko": {"done": "한 일", "todo": "할 일", "range": "~", "none": "(없음)"},
}

EXIT_OK, EXIT_INPUT, EXIT_SECRET = 0, 2, 4


def _is_date(value) -> bool:
    if not isinstance(value, str):
        return False
    # fromisoformat also reads 20261102 and 2026-W44-1; file names and readers expect YYYY-MM-DD only
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_groups(value, where: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{where} must be a list"]
    errors = []
    for i, group in enumerate(value):
        at = f"{where}[{i}]"
        if not isinstance(group, dict):
            errors.append(f"{at} must be an object")
            continue
        if not _is_text(group.get("project")):
            errors.append(f"{at}.project must be a non-empty string")
        items = group.get("items")
        if not isinstance(items, list):
            errors.append(f"{at}.items must be a list")
            continue
        errors.extend(f"{at}.items[{j}] must be a non-empty string" for j, item in enumerate(items) if not _is_text(item))
    return errors


def _check_evidence(value) -> list[str]:
    if not isinstance(value, list):
        return ["evidence must be a list"]
    errors = []
    for i, entry in enumerate(value):
        at = f"evidence[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{at} must be an object")
            continue
        errors.extend(f"{at}.{key} must be a non-empty string" for key in ("task", "reason") if not _is_text(entry.get(key)))
        errors.extend(f"{at}.{key} must be a list of strings" for key in ("sources", "links")
                      if not (isinstance(entry.get(key), list) and all(isinstance(v, str) for v in entry[key])))
        if not isinstance(entry.get("weak"), bool):
            errors.append(f"{at}.weak must be true or false")
    return errors


def validate(payload) -> list[str]:
    """Problems with the payload, each starting with the path of the field."""
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    errors = []
    if not _is_date(payload.get("date")):
        errors.append("date must be YYYY-MM-DD")
    span = payload.get("doneRange")
    if span is not None and not (isinstance(span, list) and len(span) == 2 and all(map(_is_date, span))):
        errors.append("doneRange must be null or [start, end] dates")
    errors += _check_groups(payload.get("done"), "done")
    errors += _check_groups(payload.get("todo"), "todo")
    errors += _check_evidence(payload.get("evidence"))
    notes = payload.get("notes")
    if not (isinstance(notes, list) and all(isinstance(n, str) for n in notes)):
        errors.append("notes must be a list of strings")
    status = payload.get("sourceStatus")
    if status is not None:
        if not isinstance(status, dict):
            errors.append("sourceStatus must be an object")
        else:
            errors.extend(f"sourceStatus.{k} must be a string" for k, v in status.items() if not isinstance(v, str))
    return errors


def _short(d: date) -> str:
    return f"{d.month}/{d.day}"


def _block(heading: str, groups: list[dict], none: str) -> list[str]:
    lines = [heading]
    for group in groups:
        lines.append(f"- {group['project']}")
        lines.extend(f"  - {item}" for item in group["items"])
    if not groups:
        lines.append(f"- {none}")
    return lines


def render_text(payload: dict, language: str) -> str:
    h = HEADINGS[language]
    span = payload.get("doneRange")
    done_heading = h["done"]
    if span:
        start, end = date.fromisoformat(span[0]), date.fromisoformat(span[1])
        done_heading += f" ({_short(start)})" if start == end else f" ({_short(start)}{h['range']}{_short(end)})"
    todo_heading = f"{h['todo']} ({_short(date.fromisoformat(payload['date']))})"
    return "\n".join([*_block(done_heading, payload["done"], h["none"]), "",
                      *_block(todo_heading, payload["todo"], h["none"])])


def _prune(dailies_dir: Path, today: date) -> None:
    oldest = today - timedelta(days=RETENTION_DAYS)
    for path in dailies_dir.iterdir():
        match = DAILY_NAME_RE.match(path.name)
        if match and _is_date(match.group(1)) and date.fromisoformat(match.group(1)) < oldest:
            path.unlink(missing_ok=True)


def _ensure_dir(dailies_dir: Path) -> None:
    dailies_dir.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)


def save(payload: dict, trigger: str, now: datetime, dailies_dir: Path, language: str) -> Path:
    record = {k: v for k, v in payload.items() if k != "sourceStatus"}
    record.update({
        "sources": payload.get("sourceStatus") or {},
        "generatedAt": now.isoformat(timespec="seconds"),
        "trigger": trigger,
        "text": render_text(payload, language),
    })
    _ensure_dir(dailies_dir)
    path = dailies_dir / f"{payload['date']}.json"
    atomic_write_text(path, json.dumps(record, ensure_ascii=False, indent=2))
    _prune(dailies_dir, now.date())
    return path


def latest(dailies_dir: Path, on: str | None = None) -> Path | None:
    if not dailies_dir.is_dir():
        return None
    names = sorted(p.name for p in dailies_dir.iterdir() if DAILY_NAME_RE.match(p.name))
    if on is not None:
        names = [n for n in names if n == f"{on}.json"]
    return dailies_dir / names[-1] if names else None


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_save = sub.add_parser("save")
    p_save.add_argument("--json", type=Path, required=True)
    p_save.add_argument("--trigger", choices=TRIGGERS, default="interactive")
    p_save.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    p_show = sub.add_parser("show")
    p_show.add_argument("--date")
    p_run = sub.add_parser("record-run")
    p_run.add_argument("--started-at", required=True)
    p_run.add_argument("--ended-at", required=True)
    p_run.add_argument("--result", choices=RUN_RESULTS, required=True)
    p_run.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.command == "show":
        path = latest(DAILIES_DIR, args.date)
        if path is None:
            print("No daily found", file=sys.stderr)
            return EXIT_INPUT
        print(json.loads(path.read_text(encoding="utf-8"))["text"])
        return EXIT_OK

    if args.command == "record-run":
        _ensure_dir(DAILIES_DIR)
        record = {"startedAt": args.started_at, "endedAt": args.ended_at, "trigger": "app",
                  "result": args.result, "reason": args.reason or None}
        atomic_write_text(DAILIES_DIR / LAST_RUN_NAME, json.dumps(record, ensure_ascii=False, indent=2))
        return EXIT_OK

    try:
        payload = json.loads(args.json.read_text(encoding="utf-8"))
        language = load_settings(args.settings).log_language
    except (OSError, ValueError, SettingsError) as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    errors = validate(payload)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return EXIT_INPUT
    secrets = secret_fields(payload)
    if secrets:
        print(secret_message(secrets), file=sys.stderr)
        return EXIT_SECRET
    path = save(payload, args.trigger, datetime.now(system_timezone()), DAILIES_DIR, language)
    print(path)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
