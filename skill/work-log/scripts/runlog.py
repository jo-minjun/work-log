#!/usr/bin/env python3
"""Summarize a provider run and append it to runs.jsonl.

Usage: runlog.py append --provider P --started-at T --ended-at T --trigger T --result R
                        [--output PATH] [--reason TEXT] [--log-path PATH] [--runs PATH]

Exit codes: 0 success
"""

import argparse
import json
import os
import sys
from pathlib import Path

from settings import DATA_DIR

DEFAULT_RUNS_PATH = DATA_DIR / "runs.jsonl"
CODEX_FAILURE_EVENTS = ("turn.failed", "error")
CODEX_USAGE_EVENT = "turn.completed"


def _summarize_claude(text: str) -> dict:
    data = json.loads(text)
    return {"costUsd": data.get("total_cost_usd"), "tokens": None, "isError": bool(data.get("is_error"))}


def _summarize_codex(text: str) -> dict:
    tokens, failed = 0, False
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        if kind in CODEX_FAILURE_EVENTS:
            failed = True
        elif kind == CODEX_USAGE_EVENT:
            usage = event.get("usage") or {}
            tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    return {"costUsd": None, "tokens": tokens, "isError": failed}


def summarize(provider: str, output_path: Path) -> dict:
    try:
        text = Path(output_path).read_text(encoding="utf-8")
        return _summarize_codex(text) if provider == "codex" else _summarize_claude(text)
    except (OSError, ValueError, AttributeError):
        return {"costUsd": None, "tokens": None, "isError": True}


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    # One O_APPEND write keeps a line intact even if the app appends at the same moment
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("append")
    cmd.add_argument("--provider", required=True)
    cmd.add_argument("--output", type=Path)
    cmd.add_argument("--started-at", required=True)
    cmd.add_argument("--ended-at", required=True)
    cmd.add_argument("--trigger", required=True)
    cmd.add_argument("--result", required=True)
    cmd.add_argument("--reason")
    cmd.add_argument("--log-path")
    cmd.add_argument("--runs", type=Path, default=DEFAULT_RUNS_PATH)
    args = parser.parse_args()

    summary = summarize(args.provider, args.output) if args.output else {"costUsd": None, "tokens": None}
    append(args.runs, {
        "startedAt": args.started_at,
        "endedAt": args.ended_at,
        "trigger": args.trigger,
        "provider": args.provider,
        "result": args.result,
        "reason": args.reason or None,
        "costUsd": summary["costUsd"],
        "tokens": summary["tokens"],
        "logPath": args.log_path or None,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
