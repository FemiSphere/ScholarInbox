from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Any, Iterator, Protocol


_LLM_DEADLINE: ContextVar[float | None] = ContextVar("llm_deadline", default=None)


def current_llm_deadline() -> float | None:
    return _LLM_DEADLINE.get()


@contextmanager
def llm_time_budget(seconds: float) -> Iterator[None]:
    """Share one wall-clock budget across nested LLM requests and retries."""
    deadline = perf_counter() + max(0.0, float(seconds))
    parent = current_llm_deadline()
    if parent is not None:
        deadline = min(deadline, parent)
    token = _LLM_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _LLM_DEADLINE.reset(token)


class LLMError(RuntimeError):
    """An LLM failure with a stable, content-free classification."""

    def __init__(self, message: str = "", *, code: str = "llm_error") -> None:
        super().__init__(message)
        self.code = code


class LLMOutputTruncatedError(LLMError):
    """The provider reached its output limit; never trust the partial result."""

    def __init__(self, message: str = "LLM output reached its length limit.", *, code: str = "output_length") -> None:
        super().__init__(message, code=code)


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...

    def complete_json(self, prompt: str) -> dict[str, Any]:
        ...


def redact_secrets(text: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***REDACTED***", text)
    redacted = re.sub(
        r"(?i)(api[_-]?key[\"'\s:=]+)[A-Za-z0-9_\-\.]{12,}",
        r"\1***REDACTED***",
        redacted,
    )
    return redacted


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM response contained malformed fenced JSON: {exc}", code="invalid_json") from exc
        if isinstance(parsed, dict):
            return parsed
        raise LLMError("LLM response fenced JSON was not an object.", code="invalid_json")

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM response contained malformed JSON object: {exc}", code="invalid_json") from exc
        if isinstance(parsed, dict):
            return parsed
        raise LLMError("LLM response JSON was not an object.", code="invalid_json")
    raise LLMError("LLM response did not contain a JSON object.", code="invalid_json")
