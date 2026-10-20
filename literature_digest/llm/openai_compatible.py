from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from contextvars import ContextVar
from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import BoundedSemaphore, Thread
import errno
import socket
import ssl
from time import perf_counter, sleep
from typing import Any

from .base import LLMError, LLMOutputTruncatedError, current_llm_deadline, extract_json_object, redact_secrets
from ..telemetry import RunMetrics, llm_json_retry, current_llm_operation


_REQUEST_DEADLINE: ContextVar[float | None] = ContextVar("api_request_deadline", default=None)


@dataclass(slots=True)
class OpenAICompatibleClient:
    base_url: str
    api_key_env: str
    model: str
    timeout_seconds: int = 120
    max_output_tokens: int | None = None
    temperature: float | None = 0.2
    reasoning_effort: str = ""
    response_format_json: bool = True
    extra_body: dict[str, Any] | None = None
    max_retries: int = 1
    retry_backoff_seconds: float = 1.0
    metrics: RunMetrics | None = None
    operation_timeouts: dict[str, float] = field(default_factory=lambda: {"email_extraction": 45.0, "paper_ranking": 90.0})
    request_budget_seconds: float = 120.0
    operation_settings: dict[str, dict[str, Any]] = field(default_factory=dict)
    _network_slots: BoundedSemaphore = field(default_factory=lambda: BoundedSemaphore(8), init=False, repr=False)

    def complete(self, prompt: str) -> str:
        if self.api_key_env.strip().lower().startswith("sk-"):
            raise LLMError(
                "openai_compatible.api_key_env looks like an API key. "
                "Set it to an environment variable name such as DEEPSEEK_API_KEY, "
                "and put the real key in .env."
            )
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise LLMError(f"Missing API key environment variable: {self.api_key_env}")
        if not self.base_url:
            raise LLMError("Missing openai_compatible.base_url")
        if not self.model:
            raise LLMError("Missing openai_compatible.model")

        operation = current_llm_operation()
        settings = self.operation_settings.get(operation, {})
        extra_body = dict(self.extra_body or {})
        if "thinking" in settings:
            extra_body["thinking"] = {"type": settings["thinking"]}
        thinking = extra_body.get("thinking", {}).get("type", "unspecified")
        reasoning_effort = settings.get("reasoning_effort", self.reasoning_effort)
        if thinking == "disabled":
            reasoning_effort = ""
        temperature = settings.get("temperature", self.temperature)
        max_output_tokens = settings.get("max_output_tokens", self.max_output_tokens)
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None and thinking != "enabled":
            body["temperature"] = temperature
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
        if self.response_format_json:
            body["response_format"] = {"type": "json_object"}
        if max_output_tokens:
            body["max_tokens"] = max_output_tokens
        body.update(extra_body)

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        deadline = _REQUEST_DEADLINE.get()
        if deadline is None:
            deadline = perf_counter() + self._operation_budget()
        parent_deadline = current_llm_deadline()
        if parent_deadline is not None:
            deadline = min(deadline, parent_deadline)
        operation_timeout = self.operation_timeouts.get(operation, self.timeout_seconds)
        attempt_timeout = max(0.001, float(settings.get("timeout_seconds", min(float(self.timeout_seconds), float(operation_timeout)))))
        for attempt in range(max(0, self.max_retries) + 1):
            self._check_budget(deadline)
            started_at = perf_counter()
            timeout = min(attempt_timeout, deadline - started_at)
            self._event("llm_request_started", operation=operation, attempt=attempt + 1,
                        timeout_seconds=round(timeout, 3), prompt_chars=len(prompt),
                        model=self.model, thinking=thinking, reasoning_effort=reasoning_effort,
                        max_output_tokens=max_output_tokens)
            retryable = False
            failure: Exception | None = None
            status = "ok"
            finish_reason: str | None = None
            usage: dict[str, Any] | None = None
            try:
                payload = self._request_payload(request, timeout)
                if not isinstance(payload, dict):
                    raise TypeError("response JSON was not an object")
                choice = payload["choices"][0]
                if not isinstance(choice, dict):
                    raise TypeError("response choice was not an object")
                raw_usage = payload.get("usage")
                usage = raw_usage if isinstance(raw_usage, dict) else None
                raw_finish_reason = choice.get("finish_reason")
                finish_reason = raw_finish_reason if isinstance(raw_finish_reason, str) or raw_finish_reason is None else "unknown"
                if finish_reason == "length":
                    raise LLMOutputTruncatedError(
                        "OpenAI-compatible API output reached its length limit; partial content was discarded."
                    )
                if finish_reason not in (None, "stop"):
                    if finish_reason not in {"content_filter", "insufficient_system_resource", "aborted"}:
                        finish_reason = "unknown"
                    code = finish_reason if finish_reason != "unknown" else "invalid_finish_reason"
                    raise LLMError(f"OpenAI-compatible API completion failed: {code}", code=code)
                content = choice["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("message content was not a string")
            except urllib.error.HTTPError as exc:
                status = f"http_{exc.code}"
                retryable = exc.code in {408, 429, 500, 502, 503, 504}
                failure = LLMError(f"OpenAI-compatible API failed: HTTP {exc.code}", code=status)
            except OSError as exc:
                reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
                status = "timeout" if isinstance(reason, TimeoutError) else "network_error"
                retryable = _transient_network_error(exc)
                failure = LLMError(f"OpenAI-compatible API request failed: {status} ({type(exc).__name__})", code=status)
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError, IndexError) as exc:
                status = "invalid_response"
                failure = LLMError(f"OpenAI-compatible API returned an invalid response ({type(exc).__name__})", code=status)
            except LLMError as exc:
                status = exc.code
                failure = exc
            if failure is None:
                self._record_request(started_at, prompt, attempt, usage=usage)
                self._event("llm_request_finished", operation=operation, attempt=attempt + 1,
                            status="ok", elapsed_seconds=round(perf_counter() - started_at, 3),
                            finish_reason=finish_reason)
                self._check_budget(deadline)
                return content.strip()
            self._record_request(started_at, prompt, attempt, status=status, usage=usage)
            self._event("llm_request_finished", operation=operation, attempt=attempt + 1,
                        status=status, elapsed_seconds=round(perf_counter() - started_at, 3),
                        finish_reason=finish_reason)
            if not retryable or attempt >= max(0, self.max_retries):
                raise failure
            self._check_budget(deadline)
            delay = max(0.0, self.retry_backoff_seconds) * (2**attempt)
            if delay >= deadline - perf_counter():
                raise LLMError("OpenAI-compatible API total request budget exhausted before retry", code="budget_exhausted")
            self._event("llm_retry_wait", operation=operation, next_attempt=attempt + 2,
                        delay_seconds=delay, previous_status=status)
            cancel_event = getattr(self.metrics, "cancel_event", None)
            if cancel_event is not None:
                cancel_event.wait(delay)
            else:
                sleep(delay)
            self._check_budget(deadline)
        raise LLMError("OpenAI-compatible API request failed", code="network_error")

    def _request_payload(self, request: urllib.request.Request, timeout: float) -> Any:
        """Bound wall time even during DNS, TLS, or a slowly trickling response.

        urllib's timeout is a socket inactivity limit, not a total deadline.
        A daemon worker allows immediate cancellation without interpreter-exit joins.
        An already dispatched POST cannot be recalled; its worker may finish later.
        """
        results: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        expires = perf_counter() + timeout
        while not self._network_slots.acquire(timeout=min(0.1, max(0.0, expires - perf_counter()))):
            self._check_cancelled()
            if perf_counter() >= expires:
                raise TimeoutError("network worker capacity deadline exceeded")

        operation = current_llm_operation()
        def fetch() -> None:
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    self._event("llm_response_headers", operation=operation,
                                http_status=getattr(response, "status", None))
                    if hasattr(response, "read1"):
                        chunks = []
                        saw_keepalive = False
                        while True:
                            chunk = response.read1(65536)
                            if not chunk:
                                break
                            chunks.append(chunk)
                            if not chunk.strip() and not saw_keepalive:
                                saw_keepalive = True
                                self._event("llm_server_keepalive", operation=operation)
                        raw = b"".join(chunks)
                    else:
                        raw = response.read()
                    result = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                results.put((False, exc))
            else:
                results.put((True, result))
            finally:
                self._network_slots.release()

        Thread(target=fetch, name="llm-http", daemon=True).start()
        while True:
            self._check_cancelled()
            remaining = expires - perf_counter()
            if remaining <= 0:
                raise TimeoutError("request wall-clock deadline exceeded")
            try:
                ok, result = results.get(timeout=min(0.1, remaining))
            except Empty:
                continue
            if not ok:
                raise result
            return result

    def _check_cancelled(self) -> None:
        event = getattr(self.metrics, "cancel_event", None)
        if event is not None and event.is_set():
            raise LLMError("OpenAI-compatible API request cancelled", code="cancelled")

    def _check_budget(self, deadline: float) -> None:
        self._check_cancelled()
        if perf_counter() >= deadline:
            raise LLMError("OpenAI-compatible API total request budget exhausted", code="budget_exhausted")

    def _event(self, name: str, **fields: Any) -> None:
        if self.metrics is not None and hasattr(self.metrics, "event"):
            self.metrics.event(name, **fields)

    def _operation_budget(self) -> float:
        settings = self.operation_settings.get(current_llm_operation(), {})
        return max(0.001, float(settings.get("request_budget_seconds", self.request_budget_seconds)))

    def complete_json(self, prompt: str) -> dict[str, Any]:
        deadline = perf_counter() + self._operation_budget()
        inherited = _REQUEST_DEADLINE.get()
        if inherited is not None:
            deadline = min(deadline, inherited)
        parent_deadline = current_llm_deadline()
        if parent_deadline is not None:
            deadline = min(deadline, parent_deadline)
        token = _REQUEST_DEADLINE.set(deadline)
        try:
            self._check_budget(deadline)
            first_response = self.complete(prompt)
            try:
                return extract_json_object(first_response)
            except LLMError:
                self._record_validation_failure("invalid_json")
                self._check_budget(deadline)
                retry_prompt = f"""
{prompt}

Your previous response could not be parsed as JSON.
Return ONLY one valid JSON object that follows the requested schema.
Do not include Markdown fences, explanations, reasoning text, status text, or any text before or after the JSON object.
The first character must be `{{` and the last character must be `}}`.
""".strip()
                self._event("llm_json_repair", operation=current_llm_operation())
                with llm_json_retry():
                    second_response = self.complete(retry_prompt)
                try:
                    return extract_json_object(second_response)
                except LLMError as exc:
                    self._record_validation_failure("invalid_json")
                    raise LLMError(
                        "OpenAI-compatible API response did not contain a parseable JSON object after repair.",
                        code="invalid_json",
                    ) from exc
        finally:
            _REQUEST_DEADLINE.reset(token)

    def _record_validation_failure(self, code: str) -> None:
        if self.metrics is not None and hasattr(self.metrics, "record_llm_validation_failure"):
            self.metrics.record_llm_validation_failure(code=code)
        else:
            self._event("llm_validation_failed", operation=current_llm_operation(), code=code)

    def _record_request(
        self,
        started_at: float,
        prompt: str,
        attempt: int,
        *,
        status: str = "ok",
        usage: dict[str, Any] | None = None,
    ) -> None:
        if self.metrics is None:
            return
        self.metrics.record_llm_request(
            elapsed_seconds=perf_counter() - started_at,
            prompt_chars=len(prompt),
            retry=attempt > 0,
            status=status,
            usage=usage,
        )


def _shorten_for_error(text: str, limit: int = 800) -> str:
    compact = " ".join(redact_secrets(text).split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _transient_network_error(exc: OSError) -> bool:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        return False
    if isinstance(reason, (TimeoutError, ConnectionError)):
        return True
    if isinstance(reason, socket.gaierror):
        return reason.errno == socket.EAI_AGAIN
    return isinstance(reason, OSError) and reason.errno in {
        errno.ECONNRESET, errno.ECONNREFUSED, errno.ECONNABORTED,
        errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH, errno.EPIPE,
    }
