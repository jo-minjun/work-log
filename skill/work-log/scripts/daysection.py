"""Split one day section into projects and subsections, move fallback-project items, and join it back.

Re-rendering a section written by write_day.py gives the same text; only days that change are rewritten.
"""

import re
from dataclasses import dataclass, field

PROJECT_PREFIX = "### "
SUBSECTION_PREFIX = "#### "
# The item's start time: "- `Feature` 10:05–11:20 · ..." or "- 14:43 · ..."
ITEM_TIME_RE = re.compile(r"^- (?:`[^`]*` )?(\d{2}:\d{2})")


@dataclass
class Project:
    name: str
    intro: list[str] = field(default_factory=list)
    subsections: list[tuple[str, list[str]]] = field(default_factory=list)

    def subsection(self, heading: str, order: list[str]) -> list[str]:
        for name, lines in self.subsections:
            if name == heading:
                return lines
        lines: list[str] = []
        rank = {h: i for i, h in enumerate(order)}
        pos = len(self.subsections)
        if heading in rank:
            pos = next((i for i, (name, _) in enumerate(self.subsections)
                        if rank.get(name, len(order)) > rank[heading]), pos)
        self.subsections.insert(pos, (heading, lines))
        return lines

    def is_empty(self) -> bool:
        return not any(line.strip() for line in self.intro) and not self.subsections


@dataclass
class DaySection:
    heading: str
    preamble: list[str]
    projects: list[Project]


def split(section: str) -> DaySection:
    lines = section.split("\n")
    day = DaySection(heading=lines[0], preamble=[], projects=[])
    project, sub = None, None
    for line in lines[1:]:
        if line.startswith(PROJECT_PREFIX):
            project, sub = Project(line.removeprefix(PROJECT_PREFIX)), None
            day.projects.append(project)
        elif project is None:
            day.preamble.append(line)
        elif line.startswith(SUBSECTION_PREFIX):
            sub = []
            project.subsections.append((line.removeprefix(SUBSECTION_PREFIX), sub))
        elif sub is None:
            project.intro.append(line)
        else:
            sub.append(line)
    return day


def join(day: DaySection) -> str:
    blocks = [day.heading]
    preamble = "\n".join(day.preamble).strip("\n")
    if preamble:
        blocks.append(preamble)
    for project in day.projects:
        blocks.append(f"{PROJECT_PREFIX}{project.name}")
        intro = "\n".join(project.intro).strip("\n")
        if intro:
            blocks.append(intro)
        for heading, lines in project.subsections:
            blocks.append("\n".join([f"{SUBSECTION_PREFIX}{heading}", *(l for l in lines if l.strip())]))
    return "\n\n".join(blocks)


def _insert_in_time_order(lines: list[str], line: str) -> None:
    match = ITEM_TIME_RE.match(line)
    if not match:
        lines.append(line)
        return
    pos = len(lines)
    for i, existing in enumerate(lines):
        other = ITEM_TIME_RE.match(existing)
        if other and other.group(1) > match.group(1):
            pos = i
            break
    lines.insert(pos, line)


def move_items(section: str, wanted: set[str], target: str, fallback: str,
               heading_order: list[str]) -> tuple[str, set[str], int]:
    """Move fallback-project items whose line is in `wanted` into project `target`.

    Returns the new section, the wanted lines that were found, and how many lines moved.
    """
    day = split(section)
    source = next((p for p in day.projects if p.name == fallback), None)
    if source is None:
        return section, set(), 0
    moving: list[tuple[str, str]] = []
    for heading, lines in source.subsections:
        moving.extend((heading, l) for l in lines if l in wanted)
        lines[:] = [l for l in lines if l not in wanted]
    if not moving:
        return section, set(), 0
    dest = next((p for p in day.projects if p.name == target), None)
    if dest is None:
        dest = Project(target)
        day.projects.insert(day.projects.index(source), dest)
    for heading, line in moving:
        _insert_in_time_order(dest.subsection(heading, heading_order), line)
    source.subsections = [(h, ls) for h, ls in source.subsections if any(l.strip() for l in ls)]
    day.projects = [p for p in day.projects if not (p is source and p.is_empty())]
    day.projects.sort(key=lambda p: p.name == fallback)
    return join(day), {line for _, line in moving}, len(moving)
