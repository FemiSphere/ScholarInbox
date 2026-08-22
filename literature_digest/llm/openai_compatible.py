from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Any

from .base import LLMError, extract_json_object, redact_secrets
from ..telemetry import RunMetrics, llm_json_retry


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
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    metrics: RunMetrics | None = None

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

        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if self.response_format_json:
            body["response_format"] = {"type": "json_object"}
        if self.max_output_tokens:
            body["max_tokens"] = self.max_output_tokens
        if self.extra_body:
            body.update(self.extra_body)

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        payload: dict[str, Any] = {}
        for attempt in range(max(0, self.max_retries) + 1):
            started_at = perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    decoded = json.loads(response.read().decode("utf-8"))
                    if not isinstance(decoded, dict):
                        raise TypeError("response JSON was not an object")
                    payload = decoded
            except urllib.error.HTTPError as exc:
                self._record_request(started_at, prompt, attempt, status=f"http_{exc.code}")
                body_text = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 500, 502, 503, 504} and attempt < max(0, self.max_retries):
                    sleep(max(0.0, self.retry_backoff_seconds) * (2**attempt))
                    continue
                raise LLMError(
                    f"OpenAI-compatible API failed: HTTP {exc.code}: {redact_secrets(body_text)}"
                ) from exc
            except OSError as exc:
                self._record_request(started_at, prompt, attempt, status="network_error")
                if attempt < max(0, self.max_retries):
                    sleep(max(0.0, self.retry_backoff_seconds) * (2**attempt))
                    continue
                raise LLMError(f"OpenAI-compatible API request failed: {exc}") from exc
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
                self._record_request(started_at, prompt, attempt, status="invalid_response")
                if attempt < max(0, self.max_retries):
                    sleep(max(0.0, self.retry_backoff_seconds) * (2**attempt))
                    continue
                raise LLMError(f"OpenAI-compatible API returned invalid JSON: {exc}") from exc
            else:
                self._record_request(started_at, prompt, attempt, usage=payload.get("usage"))
                break

        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("OpenAI-compatible API response did not contain message content.") from exc

    def complete_json(self, prompt: str) -> dict[str, Any]:
        first_response = self.complete(prompt)
        try:
            return extract_json_object(first_response)
        except LLMError:
            retry_prompt = f"""
{prompt}

Your previous response could not be parsed as JSON.
Return ONLY one valid JSON object that follows the requested schema.
Do not include Markdown fences, explanations, reasoning text, status text, or any text before or after the JSON object.
The first character must be `{{` and the last character must be `}}`.
""".strip()
            with llm_json_retry():
                second_response = self.complete(retry_prompt)
            try:
                return extract_json_object(second_response)
            except LLMError as exc:
                preview = _shorten_for_error(second_response or first_response)
                raise LLMError(
                    "OpenAI-compatible API response did not contain a parseable JSON object after retry. "
                    f"Response preview: {preview}"
                ) from exc

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
