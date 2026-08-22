from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .dedupe import (
    canonicalize_url,
    extract_entry_dois,
    fuzzy_title_match_score,
    informative_title_tokens,
    normalize_title,
)
from .models import PaperEntry
from .recent_outputs import parse_digest_markdown, select_recent_digest_files


REGISTRY_VERSION = 1
ARXIV_RE = re.compile(
    r"(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)"
    r"(?P<id>(?:[a-z-]+/\d{7}|\d{4}\.\d{4,5}))(?:v\d+)?",
    re.IGNORECASE,
)
MAX_ALIASES = 12
MAX_SOURCES = 20


class PaperRegistryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RegistryMatch:
    paper_id: str
    reason: str
    score: float | None = None


@dataclass(slots=True)
class RegistryFilterResult:
    unique_entries: list[PaperEntry]
    duplicates_removed: int
    reasons: dict[str, int] = field(default_factory=dict)


class PaperRegistry:
    def __init__(
        self,
        path: str | Path,
        *,
        retention_days: int = 30,
        fuzzy_title_threshold: float = 94.0,
        papers: dict[str, dict[str, Any]] | None = None,
        loaded_from_disk: bool = False,
    ) -> None:
        self.path = Path(path)
        self.retention_days = max(1, retention_days)
        self.fuzzy_title_threshold = max(0.0, min(float(fuzzy_title_threshold), 100.0))
        self.papers: dict[str, dict[str, Any]] = papers or {}
        self.loaded_from_disk = loaded_from_disk
        self._doi_index: dict[str, str] = {}
        self._arxiv_index: dict[str, str] = {}
        self._url_index: dict[str, str] = {}
        self._title_index: dict[str, set[str]] = defaultdict(set)
        self._token_index: dict[str, set[str]] = defaultdict(set)
        self._rebuild_indexes()

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        reference_date: date,
        retention_days: int = 30,
        fuzzy_title_threshold: float = 94.0,
    ) -> PaperRegistry:
        registry_path = Path(path)
        if not registry_path.exists():
            return cls(
                registry_path,
                retention_days=retention_days,
                fuzzy_title_threshold=fuzzy_title_threshold,
            )
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PaperRegistryError(f"Could not read paper registry {registry_path}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("version") != REGISTRY_VERSION:
            raise PaperRegistryError(
                f"Unsupported paper registry format in {registry_path}; expected version {REGISTRY_VERSION}."
            )
        papers = payload.get("papers")
        if not isinstance(papers, dict):
            raise PaperRegistryError(f"Paper registry has invalid 'papers' data: {registry_path}")
        registry = cls(
            registry_path,
            retention_days=retention_days,
            fuzzy_title_threshold=fuzzy_title_threshold,
            papers={str(key): value for key, value in papers.items() if isinstance(value, dict)},
            loaded_from_disk=True,
        )
        registry.prune(reference_date)
        return registry

    def prune(self, reference_date: date) -> int:
        cutoff = reference_date - timedelta(days=self.retention_days)
        expired: list[str] = []
        for paper_id, record in self.papers.items():
            last_seen = _parse_date(record.get("last_seen"))
            if last_seen is None or last_seen < cutoff:
                expired.append(paper_id)
        for paper_id in expired:
            del self.papers[paper_id]
        if expired:
            self._rebuild_indexes()
        return len(expired)

    def filter_new(self, entries: list[PaperEntry]) -> RegistryFilterResult:
        unique: list[PaperEntry] = []
        reasons: Counter[str] = Counter()
        for entry in entries:
            match = self.find_match(entry)
            if match is None:
                unique.append(entry)
                continue
            reasons[match.reason] += 1
        return RegistryFilterResult(
            unique_entries=unique,
            duplicates_removed=sum(reasons.values()),
            reasons=dict(sorted(reasons.items())),
        )

    def find_match(self, entry: PaperEntry) -> RegistryMatch | None:
        for doi in _entry_dois(entry):
            paper_id = self._doi_index.get(doi)
            if paper_id:
                return RegistryMatch(paper_id=paper_id, reason="doi")
        for arxiv_id in _entry_arxiv_ids(entry):
            paper_id = self._arxiv_index.get(arxiv_id)
            if paper_id:
                return RegistryMatch(paper_id=paper_id, reason="arxiv")
        url = canonicalize_url(entry.url)
        if url and url in self._url_index:
            return RegistryMatch(paper_id=self._url_index[url], reason="url")

        title = normalize_title(entry.title)
        if not title:
            return None
        exact_ids = self._title_index.get(title)
        if exact_ids:
            return RegistryMatch(paper_id=_newest_record_id(exact_ids, self.papers), reason="exact_title")

        best: RegistryMatch | None = None
        for paper_id in self._fuzzy_candidates(title):
            record = self.papers[paper_id]
            for alias in _string_list(record.get("title_aliases")):
                normalized_alias = normalize_title(alias)
                score = fuzzy_title_match_score(title, normalized_alias)
                if score is None or score < self.fuzzy_title_threshold:
                    continue
                if best is None or score > (best.score or 0.0):
                    best = RegistryMatch(paper_id=paper_id, reason="fuzzy_title", score=score)
        return best

    def record_entries(self, entries: list[PaperEntry], *, seen_on: date) -> None:
        for entry in entries:
            match = self.find_match(entry)
            if match is None:
                paper_id = self._new_paper_id(entry)
                record = _new_record(entry, seen_on)
                if record is None:
                    continue
                self.papers[paper_id] = record
            else:
                paper_id = match.paper_id
                record = self.papers[paper_id]
                _update_record(record, entry, seen_on)
            self._index_record(paper_id, record)

    def save(self, *, reference_date: date) -> None:
        self.prune(reference_date)
        payload = {
            "version": REGISTRY_VERSION,
            "retention_days": self.retention_days,
            "updated_at": reference_date.isoformat(),
            "papers": dict(sorted(self.papers.items())),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise PaperRegistryError(f"Could not write paper registry {self.path}: {exc}") from exc

    def _new_paper_id(self, entry: PaperEntry) -> str:
        identity = (
            next(iter(_entry_dois(entry)), "")
            or next(iter(_entry_arxiv_ids(entry)), "")
            or normalize_title(entry.title)
            or canonicalize_url(entry.url)
        )
        base = "paper-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        paper_id = base
        suffix = 2
        while paper_id in self.papers:
            paper_id = f"{base}-{suffix}"
            suffix += 1
        return paper_id

    def _fuzzy_candidates(self, normalized_title: str) -> set[str]:
        tokens = informative_title_tokens(normalized_title)
        if len(tokens) < 4:
            return set()
        counts: Counter[str] = Counter()
        for token in tokens:
            counts.update(self._token_index.get(token, set()))
        minimum_shared = max(2, min(4, len(tokens) // 3))
        return {paper_id for paper_id, count in counts.items() if count >= minimum_shared}

    def _rebuild_indexes(self) -> None:
        self._doi_index.clear()
        self._arxiv_index.clear()
        self._url_index.clear()
        self._title_index.clear()
        self._token_index.clear()
        for paper_id, record in self.papers.items():
            self._index_record(paper_id, record)

    def _index_record(self, paper_id: str, record: dict[str, Any]) -> None:
        for doi in _string_list(record.get("dois")):
            self._doi_index.setdefault(doi, paper_id)
        for arxiv_id in _string_list(record.get("arxiv_ids")):
            self._arxiv_index.setdefault(arxiv_id, paper_id)
        for url in _string_list(record.get("urls")):
            self._url_index.setdefault(url, paper_id)
        aliases = _string_list(record.get("title_aliases"))
        canonical_title = str(record.get("canonical_title") or "").strip()
        if canonical_title and canonical_title not in aliases:
            aliases.append(canonical_title)
        for alias in aliases:
            normalized = normalize_title(alias)
            if not normalized:
                continue
            self._title_index[normalized].add(paper_id)
            for token in informative_title_tokens(normalized):
                self._token_index[token].add(paper_id)


def bootstrap_registry_from_markdown(
    registry: PaperRegistry,
    output_dir: str | Path,
    *,
    reference_date: date,
) -> tuple[int, int]:
    files = select_recent_digest_files(
        output_dir,
        date_label=reference_date.isoformat(),
        lookback_days=registry.retention_days,
        lookback_files=0,
    )
    entry_count = 0
    for path in sorted(files, key=lambda item: item.name):
        seen_on = _date_from_digest_name(path) or reference_date
        entries = parse_digest_markdown(path)
        registry.record_entries(entries, seen_on=seen_on)
        entry_count += len(entries)
    registry.prune(reference_date)
    return len(files), entry_count


def extract_arxiv_ids(*values: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for match in ARXIV_RE.finditer(value or ""):
            identifier = match.group("id").casefold()
            if identifier not in seen:
                seen.add(identifier)
                result.append(identifier)
    return result


def _entry_dois(entry: PaperEntry) -> list[str]:
    return extract_entry_dois(entry)


def _entry_arxiv_ids(entry: PaperEntry) -> list[str]:
    direct = extract_arxiv_ids(entry.doi, entry.url, entry.title)
    if direct:
        return direct
    contextual = extract_arxiv_ids(entry.abstract, entry.raw_text)
    return contextual if len(contextual) == 1 else []


def _new_record(entry: PaperEntry, seen_on: date) -> dict[str, Any] | None:
    title = entry.title.strip()
    dois = _entry_dois(entry)
    arxiv_ids = _entry_arxiv_ids(entry)
    url = canonicalize_url(entry.url)
    if not (title or dois or arxiv_ids or url):
        return None
    return {
        "canonical_title": title,
        "title_aliases": [title] if title else [],
        "dois": dois,
        "arxiv_ids": arxiv_ids,
        "urls": [url] if url else [],
        "authors": [entry.authors.strip()] if entry.authors.strip() else [],
        "venues": [entry.venue.strip()] if entry.venue.strip() else [],
        "source_subjects": [entry.source_subject.strip()] if entry.source_subject.strip() else [],
        "source_senders": [entry.source_sender.strip()] if entry.source_sender.strip() else [],
        "first_seen": seen_on.isoformat(),
        "last_seen": seen_on.isoformat(),
        "seen_count": 1,
    }


def _update_record(record: dict[str, Any], entry: PaperEntry, seen_on: date) -> None:
    title = entry.title.strip()
    _extend_unique(record, "title_aliases", [title] if title else [], MAX_ALIASES)
    _extend_unique(record, "dois", _entry_dois(entry), MAX_ALIASES)
    _extend_unique(record, "arxiv_ids", _entry_arxiv_ids(entry), MAX_ALIASES)
    url = canonicalize_url(entry.url)
    _extend_unique(record, "urls", [url] if url else [], MAX_ALIASES)
    _extend_unique(record, "authors", [entry.authors.strip()] if entry.authors.strip() else [], MAX_ALIASES)
    _extend_unique(record, "venues", [entry.venue.strip()] if entry.venue.strip() else [], MAX_ALIASES)
    _extend_unique(
        record,
        "source_subjects",
        [entry.source_subject.strip()] if entry.source_subject.strip() else [],
        MAX_SOURCES,
    )
    _extend_unique(
        record,
        "source_senders",
        [entry.source_sender.strip()] if entry.source_sender.strip() else [],
        MAX_SOURCES,
    )
    first_seen = _parse_date(record.get("first_seen"))
    last_seen = _parse_date(record.get("last_seen"))
    record["first_seen"] = min(first_seen or seen_on, seen_on).isoformat()
    record["last_seen"] = max(last_seen or seen_on, seen_on).isoformat()
    record["seen_count"] = max(0, _as_int(record.get("seen_count"))) + 1
    if not str(record.get("canonical_title") or "").strip() and title:
        record["canonical_title"] = title


def _extend_unique(record: dict[str, Any], key: str, values: list[str], limit: int) -> None:
    current = _string_list(record.get(key))
    seen = {value.casefold() for value in current}
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned.casefold() in seen:
            continue
        current.append(cleaned)
        seen.add(cleaned.casefold())
    record[key] = current[-limit:]


def _newest_record_id(paper_ids: set[str], papers: dict[str, dict[str, Any]]) -> str:
    return max(paper_ids, key=lambda paper_id: str(papers[paper_id].get("last_seen") or ""))


def _date_from_digest_name(path: Path) -> date | None:
    return _parse_date(path.name[:10])


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
