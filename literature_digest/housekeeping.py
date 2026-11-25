"""Bounded retention for files the program itself writes (run logs, request metrics)."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

# Only names this program creates are eligible; anything else in the folders is left alone.
_LOG_PATTERNS = (
    re.compile(r"digest-(\d{8})-\d{6}(?:-\d+)?\.log"),
    re.compile(r"(?:requests|metrics)-(\d{8})-\d{6}(?:-\d+)?\.(?:jsonl|log)"),
)


def prune_old_logs(directories: list[Path], *, today: date, retention_days: int) -> tuple[int, list[str]]:
    """Delete program logs whose filename date is older than ``retention_days``.

    Returns (removed_count, names_that_failed). A non-positive retention disables cleanup.
    """
    if retention_days <= 0:
        return 0, []
    cutoff = today - timedelta(days=retention_days)
    removed, failed = 0, []
    seen: set[Path] = set()
    for directory in directories:
        try:
            candidates = list(directory.iterdir())
        except OSError:
            continue
        for path in candidates:
            if path in seen or path.is_symlink() or not path.is_file():
                continue
            seen.add(path)
            stamp = _filename_date(path.name)
            if stamp is None or stamp >= cutoff:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                failed.append(path.name)
            else:
                removed += 1
    return removed, failed


def _filename_date(name: str) -> date | None:
    for pattern in _LOG_PATTERNS:
        match = pattern.fullmatch(name)
        if match:
            raw = match[1]
            try:
                return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
            except ValueError:
                return None
    return None


def prune_stale_files(directory: Path, *, max_age_days: float, suffixes: tuple[str, ...] = (),
                      now: float | None = None) -> tuple[int, list[str]]:
    """Delete regular files in ``directory`` (not recursive) not modified for ``max_age_days``.

    Used for program-owned folders only (parse cache, TOC images). ``suffixes`` limits which
    files are eligible; an empty tuple means any regular file. Missing folders are fine.
    """
    import time

    if max_age_days <= 0:
        return 0, []
    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    removed, failed = 0, []
    try:
        candidates = list(Path(directory).iterdir())
    except OSError:
        return 0, []
    for path in candidates:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if suffixes and not path.name.endswith(suffixes):
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            failed.append(path.name)
        else:
            removed += 1
    return removed, failed


def remove_files(paths: list[Path]) -> int:
    """Remove the given files if they still exist; returns how many were deleted."""
    removed = 0
    for path in paths:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue
        removed += 1
    return removed
