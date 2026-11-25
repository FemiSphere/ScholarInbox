"""Operation policies remain isolated when a shared client serves parallel tasks."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from literature_digest.llm.base import LLMError
from literature_digest.llm.factory import build_llm_client
from literature_digest.llm.openai_compatible import OpenAICompatibleClient
from literature_digest.telemetry import llm_operation


def make_client(monkeypatch, **kwargs):
    monkeypatch.setenv("TEST_POLICY_KEY", "offline-key")
    return OpenAICompatibleClient(
        base_url="https://unused.invalid", api_key_env="TEST_POLICY_KEY", model="test",
        extra_body={"thinking": {"type": "disabled"}}, max_output_tokens=4000,
        retry_backoff_seconds=0, **kwargs,
    )


def test_parallel_thinking_and_translation_payloads_are_isolated(monkeypatch):
    policies = {
        "paper_ranking": {"thinking": "enabled", "reasoning_effort": "high", "max_output_tokens": 12000, "timeout_seconds": 150, "request_budget_seconds": 180},
        "paper_translation": {"thinking": "disabled", "max_output_tokens": 4000, "timeout_seconds": 90},
    }
    client = make_client(monkeypatch, operation_settings=policies, timeout_seconds=120)
    rendezvous = threading.Barrier(2)
    seen = {}

    def fetch(self, request, timeout):
        body = json.loads(request.data)
        operation = body["messages"][0]["content"]
        seen[operation] = (body, timeout)
        rendezvous.wait(timeout=2)
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    monkeypatch.setattr(OpenAICompatibleClient, "_request_payload", fetch)

    def run(operation):
        with llm_operation(operation, 1):
            return client.complete_json(operation)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run, policies)) == [{"ok": True}, {"ok": True}]
    ranking, timeout = seen["paper_ranking"]
    assert ranking["thinking"] == {"type": "enabled"}
    assert ranking["reasoning_effort"] == "high"
    assert ranking["max_tokens"] == 12000
    assert "temperature" not in ranking
    assert timeout == 150
    translation, timeout = seen["paper_translation"]
    assert translation["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in translation
    assert translation["temperature"] == 0.2
    assert translation["max_tokens"] == 4000
    assert timeout == 90
    assert client.extra_body == {"thinking": {"type": "disabled"}}
    assert client.max_output_tokens == 4000
    assert client.reasoning_effort == ""


def test_operation_budget_shared_by_retries_and_json_repair(monkeypatch):
    client = make_client(monkeypatch, operation_settings={"paper_ranking": {"request_budget_seconds": 0.1}})
    calls = []
    # A fake clock keeps this deterministic on slow CI machines: each request "takes" 0.04 s
    # and retry back-off sleeps advance the same clock instead of real time.
    from literature_digest.llm import openai_compatible as module
    clock = [0.0]
    monkeypatch.setattr(module, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(module, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def fetch(self, request, timeout):
        calls.append(timeout)
        clock[0] += 0.04
        if len(calls) == 1:
            raise TimeoutError()
        return {"choices": [{"message": {"content": "not json"}}]}

    monkeypatch.setattr(OpenAICompatibleClient, "_request_payload", fetch)
    with llm_operation("paper_ranking", 1):
        with pytest.raises(LLMError, match="budget"):
            client.complete_json("prompt")
    assert len(calls) == 3
    assert calls[0] <= 0.1
    assert calls[2] < calls[1] < calls[0]
    assert client.request_budget_seconds == 120


def test_factory_uses_top_level_budgets_with_legacy_fallback():
    config = {"llm": {"provider": "openai_compatible", "request_budget_seconds": 180,
        "operation_timeouts": {"paper_ranking": 100},
        "operation_settings": {"paper_ranking": {"thinking": "enabled"}},
        "openai_compatible": {"request_budget_seconds": 30,
            "operation_timeouts": {"paper_ranking": 40, "legacy": 20}}}, "safety": {}}
    client = build_llm_client(config)
    assert client.request_budget_seconds == 180
    assert client.operation_timeouts["paper_ranking"] == 100
    assert client.operation_timeouts["legacy"] == 20
    assert client.operation_settings["paper_ranking"]["thinking"] == "enabled"
    del config["llm"]["request_budget_seconds"]
    del config["llm"]["operation_timeouts"]
    client = build_llm_client(config)
    assert client.request_budget_seconds == 30
    assert client.operation_timeouts["paper_ranking"] == 40
