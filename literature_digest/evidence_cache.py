"""A bounded, local cache of abstracts and negative lookup results.

Only the compact evidence record is persisted, never fetched pages or responses.
SQLite's rollback journal is transient and is removed by its normal transaction
handling. Expiry, LRU eviction and compaction bound both rows and disk space.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from time import time
from typing import Any, Callable, Iterator


_APPLICATION_ID = 0x53494543  # ScholarInbox Evidence Cache
_SCHEMA_VERSION = 1
_MAX_RECORD_BYTES = 32 * 1024
_RAW_PAGE_FIELDS = {"html", "raw_html", "raw_response", "page_content", "content", "headers"}


class CacheError(RuntimeError):
    """The cache is unavailable; callers can continue without persistence."""


def _has_raw_page(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in _RAW_PAGE_FIELDS or _has_raw_page(item)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_raw_page(item) for item in value)
    return False


class EvidenceCache:
    def __init__(
        self, path: str | Path, *, max_entries: int = 300,
        max_bytes: int = 8 * 1024 * 1024, ttl_days: float = 30,
        negative_ttl_hours: float = 6, clock: Callable[[], float] = time,
    ) -> None:
        if max_entries < 1 or max_bytes < 16384:
            raise ValueError("Evidence cache requires at least one entry and 16384 bytes")
        if ttl_days < 0 or negative_ttl_hours < 0:
            raise ValueError("Evidence cache TTL must not be negative")
        self.path = Path(path)
        self.max_entries = int(max_entries)
        self.max_bytes = int(max_bytes)
        self.ttl_seconds = float(ttl_days) * 86400
        self.negative_ttl_seconds = float(negative_ttl_hours) * 3600
        self.clock = clock
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._last_access = 0.0
        existed = self.path.exists()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
            self._connection = connection
            if existed:
                # Inspect ownership before any pragma that could modify a user DB.
                if connection.execute("PRAGMA application_id").fetchone()[0] != _APPLICATION_ID:
                    raise CacheError("Unrecognized evidence cache database")
                if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                    raise CacheError("Unsupported evidence cache schema")
                columns = [row[1] for row in connection.execute("PRAGMA table_info(evidence)")]
                if columns != ["key", "payload", "expires", "accessed"]:
                    raise CacheError("Invalid evidence cache schema")
                if connection.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    raise CacheError("Invalid evidence cache database")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA temp_store=MEMORY")
            if not existed:
                connection.execute("CREATE TABLE evidence (key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires REAL NOT NULL, accessed REAL NOT NULL)")
                connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
                connection.commit()
                os.chmod(self.path, 0o600)
            self._last_access = connection.execute("SELECT COALESCE(MAX(accessed),0) FROM evidence").fetchone()[0]
            with self._transaction() as db:
                self._prune(db)
            self._compact_if_needed()
        except BaseException as exc:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            if isinstance(exc, CacheError) or not isinstance(exc, (OSError, sqlite3.Error)):
                raise
            raise CacheError("Cannot open evidence cache") from exc

    def __enter__(self) -> "EvidenceCache":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # Cleanup must not mask an interruption or other caller failure.
        try:
            self.close()
        except CacheError:
            if exc_type is None:
                raise

    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            raise CacheError("Evidence cache is closed")
        return self._connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._db()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise

    def _access_time(self) -> float:
        self._last_access = max(float(self.clock()), self._last_access + 0.000001)
        return self._last_access

    def get(self, key: str) -> dict[str, Any] | None:
        self._validate_key(key)
        with self._lock:
            try:
                with self._transaction() as db:
                    row = db.execute("SELECT payload, expires FROM evidence WHERE key=?", (key,)).fetchone()
                    if row is None:
                        return None
                    if row[1] <= self.clock():
                        db.execute("DELETE FROM evidence WHERE key=?", (key,))
                        return None
                    try:
                        value = json.loads(row[0])
                    except (TypeError, ValueError):
                        db.execute("DELETE FROM evidence WHERE key=?", (key,))
                        return None
                    if not isinstance(value, dict) or _has_raw_page(value):
                        db.execute("DELETE FROM evidence WHERE key=?", (key,))
                        return None
                    db.execute("UPDATE evidence SET accessed=? WHERE key=?", (self._access_time(), key))
                    return value
            except sqlite3.Error as exc:
                raise CacheError("Cannot read evidence cache") from exc

    def put(self, key: str, record: dict[str, Any], *, negative: bool = False) -> bool:
        self._validate_key(key)
        if not isinstance(record, dict):
            raise ValueError("Evidence cache record must be an object")
        if _has_raw_page(record):
            return False
        try:
            payload = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return False
        size = len(payload.encode("utf-8")) + len(key.encode("utf-8")) + 160
        if len(payload.encode("utf-8")) > _MAX_RECORD_BYTES or size > self._logical_budget():
            return False
        ttl = self.negative_ttl_seconds if negative else self.ttl_seconds
        if ttl <= 0:
            return False
        with self._lock:
            try:
                with self._transaction() as db:
                    db.execute("INSERT OR REPLACE INTO evidence (key,payload,expires,accessed) VALUES (?,?,?,?)",
                               (key, payload, self.clock() + ttl, self._access_time()))
                    self._prune(db)
                self._compact_if_needed()
                return self._db().execute("SELECT 1 FROM evidence WHERE key=?", (key,)).fetchone() is not None
            except (OSError, sqlite3.Error) as exc:
                raise CacheError("Cannot write evidence cache") from exc

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not key or len(key.encode("utf-8")) > 1024:
            raise ValueError("Evidence cache key must contain 1 to 1024 bytes")

    def _logical_budget(self) -> int:
        # Leave headroom for the table B-tree, index pages and fragmentation.
        return max(0, int((self.max_bytes - 12288) * 0.65))

    def _prune(self, db: sqlite3.Connection) -> None:
        db.execute("DELETE FROM evidence WHERE expires<=?", (self.clock(),))
        rows = db.execute("SELECT key, length(CAST(payload AS BLOB)) + length(CAST(key AS BLOB)) + 160 FROM evidence ORDER BY accessed ASC,key ASC").fetchall()
        total = sum(row[1] for row in rows)
        count = len(rows)
        for key, size in rows:
            if count <= self.max_entries and total <= self._logical_budget():
                break
            db.execute("DELETE FROM evidence WHERE key=?", (key,))
            total -= size
            count -= 1

    def _compact_if_needed(self) -> None:
        db = self._db()
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        free_bytes = page_size * db.execute("PRAGMA freelist_count").fetchone()[0]
        oversized = self.path.stat().st_size > self.max_bytes
        if oversized or free_bytes >= max(65536, self.max_bytes // 4):
            db.execute("VACUUM")
        # A very small configured budget may need more headroom than estimated.
        while self.path.stat().st_size > self.max_bytes:
            row = db.execute("SELECT key FROM evidence ORDER BY accessed ASC,key ASC LIMIT 1").fetchone()
            if row is None:
                raise CacheError("Evidence cache size limit is below SQLite storage overhead")
            with self._transaction() as transaction:
                transaction.execute("DELETE FROM evidence WHERE key=?", (row[0],))
            db.execute("VACUUM")

    def close(self) -> None:
        with self._lock:
            if self._connection is None:
                return
            try:
                with self._transaction() as db:
                    self._prune(db)
                self._compact_if_needed()
            except (OSError, sqlite3.Error) as exc:
                raise CacheError("Cannot clean evidence cache") from exc
            finally:
                self._connection.close()
                self._connection = None
