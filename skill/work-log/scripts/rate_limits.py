#!/usr/bin/env python3
"""Save the Claude Code statusline rate_limits to claude-rate-limits.json.

Usage: rate_limits.py [--path PATH]   (statusline JSON on stdin)

Exit codes: 0 always, so the user's statusline never breaks
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from fsutil import atomic_write_text
from settings import DATA_DIR, system_timezone

DEFAULT_RATE_LIMITS_PATH = DATA_DIR / "claude-rate-limits.json"


def save_from_statusline(stdin_text: str, path: Path, now: datetime) -> bool:
    try:
        data = json.loads(stdin_text)
    except ValueError:
        return False
    limits = data.get("rate_limits") if isinstance(data, dict) else None
    if not isinstance(limits, dict):
        return False
    record = {
        "five_hour": limits.get("five_hour"),
        "seven_day": limits.get("seven_day"),
        "updatedAt": now.isoformat(timespec="seconds"),
    }
    atomic_write_text(path, json.dumps(record, ensure_ascii=False))
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_RATE_LIMITS_PATH)
    args = parser.parse_args()
    try:
        save_from_statusline(sys.stdin.read(), args.path, datetime.now(system_timezone()))
    except OSError as e:
        print(e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
