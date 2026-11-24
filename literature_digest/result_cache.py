"""Short-lived cache of per-paper ranking and translation results.

Purpose: when a run ends with a fallback (emails stay unread) the next run re-reads the
same papers; successful analyses and translations from the earlier attempt are reused so
only the failed part is paid for again. Dry runs also warm it for the real run.

Bounds: entries expire after ``ttl_days`` and the table is capped at ``max_entries``
(least recently used rows are evicted). After a fully successful real run the whole
cache is cleared, because the registry then guarantees those papers will not return.
Only compact result fields are stored, never prompts, responses or email bodies.
An unrecognised database file is never modified or deleted.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from time import time
from typing import Any, Callable

from .models import EvidenceRecord, PaperEntry, RankedPaper

_APPLICATION_ID = 0x53495243  # ScholarInbox Result Cache
_SCHEMA_VERSION = 1
_ANALYSIS_FIELDS = ("relevance", "score", "reason_zh", "matched_topics")
_TRANSLATION_FIELDS = ("title_zh", "summary_zh")


class ResultCacheError(RuntimeError):
    """The cache is unavailable; callers continue without it."""


def _digest(*parts: Any) -> str:
    material = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def analysis_key(entry: PaperEntry, profile_fingerprint: str, model_fingerprint: str) -> str:
    return "a:" + _digest(entry.title, entry.abstract, entry.venue, entry.doi, entry.url,
                          profile_fingerprint, model_fingerprint)


def translation_key(paper: RankedPaper, model_fingerprint: str) -> str:
    evidence: EvidenceRecord | None = paper.evidence
    entry = paper.entry
    return "t:" + _digest(entry.title, entry.abstract, entry.venue, paper.relevance,
                          evidence.abstract if evidence else "", model_fingerprint)


class ResultCache:
    def __init__(self, path: str | Path, *, ttl_days: float = 7, max_entries: int = 5000,
                 clock: Callable[[], float] = time) -> None:
        if max_entries < 1 or ttl_days <= 0:
            raise ValueError("Result cache needs a positive TTL and capacity")
        self.path = Path(path)
        self.ttl_seconds = float(ttl_days) * 86400
        self.max_entries = int(max_entries)
        self.clock = clock
        self._lock = RLock()
        existed = self.path.exists()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
            if existed:
                if self._connection.execute("PRAGMA application_id").fetchone()[0] != _APPLICATION_ID:
                    raise ResultCacheError("Unrecognized result cache database")
                if self._connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                    raise ResultCacheError("Unsupported result cache schema")
            else:
                self._connection.execute(
                    "CREATE TABLE results (key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires REAL NOT NULL, accessed REAL NOT NULL)")
                self._connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                self._connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._connection.execute("DELETE FROM results WHERE expires <= ?", (self.clock(),))
            self._connection.commit()
        except (sqlite3.Error, OSError) as exc:
            self.close()
            raise ResultCacheError(f"Result cache unavailable: {type(exc).__name__}") from exc
        except ResultCacheError:
            self.close()
            raise

    # -- generic -----------------------------------------------------------------
    def _get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                row = self._connection.execute(
                    "SELECT payload FROM results WHERE key = ? AND expires > ?", (key, self.clock())).fetchone()
                if row is None:
                    return None
                self._connection.execute("UPDATE results SET accessed = ? WHERE key = ?", (self.clock(), key))
                self._connection.commit()
                payload = json.loads(row[0])
            except (sqlite3.Error, ValueError, AttributeError):
                return None
            return payload if isinstance(payload, dict) else None

    def _put_many(self, rows: list[tuple[str, dict[str, Any]]]) -> None:
        if not rows:
            return
        now = self.clock()
        with self._lock:
            try:
                self._connection.executemany(
                    "INSERT OR REPLACE INTO results (key, payload, expires, accessed) VALUES (?, ?, ?, ?)",
                    [(key, json.dumps(payload, ensure_ascii=False), now + self.ttl_seconds, now) for key, payload in rows])
                count = self._connection.execute("SELECT COUNT(*) FROM results").fetchone()[0]
                if count > self.max_entries:
                    self._connection.execute(
                        "DELETE FROM results WHERE key IN (SELECT key FROM results ORDER BY accessed ASC LIMIT ?)",
                        (count - self.max_entries,))
                self._connection.commit()
            except (sqlite3.Error, AttributeError):
                return

    def clear(self) -> None:
        with self._lock:
            try:
                self._connection.execute("DELETE FROM results")
                self._connection.commit()
                self._connection.execute("VACUUM")
            except (sqlite3.Error, AttributeError):
                return

    def close(self) -> None:
        connection = getattr(self, "_connection", None)
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass
            self._connection = None

    # -- typed helpers -----------------------------------------------------------
    def get_analysis(self, key: str) -> dict[str, Any] | None:
        payload = self._get(key)
        if payload is None or any(field not in payload for field in _ANALYSIS_FIELDS):
            return None
        return payload

    def put_analyses(self, items: list[tuple[str, RankedPaper]]) -> None:
        self._put_many([(key, {field: getattr(paper, field) for field in _ANALYSIS_FIELDS})
                        for key, paper in items if not paper.fallback])

    def get_translation(self, key: str) -> dict[str, str] | None:
        payload = self._get(key)
        if payload is None or not all(isinstance(payload.get(field), str) and payload[field] for field in _TRANSLATION_FIELDS):
            return None
        return payload

    def put_translations(self, items: list[tuple[str, RankedPaper]]) -> None:
        self._put_many([(key, {field: getattr(paper, field) for field in _TRANSLATION_FIELDS})
                        for key, paper in items if paper.translated])
