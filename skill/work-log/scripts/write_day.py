#!/usr/bin/env python3
"""Validate the day JSON produced by Claude and replace that day's section in the monthly work log file.

Subcommands:
  day                replace the day section (advance the last completed date if there are no warnings)
  others             print Other-project (`### 기타`/`### Other`) items from this month and the last 15 days of last month
  reclassify         move Other-project items listed in --json into the --project section of their day
  init-project-list  create the project list file if it is missing, and print its path

Exit codes: 0 success, 2 input/validation error, 3 monthly file cannot be parsed,
4 a value looks like a secret (on 2, 3 or 4 no file is changed)
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from fsutil import atomic_write_text
from settings import DEFAULT_SETTINGS_PATH, Settings, SettingsError, load_settings
from logformat import FORMATS, LogFormat
from secretscan import secret_fields, secret_message
from daysection import move_items
from monthdoc import MonthDoc, day_heading, new_doc, parse, serialize, touch
from state import DEFAULT_STATE_PATH, load_last, mark_complete, record_write

URL_PREFIXES = ("http://", "https://")
PREVIOUS_MONTH_LOOKBACK_DAYS = 15

EXIT_OK, EXIT_INPUT, EXIT_DOC, EXIT_SECRET = 0, 2, 3, 4


def log_format(cfg: Settings) -> LogFormat:
    return FORMATS[cfg.log_language]


def month_file(cfg: Settings, d: date) -> Path:
    return cfg.log_folder / log_format(cfg).month_file_name(d)


class InputError(Exception):
    pass


class DocError(Exception):
    pass


class SecretError(Exception):
    pass


def _check_text(errors: list[str], where: str, value, required: bool = True) -> None:
    if value in (None, "") and not required:
        return
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: must be a non-empty string")
        return
    # A newline would push the value onto a new line, where it could be parsed as a section heading in the monthly file
    if "\n" in value or "\r" in value:
        errors.append(f"{where}: must not contain a newline")


def validate_day(payload: dict, fmt: LogFormat) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["top-level value must be an object"]
    try:
        date.fromisoformat(payload.get("date"))
    except (TypeError, ValueError):
        errors.append("date: must be in YYYY-MM-DD format")
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        errors.append("warnings: must be an array")
    else:
        for i, w in enumerate(warnings):
            _check_text(errors, f"warnings[{i}]", w)
    projects = payload.get("projects")
    if not isinstance(projects, list):
        return errors + ["projects: must be an array"]
    names = set()
    for pi, project in enumerate(projects):
        where = f"projects[{pi}]"
        if not isinstance(project, dict):
            errors.append(f"{where}: must be an object")
            continue
        name = project.get("name")
        _check_text(errors, f"{where}.name", name)
        if isinstance(name, str):
            if name in names:
                errors.append(f"{where}.name: duplicate project name: {name}")
            names.add(name)
        items = project.get("items")
        if not isinstance(items, list):
            errors.append(f"{where}.items: must be an array")
            continue
        for ii, item in enumerate(items):
            errors.extend(_validate_item(item, f"{where}.items[{ii}]", fmt))
    return errors


def _validate_item(item, where: str, fmt: LogFormat) -> list[str]:
    if not isinstance(item, dict):
        return [f"{where}: must be an object"]
    errors: list[str] = []
    if item.get("source") not in fmt.source_headings:
        errors.append(f"{where}.source: must be one of {', '.join(fmt.source_headings)}")
    _check_text(errors, f"{where}.time", item.get("time"))
    _check_text(errors, f"{where}.text", item.get("text"))
    for key in ("feature", "location"):
        _check_text(errors, f"{where}.{key}", item.get(key), required=False)
    links = item.get("links", [])
    if not isinstance(links, list):
        return errors + [f"{where}.links: must be an array"]
    for li, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append(f"{where}.links[{li}]: must be an object")
            continue
        _check_text(errors, f"{where}.links[{li}].label", link.get("label"))
        url = link.get("url")
        if not isinstance(url, str) or not url.startswith(URL_PREFIXES) or any(c.isspace() for c in url):
            errors.append(f"{where}.links[{li}].url: must be an http(s) URL")
    return errors


def render_item(item: dict) -> str:
    parts = []
    if item.get("feature"):
        parts.append(f"`{item['feature']}`")
    body = f"{item['location']} — {item['text']}" if item.get("location") else item["text"]
    parts.append(f"{item['time']} · {body}")
    if item.get("links"):
        parts.append("(" + ", ".join(f"[{l['label']}]({l['url']})" for l in item["links"]) + ")")
    return "- " + " ".join(parts)


def render_day(payload: dict, fmt: LogFormat) -> str | None:
    warnings = payload.get("warnings", [])
    projects = [p for p in payload["projects"] if p["items"]]
    if not warnings and not projects:
        return None
    projects.sort(key=lambda p: p["name"] == fmt.other_project)
    blocks = [day_heading(date.fromisoformat(payload["date"]), fmt)]
    if warnings:
        blocks.append("\n".join(f"> {w}" for w in warnings))
    for project in projects:
        blocks.append(f"### {project['name']}")
        for source, heading in fmt.source_headings.items():
            items = [render_item(i) for i in project["items"] if i["source"] == source]
            if items:
                blocks.append("\n".join([f"#### {heading}", *items]))
    return "\n\n".join(blocks)


def _load_json(source: str):
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        raise InputError(f"cannot read JSON: {e}") from None


def _load_doc(path: Path, fmt: LogFormat) -> MonthDoc | None:
    if not path.exists():
        return None
    try:
        return parse(path.read_text(encoding="utf-8"), fmt)
    except ValueError as e:
        raise DocError(f"cannot parse {path.name}: {e}") from None


def _write_doc(path: Path, doc: MonthDoc, now: datetime) -> None:
    touch(doc, now)
    atomic_write_text(path, serialize(doc))
    if doc.dropped_legacy:
        print(f"legacy candidates section removed from {path}", file=sys.stderr)


def cmd_day(args, cfg: Settings) -> int:
    payload = _load_json(args.json)
    secrets = secret_fields(payload)
    if secrets:
        raise SecretError(secret_message(secrets))
    fmt = log_format(cfg)
    errors = validate_day(payload, fmt)
    if errors:
        raise InputError("\n".join(errors))
    d = date.fromisoformat(payload["date"])
    try:
        load_last(args.state)
    except ValueError as e:
        raise InputError(str(e)) from None
    path = month_file(cfg, d)
    doc = _load_doc(path, fmt)
    section = render_day(payload, fmt)
    now = datetime.now(cfg.tz)
    if doc is None and section is not None:
        doc = new_doc(d, now, fmt)
    if doc is not None:
        if section is None:
            doc.days.pop(d, None)
        else:
            doc.days[d] = section
        _write_doc(path, doc, now)
    record_write(args.state, now, warned=bool(payload.get("warnings")))
    if not payload.get("warnings"):
        mark_complete(args.state, d)
    print(path)
    return EXIT_OK


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError(f"not a valid date: {value} (YYYY-MM-DD)") from None


def _other_rows(section: str, other_heading: str) -> list[dict]:
    rows, inside, source = [], False, None
    for line in section.split("\n"):
        if line.startswith("### "):
            inside = line == other_heading
        elif line.startswith("#### "):
            source = line.removeprefix("#### ")
        elif inside and line.startswith("- "):
            rows.append({"source": source, "line": line})
    return rows


def cmd_others(args, cfg: Settings) -> int:
    d = _parse_date(args.date)
    first = d.replace(day=1)
    window_start = first - timedelta(days=PREVIOUS_MONTH_LOOKBACK_DAYS)
    fmt = log_format(cfg)
    other_heading = f"### {fmt.other_project}"
    rows = []
    for doc in (_load_doc(month_file(cfg, window_start), fmt), _load_doc(month_file(cfg, d), fmt)):
        if doc is None:
            continue
        for day in sorted(doc.days):
            if day >= window_start:
                rows.extend({"date": day.isoformat(), **row} for row in _other_rows(doc.days[day], other_heading))
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return EXIT_OK


def _load_evidence(source: str) -> dict[date, list[str]]:
    evidence = _load_json(source)
    if not isinstance(evidence, list):
        raise InputError("evidence: must be an array")
    by_date: dict[date, list[str]] = {}
    for i, row in enumerate(evidence):
        if not isinstance(row, dict) or not isinstance(row.get("line"), str):
            raise InputError(f"evidence[{i}]: must be an object with a string line")
        try:
            d = date.fromisoformat(row.get("date"))
        except (TypeError, ValueError):
            raise InputError(f"evidence[{i}].date: must be in YYYY-MM-DD format") from None
        lines = by_date.setdefault(d, [])
        if row["line"] not in lines:
            lines.append(row["line"])
    return by_date


def cmd_reclassify(args, cfg: Settings) -> int:
    fmt = log_format(cfg)
    project = args.project.strip()
    if not project or "\n" in project or project == fmt.other_project:
        raise InputError(f"--project must be a registered project name other than {fmt.other_project}")
    by_date = _load_evidence(args.json)
    # Parse every month file first, so a damaged one stops the command before anything is written
    docs: dict[Path, MonthDoc | None] = {}
    for d in by_date:
        path = month_file(cfg, d)
        if path not in docs:
            docs[path] = _load_doc(path, fmt)
    moved, missing, changed = 0, [], set()
    for d in sorted(by_date):
        path = month_file(cfg, d)
        doc = docs[path]
        wanted = by_date[d]
        found: set[str] = set()
        if doc is not None and d in doc.days:
            section, found, count = move_items(doc.days[d], set(wanted), project, fmt.other_project,
                                               list(fmt.source_headings.values()))
            if count:
                doc.days[d] = section
                moved += count
                changed.add(path)
        missing.extend({"date": d.isoformat(), "line": line} for line in wanted if line not in found)
    now = datetime.now(cfg.tz)
    for path in sorted(changed):
        _write_doc(path, docs[path], now)
    print(json.dumps({"moved": moved, "missing": missing}, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_init_project_list(args, cfg: Settings) -> int:
    path = cfg.log_folder / log_format(cfg).project_list_name
    result = {"path": str(path), "created": False, "copiedFrom": None}
    if not path.exists():
        # After a language switch, carry the user's projects over instead of starting from an empty list
        others = (cfg.log_folder / f.project_list_name for lang, f in FORMATS.items() if lang != cfg.log_language)
        source = next((p for p in others if p.exists()), None)
        atomic_write_text(path, source.read_text(encoding="utf-8") if source else f"# {path.stem}\n")
        result.update(created=True, copiedFrom=str(source) if source else None)
    print(json.dumps(result, ensure_ascii=False))
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    day = sub.add_parser("day")
    day.add_argument("--json", required=True)
    day.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    sub.add_parser("others").add_argument("--date", required=True)
    reclassify = sub.add_parser("reclassify")
    reclassify.add_argument("--project", required=True)
    reclassify.add_argument("--json", required=True)
    sub.add_parser("init-project-list")
    for p in sub.choices.values():
        p.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    args = parser.parse_args()

    handlers = {"day": cmd_day, "others": cmd_others, "reclassify": cmd_reclassify,
                "init-project-list": cmd_init_project_list}
    try:
        return handlers[args.command](args, load_settings(args.settings))
    except (InputError, SettingsError) as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    except DocError as e:
        print(e, file=sys.stderr)
        return EXIT_DOC
    except SecretError as e:
        print(e, file=sys.stderr)
        return EXIT_SECRET


if __name__ == "__main__":
    sys.exit(main())
