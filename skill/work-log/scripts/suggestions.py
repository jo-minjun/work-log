#!/usr/bin/env python3
"""Store for new-project suggestions (spec 5.2).

Subcommands:
  list          print every suggestion
  answered      print suggestions the user answered and that await apply
  mark-applied  move pendingAnswer into history (--id, --result)
  propose       evaluate a candidate read from --json (file or "-"); without an id
                it matches an existing record by exact name, ignoring case

Exit codes: 0 ok, 2 input, validation or store error, 4 a value looks like a secret
(on 2 or 4 the file is left untouched).

This module never writes pendingAnswer, neverSuggest, or status "answered";
those fields belong to the app. Both sides serialize through an flock on
suggestions.json.lock.
"""

import argparse
import fcntl
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fsutil import atomic_write_text
from secretscan import secret_fields, secret_message
from settings import DATA_DIR, system_timezone

DEFAULT_SUGGESTIONS_PATH = DATA_DIR / "suggestions.json"
LOCK_TIMEOUT_SEC = 10
LOCK_RETRY_SEC = 0.05
LOCK_TIMEOUT_ENV = "WORKLOG_LOCK_TIMEOUT"
WINDOW_LEAD_DAYS = 15
MIN_DISTINCT_DAYS = 2
MIN_ITEMS = 3
STORE_VERSION = 1

PENDING, ANSWERED, APPLIED = "pending", "answered", "applied"
ACCEPT, REJECT = "accept", "reject"

EXIT_OK, EXIT_INPUT, EXIT_SECRET = 0, 2, 4


class StoreError(Exception):
    pass


class SecretError(Exception):
    pass


def _lock_timeout() -> float:
    raw = os.environ.get(LOCK_TIMEOUT_ENV)
    if not raw:
        return LOCK_TIMEOUT_SEC
    try:
        return float(raw)
    except ValueError:
        raise StoreError(f"{LOCK_TIMEOUT_ENV} must be a number: {raw}") from None


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _lock_timeout()
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise StoreError("timed out waiting for the suggestions lock") from None
                time.sleep(LOCK_RETRY_SEC)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _read(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"version": STORE_VERSION, "suggestions": []}
    except OSError as e:
        raise StoreError(f"cannot read {path}: {e}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise StoreError(f"{path} is not valid JSON: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("suggestions"), list):
        raise StoreError(f"{path} has no suggestions array")
    return data


