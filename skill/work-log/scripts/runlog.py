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
CODEX_ITEM_EVENT = "item.completed"
CODEX_MESSAGE_ITEM = "agent_message"
# A notification shows a few lines at most; the full report stays in the output file
SUMMARY_MAX_CHARS = 200
EMPTY_SUMMARY = {"costUsd": None, "tokens": None, "summary": None}


def report_summary(report: str | None) -> str | None:
    """The first non-empty line of the report, without Markdown marks. SKILL.md makes it a one-sentence summary."""
    for line in (report or "").splitlines():
        line = line.replace("**", "").replace("`", "").strip().lstrip("#").strip()
        if line:
            return line if len(line) <= SUMMARY_MAX_CHARS else line[:SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return None


def _summarize_claude(text: str) -> dict:
    data = json.loads(text)
    return {"costUsd": data.get("total_cost_usd"), "tokens": None, "summary": report_summary(data.get("result")),
            "isError": bool(data.get("is_error"))}


def _summarize_codex(text: str) -> dict:
    tokens, failed, report = 0, False, None
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
        elif kind == CODEX_ITEM_EVENT and (event.get("item") or {}).get("type") == CODEX_MESSAGE_ITEM:
            report = event["item"].get("text")
    return {"costUsd": None, "tokens": tokens, "summary": report_summary(report), "isError": failed}


def summarize(provider: str, output_path: Path) -> dict:
    try:
        text = Path(output_path).read_text(encoding="utf-8")
        return _summarize_codex(text) if provider == "codex" else _summarize_claude(text)
    except (OSError, ValueError, AttributeError):
        return {**EMPTY_SUMMARY, "isError": True}


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

    summary = summarize(args.provider, args.output) if args.output else EMPTY_SUMMARY
    append(args.runs, {
        "startedAt": args.started_at,
        "endedAt": args.ended_at,
        "trigger": args.trigger,
        "provider": args.provider,
        "result": args.result,
        "reason": args.reason or None,
        "costUsd": summary["costUsd"],
        "tokens": summary["tokens"],
        "summary": summary["summary"],
        "logPath": args.log_path or None,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
