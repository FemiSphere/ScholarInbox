from __future__ import annotations

import base64
import json
import hashlib
import os
import tempfile
import time
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event, Lock
from collections.abc import Callable
import re
from html import unescape, escape
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import parse_qs, urlsplit

from .concurrency import cooperative_map
from .email_chunks import EmailChunk, build_email_chunks, split_email_chunk
from .dedupe import DOI_RE, normalize_doi
from .llm import LLMClient, LLMError
from .llm.base import LLMOutputTruncatedError
from .models import EmailMessage, PaperEntry
from .telemetry import llm_operation


URL_RE = re.compile(r"https?://[^\s<>)\"']+", re.IGNORECASE)
BAD_LINK_TEXT = {
    "pdf",
    "html",
    "view article",
    "read more",
    "full text",
    "unsubscribe",
    "manage alerts",
    "settings",
    "click here",
    "view online",
    "read article",
    "send feedback",
    "customize your preferences",
    "stop all emails from acs publications",
    "switch off recommended reading email alerts",
    "visit our email preference center",
}
BOILERPLATE_TEXT = (
    "unsubscribe",
    "manage alerts",
    "manage preferences",
    "email preference",
    "privacy policy",
    "view this email in your browser",
    "view online",
    "follow us on",
    "copyright ©",
    "all rights reserved",
    "stop all emails",
    "switch off recommended reading",
)


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.images: list[str] = []
        self._href_stack: list[str] = []
        self._text_stack: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if tag.lower() == "a":
            self._href_stack.append(attrs_dict.get("href", ""))
            self._text_stack.append([])
        elif tag.lower() == "img":
            src = attrs_dict.get("src", "")
            if src:
                self.images.append(src)

    def handle_data(self, data: str) -> None:
        if self._text_stack:
            self._text_stack[-1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href_stack:
            return
        href = self._href_stack.pop()
        pieces = self._text_stack.pop()
        text = normalize_space(" ".join(pieces))
        if href and text:
            self.links.append((href, text))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"style", "script", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"style", "script", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data.strip())


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html or "")
    return normalize_space("\n".join(parser.parts))


def parse_emails(
    emails: Iterable[EmailMessage],
    *,
    llm: LLMClient | None = None,
    llm_structure_non_scholar: bool = False,
    max_workers: int = 1,
    llm_text_max_chars: int = 6000,
    llm_max_links: int = 50,
    llm_max_images: int = 20,
    llm_max_chunk_items: int = 8,
    llm_max_split_depth: int = 4,
    llm_max_requests_per_email: int = 32,
    llm_email_budget_seconds: float = 240,
    progress: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str], None] | None = None,
    cache_dir: Path | None = None,
    cache_namespace: str = "",
    cancel_event: Event | None = None,
    used_cache_paths: list[Path] | None = None,
) -> list[PaperEntry]:
    """``used_cache_paths`` (optional) collects the cache file of every parsed email so the
    caller can delete them once those emails are marked as read."""
    email_list = list(emails)
    callback_lock = Lock()

    def emit(message: str) -> None:
        if event_callback:
            with callback_lock:
                event_callback(message)

    def parse_one(item: tuple[int, EmailMessage]) -> list[PaperEntry]:
        index, email = item
        started = time.monotonic()
        cache_path = None
        if cache_dir is not None:
            signature = {
                "version": 3, "email": asdict(email),
                "llm_enabled": llm_structure_non_scholar and llm is not None,
                "namespace": cache_namespace, "text_max_chars": llm_text_max_chars,
                "max_links": llm_max_links, "max_images": llm_max_images,
                "max_chunk_items": llm_max_chunk_items, "max_split_depth": llm_max_split_depth,
                "max_requests_per_email": llm_max_requests_per_email,
                "email_budget_seconds": llm_email_budget_seconds,
            }
            key = hashlib.sha256(json.dumps(signature, sort_keys=True, default=str).encode()).hexdigest()
            cache_path = Path(cache_dir) / f"{key}.json"
            if used_cache_paths is not None:
                with callback_lock:
                    used_cache_paths.append(cache_path)
            cached = _read_parse_cache(cache_path)
            if cached is not None:
                emit(f"邮件解析 {index}/{len(email_list)}：缓存命中，条目 {len(cached)}")
                return cached
        emit(f"邮件解析 {index}/{len(email_list)}：开始")
        failed = False

        def on_error(error: LLMError) -> None:
            nonlocal failed
            failed = True
            emit(f"邮件解析 {index}/{len(email_list)}：LLM 失败（{type(error).__name__}，code={_safe_error_code(error)}），回退本地规则")

        entries = []
        if llm_structure_non_scholar and llm is not None and not _is_google_scholar_email(email):
            entries = _parse_non_scholar_email_with_llm(
                email, llm, text_max_chars=llm_text_max_chars,
                max_links=llm_max_links, max_images=llm_max_images, on_error=on_error,
                max_chunk_items=llm_max_chunk_items, max_split_depth=llm_max_split_depth,
                max_requests_per_email=llm_max_requests_per_email,
                email_budget_seconds=llm_email_budget_seconds, cancel_event=cancel_event,
                event_callback=lambda message: emit(f"邮件解析 {index}/{len(email_list)}：{message}"),
            )
        else:
            entries = parse_email(email)
        if cache_path is not None and not failed:
            try:
                _write_parse_cache(cache_path, entries)
            except OSError:
                emit(f"邮件解析 {index}/{len(email_list)}：缓存写入失败（OSError）")
        emit(f"邮件解析 {index}/{len(email_list)}：完成，条目 {len(entries)}，耗时 {time.monotonic() - started:.1f}s")
        return entries

    worker_count = min(max(1, max_workers), len(email_list) or 1)
    parsed = cooperative_map(
        parse_one, enumerate(email_list, start=1), max_workers=worker_count,
        thread_name_prefix="email-parser", cancel_event=cancel_event, progress=progress,
    )
    return [entry for email_entries in parsed for entry in email_entries]


