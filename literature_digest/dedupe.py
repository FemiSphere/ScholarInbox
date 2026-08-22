from __future__ import annotations

import re
import unicodedata
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import DeduplicationResult, PaperEntry


DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
DOI_PAGE_SUFFIX_RE = re.compile(r"/(?:abs|abstract|epdf|full|html|meta|pdf)$", re.IGNORECASE)
DROP_QUERY_PREFIXES = ("utm_",)
DROP_QUERY_KEYS = {"fbclid", "gclid", "cmpid", "cid", "ref", "source"}
GREEK_TITLE_REPLACEMENTS = {
    "α": " alpha ",
    "β": " beta ",
    "γ": " gamma ",
    "δ": " delta ",
    "κ": " kappa ",
    "λ": " lambda ",
    "μ": " mu ",
    "π": " pi ",
    "σ": " sigma ",
    "ω": " omega ",
}
TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "using",
    "via",
    "with",
}
VERSION_MARKERS = {
    "comment",
    "commentary",
    "correction",
    "corrigendum",
    "erratum",
    "part",
    "reply",
    "response",
    "retraction",
}
ROMAN_NUMERALS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}


def normalize_doi(value: str) -> str:
    candidates = extract_dois(value)
    return candidates[0] if candidates else ""


def extract_dois(*values: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for match in DOI_RE.finditer(value or ""):
            doi = match.group(0).rstrip(".,;)").lower()
            doi = DOI_PAGE_SUFFIX_RE.sub("", doi)
            if doi and doi not in seen:
                seen.add(doi)
                result.append(doi)
    return result


def extract_entry_dois(entry: PaperEntry) -> list[str]:
    direct = extract_dois(entry.doi, entry.url)
    if direct:
        return direct
    contextual = extract_dois(entry.abstract, entry.raw_text)
    return contextual if len(contextual) == 1 else []


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    cleaned = url.strip()
    try:
        split = urlsplit(cleaned)
    except ValueError:
        return cleaned.lower().rstrip("/")
    if not split.scheme and not split.netloc:
        return cleaned.lower().rstrip("/")
    query = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in DROP_QUERY_KEYS or lower_key.startswith(DROP_QUERY_PREFIXES):
            continue
        query.append((key, value))
    return urlunsplit(
        (
            split.scheme.lower(),
            split.netloc.lower(),
            split.path.rstrip("/"),
            urlencode(query, doseq=True),
            "",
        )
    )


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", unescape(title or "")).casefold()
    for symbol, replacement in GREEK_TITLE_REPLACEMENTS.items():
        text = text.replace(symbol, replacement)
    text = re.sub(r"^\s*\[(?:html|pdf)\]\s*", "", text)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def title_similarity(left: str, right: str) -> float:
    try:
        from rapidfuzz import fuzz

        return float(fuzz.token_set_ratio(left, right))
    except ImportError:
        from difflib import SequenceMatcher

        left_tokens = set(left.split())
        right_tokens = set(right.split())
        if not left_tokens or not right_tokens:
            return SequenceMatcher(None, left, right).ratio() * 100
        intersection = " ".join(sorted(left_tokens & right_tokens))
        left_combined = " ".join(sorted((left_tokens & right_tokens) | (left_tokens - right_tokens)))
        right_combined = " ".join(sorted((left_tokens & right_tokens) | (right_tokens - left_tokens)))
        return max(
            SequenceMatcher(None, left, right).ratio(),
            SequenceMatcher(None, intersection, left_combined).ratio(),
            SequenceMatcher(None, intersection, right_combined).ratio(),
            SequenceMatcher(None, left_combined, right_combined).ratio(),
        ) * 100


def informative_title_tokens(title: str) -> set[str]:
    normalized = normalize_title(title)
    return {
        _comparison_token(token)
        for token in normalized.split()
        if token not in TITLE_STOPWORDS and (len(token) >= 3 or any(char.isdigit() for char in token))
    }


def fuzzy_title_match_score(left: str, right: str) -> float | None:
    left_normalized = normalize_title(left)
    right_normalized = normalize_title(right)
    if not left_normalized or not right_normalized:
        return None
    length_ratio = min(len(left_normalized), len(right_normalized)) / max(
        len(left_normalized), len(right_normalized)
    )
    if length_ratio < 0.75 or _protected_title_tokens(left_normalized) != _protected_title_tokens(right_normalized):
        return None
    left_tokens = informative_title_tokens(left_normalized)
    right_tokens = informative_title_tokens(right_normalized)
    if len(left_tokens) < 4 or len(right_tokens) < 4:
        return None
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    if jaccard < 0.62:
        return None
    try:
        from rapidfuzz import fuzz

        return float(
            max(
                fuzz.ratio(left_normalized, right_normalized),
                fuzz.token_sort_ratio(left_normalized, right_normalized),
            )
        )
    except ImportError:
        from difflib import SequenceMatcher

        character_score = SequenceMatcher(None, left_normalized, right_normalized).ratio()
        token_score = SequenceMatcher(
            None,
            " ".join(sorted(left_tokens)),
            " ".join(sorted(right_tokens)),
        ).ratio()
        return max(character_score, token_score) * 100


def deduplicate_entries(
    entries: list[PaperEntry],
    fuzzy_title_threshold: int = 92,
    *,
    existing_entries: list[PaperEntry] | None = None,
) -> DeduplicationResult:
    unique: list[PaperEntry] = []
    seen_dois: dict[str, PaperEntry] = {}
    seen_urls: dict[str, PaperEntry] = {}
    seen_titles: dict[str, PaperEntry] = {}
    comparison_entries: list[PaperEntry] = []
    duplicates = 0

    for existing in existing_entries or []:
        dois = extract_entry_dois(existing)
        url = canonicalize_url(existing.url)
        title = normalize_title(existing.title)
        for doi in dois:
            seen_dois.setdefault(doi, existing)
        if url:
            seen_urls.setdefault(url, existing)
        if title:
            seen_titles.setdefault(title, existing)
            comparison_entries.append(existing)

    for entry in entries:
        dois = extract_entry_dois(entry)
        url = canonicalize_url(entry.url)
        title = normalize_title(entry.title)

        matched: PaperEntry | None = None
        for doi in dois:
            if doi in seen_dois:
                matched = seen_dois[doi]
                break
        if matched is None and url and url in seen_urls:
            matched = seen_urls[url]
        if matched is None and title and title in seen_titles:
            matched = seen_titles[title]
        if matched is None and title:
            matched = next(
                (
                    existing
                    for existing in comparison_entries
                    if existing.title
                    and (fuzzy_title_match_score(title, existing.title) or 0.0) >= fuzzy_title_threshold
                ),
                None,
            )

        if matched is not None:
            if any(matched is item for item in unique):
                _merge_entry_metadata(matched, entry)
            for doi in dois:
                seen_dois.setdefault(doi, matched)
            if url:
                seen_urls.setdefault(url, matched)
            if title:
                seen_titles.setdefault(title, matched)
            duplicates += 1
            continue

        if dois:
            entry.doi = dois[0]
            for doi in dois:
                seen_dois.setdefault(doi, entry)
        if url:
            entry.url = url
            seen_urls.setdefault(url, entry)
        if title:
            seen_titles.setdefault(title, entry)
            comparison_entries.append(entry)
        unique.append(entry)

    return DeduplicationResult(unique_entries=unique, duplicates_removed=duplicates)


def _merge_entry_metadata(target: PaperEntry, source: PaperEntry) -> None:
    source_dois = extract_entry_dois(source)
    if not target.doi and source_dois:
        target.doi = source_dois[0]
    if not target.url and source.url:
        target.url = canonicalize_url(source.url)
    if not target.authors and source.authors:
        target.authors = source.authors
    if not target.venue and source.venue:
        target.venue = source.venue
    if len(source.abstract) > len(target.abstract):
        target.abstract = source.abstract
    if len(source.raw_text) > len(target.raw_text):
        target.raw_text = source.raw_text
    existing_images = {str(path) for path in target.image_paths}
    for image in source.image_paths:
        if str(image) not in existing_images:
            target.image_paths.append(image)
            existing_images.add(str(image))


def _protected_title_tokens(normalized_title: str) -> set[str]:
    return {
        token
        for token in normalized_title.split()
        if any(char.isdigit() for char in token) or token in VERSION_MARKERS or token in ROMAN_NUMERALS
    }


def _comparison_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("is", "ss", "us")):
        return token[:-1]
    return token
