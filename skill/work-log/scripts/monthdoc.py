"""Split a monthly work log into frontmatter, title and day sections, and join them back."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from logformat import LogFormat

FRONTMATTER_DELIM = "---"
# Older files may still carry this section; it is accepted on read and dropped on write
LEGACY_CANDIDATES_HEADING = "## 새 프로젝트 후보"
UPDATED_AT_RE = re.compile(r"^updatedAt: .*$", re.M)


@dataclass
class MonthDoc:
    frontmatter: str
    title: str
    days: dict[date, str] = field(default_factory=dict)
    dropped_legacy: bool = False


def day_heading(d: date, fmt: LogFormat) -> str:
    return fmt.day_heading(d)


def _day_heading_re(fmt: LogFormat) -> re.Pattern:
    names = "|".join(re.escape(w) for w in fmt.weekdays)
    return re.compile(rf"^## (\d{{4}}-\d{{2}}-\d{{2}}) \((?:{names})\)$")


def new_doc(d: date, now: datetime, fmt: LogFormat) -> MonthDoc:
    stamp = now.isoformat(timespec="seconds")
    title = fmt.month_title(d)
    frontmatter = "\n".join([
        "type: Area",
        f"title: {title}",
        f"description: {fmt.description(d)}",
        "status: active",
        "tags:",
        *(f"  - {tag}" for tag in fmt.tags),
        f"year: {d.year}",
        f"month: {d.month}",
        f"createdAt: {stamp}",
        f"updatedAt: {stamp}",
    ])
    return MonthDoc(frontmatter=frontmatter, title=f"# {title}")


def touch(doc: MonthDoc, now: datetime) -> None:
    doc.frontmatter = UPDATED_AT_RE.sub(f"updatedAt: {now.isoformat(timespec='seconds')}", doc.frontmatter)


def parse(text: str, fmt: LogFormat) -> MonthDoc:
    lines = text.split("\n")
    if not lines or lines[0] != FRONTMATTER_DELIM or FRONTMATTER_DELIM not in lines[1:]:
        raise ValueError("frontmatter is missing")
    end = lines.index(FRONTMATTER_DELIM, 1)
    title, sections, current = None, [], None
    for line in lines[end + 1:]:
        if line.startswith("## "):
            current = [line]
            sections.append(current)
        elif current is not None:
            current.append(line)
        elif line.startswith("# ") and title is None:
            title = line
        elif line.strip():
            raise ValueError(f"unexpected content before the title: {line}")
    if title is None:
        raise ValueError("document title (# ...) is missing")

    day_re = _day_heading_re(fmt)
    doc = MonthDoc(frontmatter="\n".join(lines[1:end]), title=title)
    for section in sections:
        body = "\n".join(section).rstrip()
        heading = section[0]
        match = day_re.match(heading)
        if heading == LEGACY_CANDIDATES_HEADING:
            doc.dropped_legacy = True
            continue
        if match:
            d = date.fromisoformat(match.group(1))
            if d in doc.days:
                raise ValueError(f"duplicate date section: {heading}")
            doc.days[d] = body
        else:
            raise ValueError(f"unknown section: {heading}")
    return doc


def serialize(doc: MonthDoc) -> str:
    sections = [doc.days[d] for d in sorted(doc.days, reverse=True)]
    head = f"{FRONTMATTER_DELIM}\n{doc.frontmatter}\n{FRONTMATTER_DELIM}\n{doc.title}\n"
    return head + "".join(f"\n{s}\n" for s in sections)
