"""Free scholarly-metadata lookups (Crossref, OpenAlex) for identity-matched abstracts.

Tried before the paid DeepSeek Search/Fetch path. A 2026-11-25 probe on 48 high/medium
papers found an abstract for 40 through these APIs, versus roughly 25-50% from page fetching
(publisher pages often refuse automated access). Elsevier does not deposit abstracts, so
ScienceDirect papers still fall through to Search.

Only the DOI and title of a paper are sent; the User-Agent is generic and carries no personal
contact data. Responses stay in memory; only the resulting EvidenceRecord may be cached.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from rapidfuzz import fuzz

from .llm.base import current_llm_deadline
from .web_evidence import EvidenceUnavailable, _doi_key

USER_AGENT = "ScholarInbox/0.2 (literature digest; +https://github.com/FemiSphere/ScholarInbox)"
_PII = re.compile(r"/pii/([A-Z0-9]{10,24})", re.I)
# Preprint servers whose DOIs are not journal versions.
_PREPRINT_DOI_PREFIXES = ("10.48550/", "10.26434/", "10.21203/", "10.1101/", "10.20944/", "10.31219/")
_HOST_INTERVAL = {"api.crossref.org": 0.25, "api.openalex.org": 0.15}


@dataclass
class ScholarlyClient:
    """Bounded JSON GET client shared by enrichment workers."""
    metrics: Any = None
    timeout_seconds: float = 10
    max_requests: int = 300
    max_response_bytes: int = 2_000_000
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _count: int = field(default=0, init=False)
    _next: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def _event(self, name: str, **fields: Any) -> None:
        if self.metrics is not None:
            self.metrics.event(name, **fields)

    def get_json(self, url: str) -> dict[str, Any] | None:
        """Return decoded JSON, or None for 404. Raises EvidenceUnavailable on other failures."""
        host = urllib.parse.urlsplit(url).hostname or ""
        deadline = current_llm_deadline()
        with self._lock:
            if self._count >= self.max_requests:
                raise EvidenceUnavailable("request_limit")
            self._count += 1
            wait = max(0.0, self._next.get(host, 0.0) - time.monotonic())
            self._next[host] = max(time.monotonic(), self._next.get(host, 0.0)) + _HOST_INTERVAL.get(host, 0.2)
        if wait:
            time.sleep(wait)
        timeout = self.timeout_seconds
        if deadline is not None:
            timeout = min(timeout, deadline - time.perf_counter())
            if timeout <= 0:
                raise EvidenceUnavailable("budget_exhausted")
        started = time.monotonic()
        status = "ok"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                status = "response_too_large"
                raise EvidenceUnavailable(status)
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            return payload if isinstance(payload, dict) else None
        except urllib.error.HTTPError as exc:
            status = f"http_{exc.code}"
            exc.close()
            if exc.code == 404:
                return None
            raise EvidenceUnavailable(status) from None
        except (json.JSONDecodeError, UnicodeError, ValueError):
            status = "invalid_response"
            raise EvidenceUnavailable(status) from None
        except OSError as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            status = "timeout" if isinstance(reason, TimeoutError) else "network_error"
            raise EvidenceUnavailable(status) from None
        finally:
            self._event("scholarly_request_finished", host=host, status=status,
                        elapsed_seconds=round(time.monotonic() - started, 3))


# ----------------------------------------------------------------- helpers

def _clean_abstract(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"^\s*(?:abstract|summary)\s*[:.]?\s*", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _from_inverted_index(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions = []
    for word, places in index.items():
        if isinstance(places, list):
            positions.extend((place, word) for place in places if isinstance(place, int))
    return " ".join(word for _, word in sorted(positions))


def _norm_title(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"[…]|\.\.\.$", " ", text)
    return " ".join(re.findall(r"\w+", text.casefold()))


def titles_match(expected: str, candidate: str, *, strict: bool) -> bool:
    """Strict for title-search hits; lenient (truncated email titles) when a DOI already matches."""
    left, right = _norm_title(expected), _norm_title(candidate)
    if not left or not right:
        return False
    if left == right:
        return True
    score = fuzz.token_sort_ratio(left, right)
    if strict:
        return score >= 93 and len(left.split()) >= 4
    # Alert emails often truncate long titles; accept a clear prefix as well.
    shorter, longer = sorted((left, right), key=len)
    return score >= 85 or (len(shorter.split()) >= 5 and longer.startswith(shorter))


def _usable(abstract: str, max_chars: int) -> bool:
    return 80 <= len(abstract) <= max_chars and len(abstract.split()) >= 12


def _kind_for(doi: str, work_type: str) -> str:
    if doi.startswith(_PREPRINT_DOI_PREFIXES) or work_type in {"posted-content", "preprint"}:
        return "preprint_abstract"
    return "publisher_abstract"


def _record(abstract: str, doi: str, kind: str, matched_by: str):
    from .models import EvidenceRecord
    return EvidenceRecord(abstract=abstract, source_url="https://doi.org/" + doi, source_kind=kind,
                          fetched_at=datetime.now(timezone.utc).isoformat(), matched_by=matched_by, identity=doi)


# ----------------------------------------------------------------- lookups

def _crossref_work(client: ScholarlyClient, doi: str) -> dict[str, Any] | None:
    payload = client.get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/"))
    message = (payload or {}).get("message")
    return message if isinstance(message, dict) else None


def _openalex_work(client: ScholarlyClient, doi: str) -> dict[str, Any] | None:
    return client.get_json("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="/"))


def _doi_from_pii(client: ScholarlyClient, pii: str, title: str) -> str:
    payload = client.get_json("https://api.crossref.org/works?rows=2&filter=alternative-id:" + urllib.parse.quote(pii))
    for item in ((payload or {}).get("message") or {}).get("items", []) or []:
        if isinstance(item, dict) and titles_match(title, (item.get("title") or [""])[0], strict=False):
            return str(item.get("DOI", "")).casefold()
    return ""


def _search_by_title(client: ScholarlyClient, title: str, max_chars: int):
    """Return (doi, abstract, kind) from a strict title match, or ("", "", "")."""
    query = urllib.parse.quote(title[:250])
    payload = client.get_json(f"https://api.openalex.org/works?per-page=3&search={query}")
    for work in (payload or {}).get("results", []) or []:
        if not isinstance(work, dict) or not titles_match(title, work.get("title") or "", strict=True):
            continue
        doi = str(work.get("doi") or "").replace("https://doi.org/", "").casefold()
        abstract = _clean_abstract(_from_inverted_index(work.get("abstract_inverted_index")))
        if doi:
            return doi, abstract if _usable(abstract, max_chars) else "", _kind_for(doi, str(work.get("type", "")))
    payload = client.get_json(f"https://api.crossref.org/works?rows=3&query.bibliographic={query}")
    for item in ((payload or {}).get("message") or {}).get("items", []) or []:
        if isinstance(item, dict) and titles_match(title, (item.get("title") or [""])[0], strict=True):
            doi = str(item.get("DOI", "")).casefold()
            abstract = _clean_abstract(item.get("abstract", ""))
            return doi, abstract if _usable(abstract, max_chars) else "", _kind_for(doi, str(item.get("type", "")))
    return "", "", ""


def acquire_from_metadata(entry: Any, client: ScholarlyClient, *, max_chars: int = 12000):
    """Identity-matched abstract from Crossref/OpenAlex, or None. Raises only budget/limit errors."""
    title = str(getattr(entry, "title", "") or "")
    url = str(getattr(entry, "url", "") or "")
    via = ""
    try:
        doi = _doi_key(str(getattr(entry, "doi", "") or ""))
        matched_by = "doi"
        if not doi:
            doi = _doi_key(urllib.parse.unquote(url))
            doi = re.sub(r"/(?:abstract|full|pdf|epdf|html)$", "", doi)
        if not doi:
            pii = _PII.search(url)
            if pii:
                doi = _doi_from_pii(client, pii.group(1), title)
        if not doi:
            doi, abstract, kind = _search_by_title(client, title, max_chars)
            matched_by = "title"
            if abstract:
                via = "openalex_title"
                return _record(abstract, doi, kind, matched_by)
        if not doi:
            return None
        strict = matched_by == "title"
        work = _crossref_work(client, doi)
        if work and titles_match(title, (work.get("title") or [""])[0], strict=strict):
            abstract = _clean_abstract(work.get("abstract", ""))
            if _usable(abstract, max_chars):
                via = "crossref"
                return _record(abstract, doi, _kind_for(doi, str(work.get("type", ""))), matched_by)
        work = _openalex_work(client, doi)
        if work and titles_match(title, work.get("title") or "", strict=strict):
            abstract = _clean_abstract(_from_inverted_index(work.get("abstract_inverted_index")))
            if _usable(abstract, max_chars):
                via = "openalex"
                return _record(abstract, doi, _kind_for(doi, str(work.get("type", ""))), matched_by)
        return None
    except EvidenceUnavailable as exc:
        if exc.code in {"budget_exhausted", "request_limit"}:
            raise
        return None  # one source failing must not stop the paid fallback
    finally:
        client._event("scholarly_lookup", via=via or "none")
