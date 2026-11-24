from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


RelevanceLevel = Literal["high", "medium", "low", "off_topic", "irrelevant"]

# Display/ranking order. "off_topic" is a genuine paper outside the user's broad
# field; "irrelevant" is reserved for non-academic or malformed entries.
RELEVANCE_LEVELS: tuple[str, ...] = ("high", "medium", "low", "off_topic", "irrelevant")
RELEVANCE_LABELS: dict[str, str] = {
    "high": "高相关", "medium": "中相关", "low": "低相关", "off_topic": "领域外", "irrelevant": "不相关",
}


@dataclass(slots=True)
class EmailMessage:
    id: str
    thread_id: str
    subject: str
    sender: str
    date: datetime | None
    html: str = ""
    text: str = ""
    snippet: str = ""
    labels: list[str] = field(default_factory=list)
    image_paths: list[Path | str] = field(default_factory=list)


@dataclass(slots=True)
class SkippedEmail:
    email_id: str
    subject: str
    sender: str
    reason: str


@dataclass(slots=True)
class PaperEntry:
    title: str
    url: str = ""
    authors: str = ""
    venue: str = ""
    abstract: str = ""
    doi: str = ""
    source_email_id: str = ""
    source_subject: str = ""
    source_sender: str = ""
    image_paths: list[Path | str] = field(default_factory=list)
    raw_text: str = ""


@dataclass(slots=True)
class DeduplicationResult:
    unique_entries: list[PaperEntry]
    duplicates_removed: int


@dataclass(slots=True)
class InterestProfile:
    current_projects: list[str] = field(default_factory=list)
    material_systems: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    high_priority_topics: list[str] = field(default_factory=list)
    medium_priority_topics: list[str] = field(default_factory=list)
    deprioritized_topics: list[str] = field(default_factory=list)
    broad_fields: list[str] = field(default_factory=list)
    summary_zh: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvidenceRecord:
    """Identity-matched source abstract; retained separately from original email data."""
    abstract: str
    source_url: str
    source_kind: str
    fetched_at: str
    matched_by: str
    identity: str


@dataclass(slots=True)
class RankedPaper:
    entry: PaperEntry
    relevance: RelevanceLevel
    score: float
    title_zh: str
    summary_zh: str
    reason_zh: str
    matched_topics: list[str] = field(default_factory=list)
    evidence: EvidenceRecord | None = None


@dataclass(slots=True)
class RunStats:
    emails_read: int = 0
    skipped_emails: int = 0
    paper_entries_extracted: int = 0
    duplicates_removed: int = 0
    high_relevance: int = 0
    medium_relevance: int = 0
    low_relevance: int = 0
    off_topic: int = 0
    irrelevant: int = 0
    sample_mode: bool = False


@dataclass(slots=True)
class DigestRun:
    date_label: str
    stats: RunStats
    interest_profile: InterestProfile
    papers: list[RankedPaper]
    skipped: list[SkippedEmail] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
