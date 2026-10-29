"""Per-language strings for the monthly work log (file names, headings, frontmatter text)."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class LogFormat:
    language: str
    weekdays: str | tuple[str, ...]
    source_headings: dict[str, str]
    other_project: str
    project_list_name: str
    tags: tuple[str, ...]

    def month_file_name(self, d: date) -> str:
        if self.language == "ko":
            return f"{d.year}년 {d.month:02d}월 업무 로그.md"
        return f"{d.year}-{d.month:02d} Work Log.md"

    def month_title(self, d: date) -> str:
        return self.month_file_name(d).removesuffix(".md")

    def description(self, d: date) -> str:
        if self.language == "ko":
            return f"{d.year}년 {d.month:02d}월 Claude 세션·Slack 활동·결정 사항 자동 수집 기록"
        return f"Automatically collected record of Claude sessions, Slack activity and decisions for {d.year}-{d.month:02d}"

    def weekday_name(self, d: date) -> str:
        return self.weekdays[d.weekday()]

    def day_heading(self, d: date) -> str:
        return f"## {d.isoformat()} ({self.weekday_name(d)})"


FORMATS: dict[str, LogFormat] = {
    "en": LogFormat(
        language="en",
        weekdays=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
        source_headings={"claude_session": "Claude Sessions", "slack": "Slack",
                         "decision": "Decisions", "needs_confirmation": "Needs Confirmation"},
        other_project="Other",
        project_list_name="Active Projects.md",
        tags=("work-log", "career"),
    ),
    "ko": LogFormat(
        language="ko",
        weekdays="월화수목금토일",
        source_headings={"claude_session": "Claude 세션", "slack": "Slack",
                         "decision": "결정", "needs_confirmation": "확인 필요"},
        other_project="기타",
        project_list_name="진행 중인 프로젝트.md",
        tags=("업무로그", "커리어"),
    ),
}
