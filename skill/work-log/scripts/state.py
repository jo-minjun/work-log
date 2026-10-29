#!/usr/bin/env python3
"""Compute the list of dates to collect and manage the last completed date (state.json).

Usage: state.py dates [ARG]   no ARG | YYYY-MM-DD | YYYY-MM-DD..YYYY-MM-DD
       state.py record-write   record the current time in lastWrittenAt

Exit codes: 0 success, 2 input error
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from fsutil import atomic_write_text
from settings import DATA_DIR, DEFAULT_SETTINGS_PATH, SettingsError, load_settings

DEFAULT_STATE_PATH = DATA_DIR / "state.json"
RANGE_SEP = ".."

EXIT_OK, EXIT_INPUT = 0, 2


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("not an object")
        return data
    except (ValueError, TypeError) as e:
        raise ValueError(f"cannot read state.json ({path}): {e}. Delete the file to start over from today") from None


def _write_state(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False))


def load_last(path: Path) -> date | None:
    value = _read_state(path).get("lastCompletedDate")
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError) as e:
        raise ValueError(f"cannot read state.json ({path}): {e}. Delete the file to start over from today") from None


def _load_time(path: Path, key: str) -> datetime | None:
    value = _read_state(path).get(key)
    return datetime.fromisoformat(value) if value else None


def load_last_written(path: Path) -> datetime | None:
    return _load_time(path, "lastWrittenAt")


def load_last_warned(path: Path) -> datetime | None:
    return _load_time(path, "lastWarnedAt")


def mark_complete(path: Path, d: date) -> None:
    data = _read_state(path)
    last = load_last(path)
    # Advance only through consecutive days so a day that failed midway stays in the next default run range
    if last is not None and d != last + timedelta(days=1):
        return
    data["lastCompletedDate"] = d.isoformat()
    _write_state(path, data)


def record_write(path: Path, now: datetime, warned: bool = False) -> None:
    # Lets the runner tell whether this run wrote anything, and whether a day it wrote carries warnings
    data = _read_state(path)
    data["lastWrittenAt"] = now.isoformat(timespec="seconds")
    if warned:
        data["lastWarnedAt"] = data["lastWrittenAt"]
    _write_state(path, data)


def _parse(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"not a valid date: {value} (YYYY-MM-DD)") from None


def _span(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def resolve_dates(arg: str | None, last: date | None, today: date) -> list[date]:
    if not arg:
        # Days up to the last completed one are never rewritten by default; a finished today is refreshed
        if last is None or last >= today:
            return [today]
        return _span(last + timedelta(days=1), today)
    if RANGE_SEP in arg:
        start_s, end_s = arg.split(RANGE_SEP, 1)
        start, end = _parse(start_s), _parse(end_s)
        if start > end:
            raise ValueError(f"start date is after end date: {arg}")
    else:
        start = end = _parse(arg)
    if end > today:
        raise ValueError(f"cannot collect a future date: {end}")
    return _span(start, end)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    dates = sub.add_parser("dates")
    dates.add_argument("arg", nargs="?", default="")
    dates.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    dates.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    record = sub.add_parser("record-write")
    record.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    record.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    args = parser.parse_args()

    if args.command == "record-write":
        try:
            record_write(args.state, datetime.now(load_settings(args.settings).tz))
        except (ValueError, SettingsError) as e:
            print(e, file=sys.stderr)
            return EXIT_INPUT
        return EXIT_OK

    try:
        today = datetime.now(load_settings(args.settings).tz).date()
        result = resolve_dates(args.arg.strip(), load_last(args.state), today)
    except (ValueError, SettingsError) as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    print("\n".join(d.isoformat() for d in result))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
