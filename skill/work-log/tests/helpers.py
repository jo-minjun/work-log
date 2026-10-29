import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from settings import Settings  # noqa: E402

TEST_TZ = "Asia/Seoul"


def make_settings(tmp: Path, include: list[Path], language: str = "ko") -> Settings:
    return Settings(
        log_folder=tmp / "out",
        log_language=language,
        session_folders=include,
        provider="claude",
        slack_user_id="U0TEST",
        tz=ZoneInfo(TEST_TZ),
    )


def write_settings_json(tmp: Path, include: list[Path], language: str = "ko") -> Path:
    path = tmp / "settings.json"
    path.write_text(
        json.dumps({
            "logFolder": str(tmp / "out"),
            "logLanguage": language,
            "sessionFolders": [str(p) for p in include],
            "slack": {"userId": "U0TEST"},
        }),
        encoding="utf-8",
    )
    return path


def cli_env(tmp: Path) -> dict:
    """Environment for spawned CLIs: isolated data dir and a fixed time zone."""
    return {**os.environ, "WORKLOG_HOME": str(tmp / "home"), "TZ": TEST_TZ}