def _write(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _find(data: dict, sid: str) -> dict:
    for s in data["suggestions"]:
        if isinstance(s, dict) and s.get("id") == sid:
            return s
    raise StoreError(f"suggestion not found: {sid}")


def _is_day(value) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _is_timestamp(value) -> bool:
    try:
        datetime.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _record_is_valid(record) -> bool:
    # One hand-edited or half-migrated record must not stop the other suggestions from being handled
    if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not isinstance(record.get("name"), str):
        return False
    if record.get("status") not in (PENDING, ANSWERED, APPLIED):
        return False
    evidence, history = record.get("evidence"), record.get("history", [])
    if not isinstance(evidence, list) or not isinstance(history, list):
        return False
    if not all(isinstance(e, dict) and _is_day(e.get("date")) and isinstance(e.get("source"), str)
               and isinstance(e.get("line"), str) for e in evidence):
        return False
    if not all(isinstance(h, dict) and isinstance(h.get("answer"), str) and _is_timestamp(h.get("answeredAt"))
               for h in history):
        return False
    return record.get("pendingAnswer") is None or isinstance(record.get("pendingAnswer"), dict)


def _stamp(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


def window_start(today: date) -> date:
    return today.replace(day=1) - timedelta(days=WINDOW_LEAD_DAYS)


def _validate_payload(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    for key in ("name", "description"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f"{key}: must be a non-empty string")
    if "id" in payload and not isinstance(payload["id"], str):
        raise ValueError("id: must be a string")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("evidence: must be an array")
    for i, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise ValueError(f"evidence[{i}]: must be an object")
        try:
            date.fromisoformat(item.get("date"))
        except (TypeError, ValueError):
            raise ValueError(f"evidence[{i}].date: must be YYYY-MM-DD") from None
        for key in ("source", "line"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"evidence[{i}].{key}: must be a non-empty string")
    return evidence


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        key = (item["date"], item["line"])
        if key not in seen:
            seen.add(key)
            out.append({"date": item["date"], "source": item["source"], "line": item["line"]})
    return out


def _meets_threshold(items: list[dict]) -> bool:
    return len({e["date"] for e in items}) >= MIN_DISTINCT_DAYS and len(items) >= MIN_ITEMS


def _result(action: str, sid: str | None, reason: str | None = None) -> dict:
    return {"action": action, "id": sid, "reason": reason}


def _existing(data: dict, payload: dict) -> dict | None:
    if "id" in payload:
        return _find(data, payload["id"])
    name = payload["name"].strip().casefold()
    for s in data["suggestions"]:
        if isinstance(s, dict) and isinstance(s.get("name"), str) and s["name"].strip().casefold() == name:
            return s
    return None


def _last_rejection_day(record: dict) -> date | None:
    history = record.get("history") or []
    if not history:
        raise StoreError(f"suggestion {record.get('id')} is applied but has no history")
    last = history[-1]
    if last.get("answer") != REJECT:
        return None
    # answeredAt carries its writer's offset; compare days in the user's time zone
    return datetime.fromisoformat(last["answeredAt"]).astimezone(system_timezone()).date()


def propose(path: Path, payload: dict, today: date, now: datetime) -> dict:
    secrets = secret_fields(payload)
    if secrets:
        raise SecretError(secret_message(secrets))
    evidence = _validate_payload(payload)
    start = window_start(today)
    fresh = _dedupe([e for e in evidence if start <= date.fromisoformat(e["date"]) <= today])
    with _locked(path):
        data = _read(path)
        record = _existing(data, payload)
        if record is None:
            if not _meets_threshold(fresh):
                return _result("skipped", None, "below threshold")
            record = {
                "id": uuid.uuid4().hex, "type": "new_project", "name": payload["name"].strip(),
                "description": payload["description"], "evidence": fresh, "status": PENDING,
                "neverSuggest": False, "createdAt": _stamp(now), "updatedAt": _stamp(now),
                "pendingAnswer": None, "history": [],
            }
            data["suggestions"].append(record)
            action = "created"
        elif not _record_is_valid(record):
            return _result("skipped", record.get("id"), "invalid record")
        elif record.get("neverSuggest"):
            return _result("skipped", record["id"], "never suggest")
        elif record["status"] == PENDING:
            # Only creation sets the description; later runs add evidence (spec §8)
            merged = _dedupe(record["evidence"] + fresh)
            record["evidence"] = [e for e in merged if start <= date.fromisoformat(e["date"]) <= today]
            record["updatedAt"] = _stamp(now)
            action = "updated"
        elif record["status"] == ANSWERED:
            return _result("skipped", record["id"], "awaiting apply")
        else:
            rejected_on = _last_rejection_day(record)
            if rejected_on is None:
                return _result("skipped", record["id"], "already accepted")
            after = [e for e in fresh if date.fromisoformat(e["date"]) > rejected_on]
            if not _meets_threshold(after):
                return _result("skipped", record["id"], "below threshold after rejection")
            record["evidence"] = after
            record["description"] = payload["description"]
            record["status"] = PENDING
            record["updatedAt"] = _stamp(now)
            action = "resuggested"
        _write(path, data)
        return _result(action, record["id"])


def list_all(path: Path) -> list[dict]:
    # Writers replace the file atomically, so a lock-free read is consistent
    return _read(path)["suggestions"]


def answered(path: Path) -> list[dict]:
    return [s for s in list_all(path) if isinstance(s, dict) and s.get("status") == ANSWERED]


def mark_applied(path: Path, sid: str, result: str, now: datetime) -> None:
    with _locked(path):
        data = _read(path)
        record = _find(data, sid)
        if not _record_is_valid(record):
            raise StoreError(f"invalid record {sid}")
        if record.get("status") != ANSWERED or not record.get("pendingAnswer"):
            raise StoreError(f"suggestion {sid} is not awaiting apply (status: {record.get('status')})")
        entry = {**record["pendingAnswer"], "appliedAt": _stamp(now), "result": result}
        record.setdefault("history", []).append(entry)
        record["pendingAnswer"] = None
        record["status"] = APPLIED
        record["updatedAt"] = _stamp(now)
        _write(path, data)


def _load_payload(source: str) -> dict:
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read JSON: {e}") from None


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=DEFAULT_SUGGESTIONS_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("answered")
    applied = sub.add_parser("mark-applied")
    applied.add_argument("--id", required=True)
    applied.add_argument("--result", required=True)
    prop = sub.add_parser("propose")
    prop.add_argument("--json", required=True, dest="source")
    args = parser.parse_args()

    now = datetime.now(system_timezone())
    try:
        if args.command == "list":
            _print(list_all(args.file))
        elif args.command == "answered":
            _print(answered(args.file))
        elif args.command == "mark-applied":
            mark_applied(args.file, args.id, args.result, now)
            _print({"id": args.id, "status": APPLIED})
        else:
            _print(propose(args.file, _load_payload(args.source), now.date(), now))
    except (StoreError, ValueError) as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    except (KeyError, TypeError, AttributeError) as e:
        print(f"unexpected data in the suggestions file: {e!r}", file=sys.stderr)
        return EXIT_INPUT
    except SecretError as e:
        print(e, file=sys.stderr)
        return EXIT_SECRET
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