def _read_parse_cache(path: Path) -> list[PaperEntry] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("entries"), list):
            return None
        entries = []
        for item in payload["entries"]:
            if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                return None
            if not isinstance(item.get("image_paths", []), list):
                return None
            entries.append(PaperEntry(**item))
        return entries
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _write_parse_cache(path: Path, entries: list[PaperEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            json.dump({"version": 1, "entries": [asdict(entry) for entry in entries]}, stream, ensure_ascii=False, default=str)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def parse_email(email: EmailMessage) -> list[PaperEntry]:
    if email.html:
        entries = _parse_html_email(email)
    else:
        entries = []
    if email.text and not entries:
        entries.extend(_parse_text_email(email))
    elif not email.html and email.snippet:
        entries.extend(_parse_text_email(email))
    return _dedupe_within_email(entries)


def _parse_html_email(email: EmailMessage) -> list[PaperEntry]:
    extractor = _AnchorExtractor()
    extractor.feed(email.html)
    text = html_to_text(email.html)
    entries: list[PaperEntry] = []
    google_scholar = _is_google_scholar_email(email)
    image_refs = [] if google_scholar else _select_entry_images(
        list(email.image_paths) + list(extractor.images)
    )
    image_refs_by_doi = _images_by_doi(image_refs)

    for href, link_text in extractor.links:
        title = normalize_space(link_text)
        if not _is_likely_title(title, href):
            continue
        raw = _snippet_around(text, title)
        cleaned_url = _clean_url(href)
        doi = _extract_doi(cleaned_url + " " + raw)
        entries.append(
            PaperEntry(
                title=title,
                url=cleaned_url,
                abstract=raw,
                doi=doi,
                venue=_extract_venue(raw, title),
                source_email_id=email.id,
                source_subject=email.subject,
                source_sender=email.sender,
                image_paths=image_refs_by_doi.get(doi, image_refs[:1]),
                raw_text=raw,
            )
        )
    return entries


def _safe_error_code(error: LLMError) -> str:
    code = getattr(error, "code", "llm_error")
    allowed = {"llm_error", "output_length", "output_truncated", "invalid_schema", "invalid_json",
               "malformed_json", "json_parse_error", "budget_exhausted", "timeout", "network",
               "network_error", "invalid_response", "request_limit", "cancelled", "content_filter",
               "insufficient_system_resource", "aborted", "invalid_finish_reason",
               "http_400", "http_401", "http_402", "http_403", "http_404", "http_408",
               "http_429", "http_500", "http_502", "http_503", "http_504"}
    return code if code in allowed else "llm_error"


def _parse_non_scholar_email_with_llm(
    email: EmailMessage, llm: LLMClient, *, text_max_chars: int, max_links: int,
    max_images: int, on_error: Callable[[LLMError], None] | None = None,
    max_chunk_items: int = 8, max_split_depth: int = 4,
    max_requests_per_email: int = 32, email_budget_seconds: float = 240,
    cancel_event: Event | None = None, event_callback: Callable[[str], None] | None = None,
) -> list[PaperEntry]:
    from .llm.base import llm_time_budget

    chunks = build_email_chunks(
        html=email.html, text=email.text or email.snippet,
        image_paths=[str(path) for path in email.image_paths],
        is_article=lambda title, href: _is_likely_title(title, href),
        accept_link=lambda href, title: not _is_obvious_non_paper_link(title, href),
        accept_image=_is_useful_image_src, text_max_chars=text_max_chars,
        max_links=max_links, max_images=max_images, max_items=max_chunk_items,
    )
    deadline = time.monotonic() + max(0, email_budget_seconds)
    request_count = 0

    def emit(message: str) -> None:
        if event_callback:
            event_callback(message)

    def fallback(chunk: EmailChunk, error: LLMError) -> list[PaperEntry]:
        if on_error:
            on_error(error)
        # Only the failed region is passed to deterministic extraction.
        html = "".join(f'<a href="{escape(url, quote=True)}">{escape(title)}</a>' for url, title in chunk.links)
        html += "".join(f'<img src="{escape(image, quote=True)}">' for image in chunk.images)
        html += f"<p>{escape(chunk.text)}</p>"
        local = replace(email, html=html if email.html else "",
                        text="" if email.html else chunk.text, snippet="", image_paths=[])
        return parse_email(local)

    def extract(chunk: EmailChunk, depth: int) -> list[PaperEntry]:
        nonlocal request_count
        if cancel_event is not None and cancel_event.is_set():
            raise KeyboardInterrupt
        if request_count >= max_requests_per_email:
            return fallback(chunk, LLMError("Email extraction request limit reached", code="request_limit"))
        if time.monotonic() >= deadline:
            return fallback(chunk, LLMError("Email extraction budget exhausted", code="budget_exhausted"))
        request_count += 1
        emit(f"分块请求 {request_count}，深度 {depth}，正文 {len(chunk.text)} 字符，链接 {len(chunk.links)}，图片 {len(chunk.images)}")
        try:
            with llm_operation("email_extraction", 1):
                payload = llm.complete_json(_email_chunk_prompt(email, chunk))
            if not isinstance(payload, dict) or not isinstance(payload.get("papers"), list):
                raise LLMError("Invalid extraction envelope", code="invalid_schema")
            if any(not isinstance(item, dict) or not isinstance(item.get("title"), str)
                   or not item["title"].strip()
                   or any(item.get(field) is not None and not isinstance(item[field], str)
                          for field in ("url", "doi", "venue", "authors", "snippet"))
                   for item in payload["papers"]):
                raise LLMError("Invalid extraction paper", code="invalid_schema")
            images = [{"index": index, "url": src} for index, src in enumerate(chunk.images)]
            return _paper_entries_from_llm_payload(payload, email, images)
        except LLMError as error:
            code = _safe_error_code(error)
            recoverable = isinstance(error, LLMOutputTruncatedError) or code in {"output_length", "output_truncated", "invalid_schema", "invalid_json", "malformed_json", "json_parse_error"}
            # Legacy clients do not expose typed JSON errors yet.
            recoverable = recoverable or (code == "llm_error" and "JSON" in str(error))
            children = split_email_chunk(chunk) if recoverable and depth < max_split_depth else []
            if children:
                emit(f"分块拆分（{code}），深度 {depth + 1}，子块 {len(children)}")
                return [entry for child in children for entry in extract(child, depth + 1)]
            return fallback(chunk, error)

    results = []
    with llm_time_budget(max(0, email_budget_seconds)):
        for chunk in chunks:
            results.extend(extract(chunk, 0))
    # Overlap can return the same paper twice. Keep its richest source excerpt.
    by_identity: dict[tuple[str, str], PaperEntry] = {}
    for entry in results:
        key = (entry.title.casefold(), entry.url.casefold())
        previous = by_identity.get(key)
        if previous is None:
            by_identity[key] = entry
        else:
            previous.image_paths = list(dict.fromkeys(previous.image_paths + entry.image_paths))
            if len(entry.abstract) > len(previous.abstract):
                previous.abstract = entry.abstract
                previous.raw_text = entry.raw_text
    return list(by_identity.values())


def _email_chunk_prompt(email: EmailMessage, chunk: EmailChunk) -> str:
    text = chunk.text
    links = _candidate_links_for_llm(chunk.links)
    images = [{"index": index, "url": src} for index, src in enumerate(chunk.images)]
    return f"""
EMAIL_PAPER_EXTRACTION_JSON

Extract academic paper entries from a publisher, journal, newsletter, or RSS-style academic email.
Return one valid JSON object only. Do not include Markdown or explanations.

Keep only real paper/article entries. Exclude navigation links, preference-center links, unsubscribe links, feedback links, social links, logos, ads, and generic buttons.

Schema:
{{
  "papers": [
    {{
      "title": "English paper title",
      "url": "https://paper-url",
      "doi": "10.xxxx/xxxxx",
      "venue": "Journal name",
      "authors": "Author list if available",
      "snippet": "Verbatim available article abstract or source excerpt, up to 2000 characters; empty if unavailable",
      "image_index": 0
    }}
  ]
}}

Rules:
- `title` must be a specific academic paper/article title.
- Preserve the available article abstract/excerpt faithfully in `snippet` (up to 2000 characters).
- Do not shorten a supplied abstract into a generic description. Preserve material, methods, results and limitations actually present.
- Never combine text from adjacent articles or invent a full abstract when only a title is visible.
- `url` should point to the paper landing page or DOI page when available.
- `doi` should be empty if not present.
- `venue` should be journal/source name if visible.
- `image_index` should be the matching image index from CANDIDATE_IMAGES, or null if no useful article image exists.
- Do not include email management links or feedback/preference/unsubscribe entries.

EMAIL_SUBJECT:
{email.subject}

EMAIL_SENDER:
{email.sender}

CANDIDATE_LINKS_JSON:
{json.dumps(links, ensure_ascii=False)}

CANDIDATE_IMAGES_JSON:
{json.dumps(images, ensure_ascii=False)}

EMAIL_TEXT:
{text}
""".strip()


def _parse_text_email(email: EmailMessage) -> list[PaperEntry]:
    text = email.text or email.snippet
    if not text:
        return []
    urls = URL_RE.findall(text)
    dois = DOI_RE.findall(text)
    candidates = _title_candidates_from_text(text)
    entries: list[PaperEntry] = []

    for idx, title in enumerate(candidates[:12]):
        url = urls[idx] if idx < len(urls) else (urls[0] if len(candidates) == 1 and urls else "")
        doi = dois[idx] if idx < len(dois) else (dois[0] if len(candidates) == 1 and dois else "")
        entries.append(
            PaperEntry(
                title=title,
                url=_clean_url(url),
                abstract=_snippet_around(text, title),
                doi=_extract_doi(doi),
                venue=_extract_venue(text, title),
                source_email_id=email.id,
                source_subject=email.subject,
                source_sender=email.sender,
                image_paths=list(email.image_paths),
                raw_text=text[:2000],
            )
        )
    return entries


def _candidate_links_for_llm(links: list[tuple[str, str]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for href, link_text in links:
        title = normalize_space(link_text)
        cleaned_url = _clean_url(href)
        if not title or not cleaned_url:
            continue
        if _is_obvious_non_paper_link(title, cleaned_url):
            continue
        key = (title.casefold(), cleaned_url)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"text": title, "url": cleaned_url})
    return candidates


def _compact_email_text(email: EmailMessage, *, max_chars: int) -> str:
    if email.html:
        extractor = _TextExtractor()
        extractor.feed(email.html)
        raw_parts = extractor.parts
    else:
        raw_parts = (email.text or email.snippet).splitlines()

    parts: list[str] = []
    seen: set[str] = set()
    for raw_part in raw_parts:
        part = normalize_space(raw_part)
        if not part:
            continue
        lower = part.casefold()
        if len(part) <= 320 and any(marker in lower for marker in BOILERPLATE_TEXT):
            continue
        key = lower[:500]
        if key in seen:
            continue
        seen.add(key)
        parts.append(part)

    result: list[str] = []
    used = 0
    for part in parts:
        remaining = max_chars - used
        if remaining <= 0:
            break
        selected = part[:remaining]
        result.append(selected)
        used += len(selected) + 1
    return "\n".join(result)


def _candidate_images_for_llm(images: list[object]) -> list[dict[str, str | int]]:
    candidates: list[dict[str, str | int]] = []
    for image in images:
        src = str(image)
        if not _is_useful_image_src(src):
            continue
        candidates.append({"index": len(candidates), "url": src})
    return candidates


def _images_by_doi(images: list[object]) -> dict[str, list[object]]:
    result: dict[str, list[object]] = {}
    for image in images:
        doi = _extract_doi(str(image))
        if doi:
            result.setdefault(doi, []).append(image)
    return result


def _paper_entries_from_llm_payload(
    payload: dict[str, Any],
    email: EmailMessage,
    images: list[dict[str, str | int]],
) -> list[PaperEntry]:
    entries: list[PaperEntry] = []
    image_by_index = {int(item["index"]): str(item["url"]) for item in images if "index" in item and "url" in item}
    for item in payload.get("papers", []):
        if not isinstance(item, dict):
            continue
        title = normalize_space(str(item.get("title", "")))
        url = _clean_url(str(item.get("url", "")))
        if not _is_likely_title(title, url):
            continue
        if _is_obvious_non_paper_link(title, url):
            continue
        image_paths: list[str] = []
        image_index = item.get("image_index")
        try:
            if image_index is not None and int(image_index) in image_by_index:
                image_paths.append(image_by_index[int(image_index)])
        except (TypeError, ValueError):
            pass
        snippet = normalize_space(str(item.get("snippet", "")))
        doi = _extract_doi(str(item.get("doi", "")) or url or snippet)
        entries.append(
            PaperEntry(
                title=title,
                url=url,
                authors=normalize_space(str(item.get("authors", ""))),
                venue=normalize_space(str(item.get("venue", ""))),
                abstract=snippet,
                doi=doi,
                source_email_id=email.id,
                source_subject=email.subject,
                source_sender=email.sender,
                image_paths=image_paths,
                raw_text=snippet,
            )
        )
    return entries


def _title_candidates_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        if not _is_likely_title(line, ""):
            continue
        candidates.append(line)
    if candidates:
        return candidates

    sentences = re.split(r"(?<=[.!?])\s+", normalize_space(text))
    return [sentence for sentence in sentences if _is_likely_title(sentence, "")][:8]


def _is_likely_title(text: str, href: str) -> bool:
    normalized = normalize_space(text)
    lower = normalized.lower()
    if len(normalized) < 16 or len(normalized) > 260:
        return False
    if lower in BAD_LINK_TEXT:
        return False
    if _is_obvious_non_paper_link(normalized, href):
        return False
    href_lower = href.lower()
    if any(token in href_lower for token in ("scholar_alerts", "citations?", "view_op=cancel_alert")):
        return False
    if "scholar.google." in href_lower and "scholar_url" not in href_lower:
        return False
    if lower.startswith("[") and lower.endswith("]") and "scholar.google." in href_lower:
        return False
    if lower.startswith(("http://", "https://", "doi:")):
        return False
    if href_lower.startswith(("mailto:", "#")):
        return False
    word_count = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", normalized))
    return word_count >= 3


def _snippet_around(text: str, title: str, radius: int = 500) -> str:
    collapsed = normalize_space(text)
    idx = collapsed.lower().find(title.lower())
    if idx == -1:
        return collapsed[:radius]
    start = max(0, idx - radius // 3)
    end = min(len(collapsed), idx + len(title) + radius)
    return collapsed[start:end]


def _clean_url(url: str) -> str:
    cleaned = unescape(url or "").rstrip(".,;)\"'")
    split = urlsplit(cleaned)
    if split.netloc.endswith("scholar.google.com") and split.path.endswith("/scholar_url"):
        target = parse_qs(split.query).get("url", [""])[0]
        if target:
            return target
    query = parse_qs(split.query)
    target = query.get("elqTarget", [""])[0]
    decoded = _decode_tracking_target(target)
    if decoded:
        return decoded
    return cleaned


def _decode_tracking_target(value: str) -> str:
    if not value:
        return ""
    for trim in range(0, min(4, len(value))):
        candidate = value[: len(value) - trim] if trim else value
        padded = candidate + "=" * (-len(candidate) % 4)
        for decoder in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                decoded = decoder(padded.encode("ascii")).decode("utf-8", errors="replace")
            except Exception:
                continue
            if decoded.startswith(("http://", "https://")):
                return decoded
    return ""


def _extract_doi(value: str) -> str:
    split = urlsplit(value or "")
    path = split.path
    for marker in ("/doi/", "/cms/"):
        if marker not in path:
            continue
        tail = path.split(marker, 1)[1].strip("/")
        pieces = tail.split("/")
        if len(pieces) >= 2 and pieces[0].startswith("10."):
            return f"{pieces[0]}/{pieces[1]}".lower().rstrip(".,;)")
    doi = normalize_doi(value)
    for marker in ("/asset", "/images", "/medium", "/full"):
        if marker in doi:
            doi = doi.split(marker, 1)[0]
    return doi


def _extract_venue(text: str, title: str) -> str:
    compact = normalize_space(text)
    title_index = compact.lower().find(title.lower())
    if title_index != -1:
        compact = compact[title_index + len(title) :]
    window = compact[:500]
    patterns = [
        r"\s-\s(?P<venue>[^,。…]+(?:,\s*\d{4})?)",
        r"\.\s*(?P<venue>[A-Z][A-Za-z&:\- ]+(?:,\s*\d{4}))",
    ]
    for pattern in patterns:
        match = re.search(pattern, window)
        if not match:
            continue
        venue = normalize_space(match.group("venue"))
        venue = venue.strip(" .;:-")
        if _is_valid_venue(venue):
            return venue
    return ""


def _is_valid_venue(value: str) -> bool:
    lower = value.lower()
    if not value or len(value) > 120:
        return False
    if any(token in lower for token in ("google scholar", "this message", "cancel alert", "unsubscribe")):
        return False
    if not re.search(r"[A-Za-z]", value):
        return False
    return True


def _is_useful_image_src(src: str) -> bool:
    lower = str(src).lower().strip()
    if not lower:
        return False
    blocked_tokens = (
        "spacer",
        "tracking",
        "pixel",
        "logo",
        "icon",
        "save-",
        "tw-",
        "twitter",
        "facebook",
        "linkedin",
        "/intl/",
        "/scholar/images/",
        "share",
        "social",
        "avatar",
        "profile",
        "open_in_new",
        "footerimage",
        "footerimages",
        "/footerimages/",
        "/e/footerimages/",
        "click.notification.",
        "/ci0/",
        "eloquaimages",
        "arrow",
    )
    if any(token in lower for token in blocked_tokens):
        return False
    return lower.startswith(("http://", "https://", "data/", "data:image", "./", "../")) or "." in lower


def _is_obvious_non_paper_link(text: str, href: str) -> bool:
    lower = normalize_space(text).lower()
    href_lower = (href or "").lower()
    blocked_text_tokens = (
        "unsubscribe",
        "privacy policy",
        "manage alert",
        "view online",
        "send feedback",
        "preference center",
        "preferences",
        "customize your preferences",
        "switch off",
        "stop all emails",
        "follow us",
        "read article",
    )
    blocked_href_tokens = (
        "unsubscribe",
        "preferences.",
        "preference",
        "privacy",
        "email_marketing_footer",
        "footer_unfollow",
        "viewonline",
    )
    return any(token in lower for token in blocked_text_tokens) or any(
        token in href_lower for token in blocked_href_tokens
    )


def _select_entry_images(images: list[object]) -> list[object]:
    useful = [image for image in images if _is_useful_image_src(str(image))]
    return useful[:20]


def _is_google_scholar_email(email: EmailMessage) -> bool:
    searchable = " ".join([email.sender, email.subject, email.html[:2000], email.text[:1000]]).lower()
    return (
        "scholaralerts-noreply@google.com" in searchable
        or "google scholar" in searchable
        or "google 学术" in searchable
        or "google 學術" in searchable
        or "scholar.google." in searchable
    )


def _dedupe_within_email(entries: list[PaperEntry]) -> list[PaperEntry]:
    seen: set[tuple[str, str]] = set()
    result: list[PaperEntry] = []
    for entry in entries:
        key = (entry.title.lower(), entry.url.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result
