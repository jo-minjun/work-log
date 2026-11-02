#!/usr/bin/env python3
"""Read and update the WorkLog settings file (settings.json).

Usage: settings.py show [--settings PATH]   (scheduleEnabled and other app-owned keys are ignored)
       settings.py set-slack --user-id ID --display-name NAME [--settings PATH]

Exit codes: 0 success, 2 invalid settings
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fsutil import atomic_write_text

DATA_DIR = Path(os.environ.get("WORKLOG_HOME") or "~/Library/Application Support/WorkLog").expanduser()
DEFAULT_SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_LOG_FOLDER = "~/WorkLog"
LOG_LANGUAGES = ("en", "ko")
PROVIDERS = ("claude", "codex")
ZONEINFO_MARKER = "zoneinfo/"
LOCALTIME_PATH = "/etc/localtime"
FALLBACK_TZ = "UTC"

EXIT_OK, EXIT_SETTINGS = 0, 2


class SettingsError(Exception):
    pass


@dataclass(frozen=True)
class DailySettings:
    github_accounts: list[str] = field(default_factory=list)
    github_owners: list[str] = field(default_factory=list)
    standup_channel: str | None = None
    jira_mcp_server: str | None = None


@dataclass(frozen=True)
class Settings:
    log_folder: Path
    log_language: str
    session_folders: list[Path]
    provider: str
    slack_user_id: str | None
    tz: ZoneInfo
    # run.sh creates only the default folder when it is missing; a folder the user chose must already exist
    log_folder_is_default: bool = False
    daily: DailySettings = field(default_factory=DailySettings)


def system_timezone() -> ZoneInfo:
    name = os.environ.get("TZ")
    if not name:
        resolved = os.path.realpath(LOCALTIME_PATH)
        name = resolved.split(ZONEINFO_MARKER, 1)[1] if ZONEINFO_MARKER in resolved else FALLBACK_TZ
    try:
        return ZoneInfo(name)
    except (ValueError, OSError, LookupError):
        # ZoneInfoNotFoundError subclasses LookupError
        return ZoneInfo(FALLBACK_TZ)


def _read_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SettingsError(f"Cannot read settings.json ({path}): {e}") from None
    if not isinstance(data, dict):
        raise SettingsError(f"settings.json must contain a JSON object ({path})")
    return data


def _typed(raw: dict, key: str, kind: type, default):
    value = raw.get(key, default)
    if value is None:
        return default
    if not isinstance(value, kind):
        raise SettingsError(f"settings.json: {key} must be {kind.__name__}")
    return value


def _string_list(raw: dict, key: str, where: str) -> list[str]:
    value = _typed(raw, key, list, [])
    if not all(isinstance(v, str) for v in value):
        raise SettingsError(f"settings.json: {where} must be a list of strings")
    return value


def _optional_string(raw: dict, key: str, where: str) -> str | None:
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        raise SettingsError(f"settings.json: {where} must be str")
    return value or None


def _load_daily(raw: dict) -> DailySettings:
    daily = _typed(raw, "daily", dict, {})
    return DailySettings(
        github_accounts=_string_list(daily, "githubAccounts", "daily.githubAccounts"),
        github_owners=_string_list(daily, "githubOwners", "daily.githubOwners"),
        standup_channel=_optional_string(daily, "standupChannel", "daily.standupChannel"),
        jira_mcp_server=_optional_string(daily, "jiraMcpServer", "daily.jiraMcpServer"),
    )


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> Settings:
    raw = _read_raw(path)
    language = _typed(raw, "logLanguage", str, "en")
    provider = _typed(raw, "provider", str, "claude")
    if language not in LOG_LANGUAGES:
        raise SettingsError(f"settings.json: logLanguage must be one of {', '.join(LOG_LANGUAGES)}")
    if provider not in PROVIDERS:
        raise SettingsError(f"settings.json: provider must be one of {', '.join(PROVIDERS)}")
    folders = _typed(raw, "sessionFolders", list, [])
    if not all(isinstance(f, str) for f in folders):
        raise SettingsError("settings.json: sessionFolders must be a list of strings")
    slack = _typed(raw, "slack", dict, {})
    user_id = slack.get("userId")
    if user_id is not None and not isinstance(user_id, str):
        raise SettingsError("settings.json: slack.userId must be str")
    log_folder = Path(_typed(raw, "logFolder", str, DEFAULT_LOG_FOLDER)).expanduser()
    return Settings(
        log_folder=log_folder,
        log_language=language,
        session_folders=[Path(f).expanduser() for f in folders],
        provider=provider,
        slack_user_id=user_id,
        tz=system_timezone(),
        log_folder_is_default=log_folder == Path(DEFAULT_LOG_FOLDER).expanduser(),
        daily=_load_daily(raw),
    )


def set_slack(path: Path, user_id: str, display_name: str, now: datetime) -> None:
    raw = _read_raw(path)
    raw["slack"] = {
        "userId": user_id,
        "displayName": display_name,
        "checkedAt": now.isoformat(timespec="seconds"),
    }
    atomic_write_text(path, json.dumps(raw, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    slack = sub.add_parser("set-slack")
    slack.add_argument("--user-id", required=True)
    slack.add_argument("--display-name", required=True)
    for p in sub.choices.values():
        p.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_PATH)
    args = parser.parse_args()
    try:
        if args.command == "show":
            s = load_settings(args.settings)
            print(json.dumps({
                "logFolder": str(s.log_folder),
                "logFolderIsDefault": s.log_folder_is_default,
                "logLanguage": s.log_language,
                "sessionFolders": [str(p) for p in s.session_folders],
                "provider": s.provider,
                "slackUserId": s.slack_user_id,
                "daily": {
                    "githubAccounts": s.daily.github_accounts,
                    "githubOwners": s.daily.github_owners,
                    "standupChannel": s.daily.standup_channel,
                    "jiraMcpServer": s.daily.jira_mcp_server,
                },
            }, ensure_ascii=False, indent=2))
        else:
            set_slack(args.settings, args.user_id, args.display_name, datetime.now(system_timezone()))
    except SettingsError as e:
        print(e, file=sys.stderr)
        return EXIT_SETTINGS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
