from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from .dedupe import normalize_doi
from .models import PaperEntry


DIGEST_MARKDOWN_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})-digest(?:-\d+)?\.md$")
MARKDOWN_LINK_RE = re.compile(r"\]\(([^)]+)\)")
ASCII_TITLE_LABEL_RE = re.compile(r"^(?:english|original)\s+(?:paper\s+)?title\s*:\s*", re.IGNORECASE)


def load_recent_output_entries(
    output_dir: str | Path,
    *,
    date_label: str,
    lookback_days: int = 5,
    lookback_files: int = 5,
) -> tuple[list[PaperEntry], list[Path]]:
    files = select_recent_digest_files(
        output_dir,
        date_label=date_label,
        lookback_days=lookback_days,
        lookback_files=lookback_files,
    )
    entries: list[PaperEntry] = []
    for path in files:
        entries.extend(parse_digest_markdown(path))
    return entries, files


def select_recent_digest_files(
    output_dir: str | Path,
    *,
    date_label: str,
    lookback_days: int = 5,
    lookback_files: int = 5,
) -> list[Path]:
    root = Path(output_dir)
    if not root.exists():
        return []

    digest_files = [path for path in root.glob("*-digest*.md") if _digest_date(path) is not None]
    newest_files = sorted(digest_files, key=lambda path: path.stat().st_mtime, reverse=True)
    selected: dict[Path, None] = {}

    if lookback_files > 0:
        for path in newest_files[:lookback_files]:
            selected[path] = None

    current_date = _parse_date(date_label)
    if current_date and lookback_days > 0:
        cutoff = current_date - timedelta(days=lookback_days)
        for path in newest_files:
            file_date = _digest_date(path)
            if file_date and cutoff <= file_date <= current_date:
                selected[path] = None

    return sorted(selected, key=lambda path: path.stat().st_mtime, reverse=True)


def parse_digest_markdown(path: str | Path) -> list[PaperEntry]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    entries: list[PaperEntry] = []
    current: dict[str, object] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            _append_current(entries, current)
            current = {
                "title": _extract_heading_title(line),
                "url": "",
                "doi": "",
                "saw_first_bullet": False,
            }
            continue
        if current is None:
            continue
        if line.startswith("## "):
            _append_current(entries, current)
            current = None
            continue
        if not line.startswith("- "):
            continue

        body = line[2:].strip()
        if not current["saw_first_bullet"]:
            title = _extract_original_title(body)
            if title:
                current["title"] = title
            current["saw_first_bullet"] = True
        if not current["url"]:
            current["url"] = _extract_first_markdown_link(body)
        if not current["doi"]:
            current["doi"] = normalize_doi(body)

    _append_current(entries, current)
    return entries


def _append_current(entries: list[PaperEntry], current: dict[str, object] | None) -> None:
    if not current:
        return
    title = str(current.get("title") or "").strip()
    url = str(current.get("url") or "").strip()
    doi = str(current.get("doi") or "").strip()
    if title or url or doi:
        entries.append(PaperEntry(title=title, url=url, doi=doi, raw_text="historical digest output"))


def _extract_heading_title(line: str) -> str:
    title = line.removeprefix("### ").strip()
    return re.sub(r"^\d+\.\s*", "", title).strip()


def _extract_original_title(body: str) -> str:
    title = re.split(r"\s+\|\s+(?:\[|DOI:)", body, maxsplit=1)[0].strip()
    title = ASCII_TITLE_LABEL_RE.sub("", title).strip()
    if not title:
        return ""

    ascii_start = _first_ascii_title_char(title)
    if ascii_start > 0:
        title = title[ascii_start:].strip()
    return title


def _extract_first_markdown_link(body: str) -> str:
    match = MARKDOWN_LINK_RE.search(body)
    return match.group(1).strip() if match else ""


def _first_ascii_title_char(value: str) -> int:
    for index, char in enumerate(value):
        if char.isascii() and (char.isalnum() or char in "([{\"'"):
            return index
    return 0


def _digest_date(path: Path) -> date | None:
    match = DIGEST_MARKDOWN_RE.search(path.name)
    if not match:
        return None
    return _parse_date(match.group("date"))


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
