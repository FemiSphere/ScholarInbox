from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from threading import Event, Lock
from typing import Any, Iterator
from pathlib import Path
from datetime import datetime, timezone
import json
import sys


_LLM_OPERATION: ContextVar[str] = ContextVar("llm_operation", default="unclassified")
_LLM_ITEM_COUNT: ContextVar[int] = ContextVar("llm_item_count", default=0)
_LLM_JSON_RETRY: ContextVar[bool] = ContextVar("llm_json_retry", default=False)


@dataclass(frozen=True, slots=True)
class LLMRequestMetric:
    operation: str
    item_count: int
    elapsed_seconds: float
    retry: bool
    status: str
    prompt_chars: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cache_hit_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class IORequestMetric:
    operation: str
    item_count: int
    elapsed_seconds: float
    status: str


class RunMetrics:
    """Thread-safe, content-free request metrics for one digest run."""

    def __init__(self) -> None:
        self._llm_requests: list[LLMRequestMetric] = []
        self._io_requests: list[IORequestMetric] = []
        self._lock = Lock()
        self.cancel_event = Event()
        self._journal_path: Path | None = None
        self._journal_failed = False
        self.event_callback = None
        self._validation_failures: list[dict[str, str]] = []

    def configure_journal(self, path: Path) -> None:
        self._journal_path = path
        self.event("run_started")

    def event(self, name: str, **fields: Any) -> None:
        # Callers provide metadata only, never prompts, responses, headers or keys.
        if self.event_callback is not None:
            self.event_callback(name, fields)
        if self._journal_path is None:
            return
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": name, **fields}
        with self._lock:
            try:
                self._journal_path.parent.mkdir(parents=True, exist_ok=True)
                with self._journal_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    handle.flush()
            except OSError:
                if not self._journal_failed:
                    print("Warning: cannot write live request metrics", file=sys.stderr)
                    self._journal_failed = True


    @property
    def llm_requests(self) -> list[LLMRequestMetric]:
        with self._lock:
            return list(self._llm_requests)

    @property
    def io_requests(self) -> list[IORequestMetric]:
        with self._lock:
            return list(self._io_requests)

    def record_llm_validation_failure(self, *, code: str) -> None:
        failure = {"operation": _LLM_OPERATION.get(), "code": code}
        with self._lock:
            self._validation_failures.append(failure)
        self.event("llm_validation_failed", **failure)

    def record_llm_request(
        self,
        *,
        elapsed_seconds: float,
        prompt_chars: int,
        retry: bool = False,
        status: str = "ok",
        usage: dict[str, Any] | None = None,
    ) -> None:
        usage = usage or {}
        details = usage.get("prompt_tokens_details")
        cache_hit_tokens = usage.get("prompt_cache_hit_tokens")
        if cache_hit_tokens is None and isinstance(details, dict):
            cache_hit_tokens = details.get("cached_tokens")
        metric = LLMRequestMetric(
            operation=_LLM_OPERATION.get(),
            item_count=max(0, _LLM_ITEM_COUNT.get()),
            elapsed_seconds=max(0.0, elapsed_seconds),
            retry=retry or _LLM_JSON_RETRY.get(),
            status=status,
            prompt_chars=max(0, prompt_chars),
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            completion_tokens=_as_int(usage.get("completion_tokens")),
            total_tokens=_as_int(usage.get("total_tokens")),
            cache_hit_tokens=_as_int(cache_hit_tokens),
        )
        with self._lock:
            self._llm_requests.append(metric)
        self.event("llm_request_metric", **asdict(metric))

    def record_io_request(
        self,
        *,
        operation: str,
        item_count: int,
        elapsed_seconds: float,
        status: str = "ok",
    ) -> None:
        metric = IORequestMetric(
            operation=operation,
            item_count=max(0, item_count),
            elapsed_seconds=max(0.0, elapsed_seconds),
            status=status,
        )
        with self._lock:
            self._io_requests.append(metric)
        self.event("io_request_finished", **asdict(metric))

    def summary_lines(self, *, include_request_details: bool = True) -> list[str]:
        llm_requests = self.llm_requests
        io_requests = self.io_requests
        with self._lock:
            validation_failures = list(self._validation_failures)
        lines: list[str] = []
        if llm_requests:
            total_tokens = sum(item.total_tokens or 0 for item in llm_requests)
            cache_tokens = sum(item.cache_hit_tokens or 0 for item in llm_requests)
            retries = sum(1 for item in llm_requests if item.retry)
            errors = sum(1 for item in llm_requests if item.status != "ok")
            lines.append(
                "LLM metrics: "
                f"requests={len(llm_requests)}, retries={retries}, errors={errors}, "
                f"validation_failures={len(validation_failures)}, "
                f"request_time_sum={sum(item.elapsed_seconds for item in llm_requests):.2f}s, "
                f"tokens={total_tokens or 'n/a'}, cache_hit_tokens={cache_tokens or 'n/a'}"
            )
            if include_request_details:
                for operation in sorted({item.operation for item in llm_requests}):
                    group = [item for item in llm_requests if item.operation == operation]
                    lines.append(
                        f"  - {operation}: requests={len(group)}, "
                        f"items={sum(item.item_count for item in group)}, "
                        f"request_time_sum={sum(item.elapsed_seconds for item in group):.2f}s"
                    )
                for index, item in enumerate(llm_requests, start=1):
                    lines.append(
                        f"  request#{index}: operation={item.operation}, items={item.item_count}, "
                        f"elapsed={item.elapsed_seconds:.2f}s, retry={str(item.retry).lower()}, "
                        f"status={item.status}, prompt_chars={item.prompt_chars}, "
                        f"prompt_tokens={item.prompt_tokens or 'n/a'}, "
                        f"completion_tokens={item.completion_tokens or 'n/a'}, "
                        f"total_tokens={item.total_tokens or 'n/a'}, "
                        f"cache_hit_tokens={item.cache_hit_tokens or 'n/a'}"
                    )
        if validation_failures:
            lines.append(f"LLM output validation: invalid_attempts={len(validation_failures)} (includes repaired responses)")
            if include_request_details:
                for failure in validation_failures:
                    lines.append(f"  operation={failure['operation']}, code={failure['code']}")
        if io_requests:
            lines.append(
                "Gmail metrics: "
                f"requests={len(io_requests)}, items={sum(item.item_count for item in io_requests)}, "
                f"request_time_sum={sum(item.elapsed_seconds for item in io_requests):.2f}s"
            )
            if include_request_details:
                for index, item in enumerate(io_requests, start=1):
                    lines.append(
                        f"  request#{index}: operation={item.operation}, items={item.item_count}, "
                        f"elapsed={item.elapsed_seconds:.2f}s, status={item.status}"
                    )
        return lines


@contextmanager
def llm_operation(operation: str, item_count: int) -> Iterator[None]:
    operation_token = _LLM_OPERATION.set(operation)
    count_token = _LLM_ITEM_COUNT.set(max(0, item_count))
    try:
        yield
    finally:
        _LLM_ITEM_COUNT.reset(count_token)
        _LLM_OPERATION.reset(operation_token)


@contextmanager
def llm_json_retry() -> Iterator[None]:
    token = _LLM_JSON_RETRY.set(True)
    try:
        yield
    finally:
        _LLM_JSON_RETRY.reset(token)


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def current_llm_operation() -> str:
    return _LLM_OPERATION.get()
