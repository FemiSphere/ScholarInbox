from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import EmailMessage


ACADEMIC_SIGNALS = (
    "doi",
    "journal",
    "article",
    "research",
    "publication",
    "google scholar",
    "scholar alert",
    "table of contents",
    "toc",
    "arxiv",
    "sciencedirect",
    "springer",
    "wiley",
    "acs",
    "rsc",
    "nature",
    "science",
    "elsevier",
    "mdpi",
    "学术",
    "學術",
    "期刊",
    "论文",
)

# Senders whose mail is always a paper alert; these are parsed locally and must
# never be dropped by keyword heuristics (paper titles can contain "sale" etc.).
TRUSTED_ALERT_SENDERS = (
    "scholaralerts-noreply@google.com",
)


@dataclass(slots=True)
class FilterDecision:
    skip: bool
    reason: str = ""


def classify_email(email: EmailMessage, config: dict[str, Any]) -> FilterDecision:
    filtering = config["filtering"]
    sender_lower = email.sender.lower()
    subject_lower = email.subject.lower()
    searchable = " ".join([sender_lower, subject_lower, email.snippet.lower(), email.text[:2000].lower()])

    for blocked in filtering.get("sender_blocklist", []):
        if blocked.lower() in sender_lower:
            return FilterDecision(True, f"sender blocklist: {blocked}")

    if any(sender in sender_lower for sender in TRUSTED_ALERT_SENDERS):
        return FilterDecision(False)

    for allowed in filtering.get("academic_sender_allowlist", []):
        if allowed.lower() in sender_lower:
            return FilterDecision(False)

    if not filtering.get("skip_promotional", True):
        return FilterDecision(False)

    has_academic_signal = any(signal in searchable for signal in ACADEMIC_SIGNALS)
    matched_keywords = [
        keyword
        for keyword in filtering.get("promotional_keywords", [])
        if _contains_keyword(searchable, keyword)
    ]

    if matched_keywords and not has_academic_signal:
        return FilterDecision(True, "promotional keywords: " + ", ".join(matched_keywords[:3]))

    if _contains_keyword(searchable, "unsubscribe") and any(
        _contains_keyword(searchable, word) for word in ("coupon", "deal", "save", "buy now")
    ):
        return FilterDecision(True, "marketing unsubscribe pattern")

    return FilterDecision(False)



def _contains_keyword(text: str, keyword: str) -> bool:
    """Whole-word match for ASCII keywords; substring match for CJK keywords.

    Plain substring matching made "sale" hit "wholesale" or "Salen", which
    skipped real Google Scholar alerts on every run.
    """
    keyword = keyword.lower().strip()
    if not keyword:
        return False
    if keyword.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text
