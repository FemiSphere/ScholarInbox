"""Provider output limits must never silently produce partial paper lists."""
import json
import urllib.error
from time import perf_counter

import pytest

from literature_digest.llm import (
    LLMError, LLMOutputTruncatedError, current_llm_deadline, llm_time_budget,
)
from literature_digest.llm.base import extract_json_object
from literature_digest.llm.openai_compatible import OpenAICompatibleClient
from literature_digest.telemetry import RunMetrics, llm_operation


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OUTPUT_VALIDATION_TEST_KEY", "offline-test-key")
    metrics = RunMetrics()
    events = []
    metrics.event_callback = lambda name, fields: events.append((name, fields))
    api = OpenAICompatibleClient(
        base_url="https://unused.invalid", api_key_env="OUTPUT_VALIDATION_TEST_KEY",
        model="offline", metrics=metrics, retry_backoff_seconds=0,
    )
    return api, events


def stub_payload(monkeypatch, content, finish_reason):
    calls = []

    def fetch(self, request, timeout):
        calls.append(timeout)
        return {
            "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4000, "total_tokens": 4010},
        }

    monkeypatch.setattr(OpenAICompatibleClient, "_request_payload", fetch)
    return calls


@pytest.mark.parametrize("content", ['{"papers":[]}', '{"papers":[', "", None])
def test_length_is_rejected_without_repair_or_retry_even_for_valid_json(client, monkeypatch, content):
    api, events = client
    calls = stub_payload(monkeypatch, content, "length")
    with llm_operation("email_extraction", 1):
        with pytest.raises(LLMOutputTruncatedError) as error:
            api.complete_json("private mail body")
    assert isinstance(error.value, LLMError)
    assert error.value.code == "output_length"
    assert len(calls) == 1
    assert [metric.status for metric in api.metrics.llm_requests] == ["output_length"]
    assert api.metrics.llm_requests[0].total_tokens == 4010
    finished = [fields for name, fields in events if name == "llm_request_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "output_length"
    assert finished[0]["finish_reason"] == "length"
    assert not any(name in {"llm_json_repair", "llm_validation_failed", "llm_retry_wait"} for name, _ in events)
    assert "private mail body" not in json.dumps(events)


@pytest.mark.parametrize("reason", ["content_filter", "insufficient_system_resource", "aborted"])
def test_nonstop_finish_reasons_have_stable_failure_codes(client, monkeypatch, reason):
    api, events = client
    calls = stub_payload(monkeypatch, '{"papers":[]}', reason)
    with pytest.raises(LLMError) as error:
        api.complete_json("prompt")
    assert error.value.code == reason
    assert len(calls) == 1
    assert api.metrics.llm_requests[0].status == reason
    assert not any(name == "llm_json_repair" for name, _ in events)


@pytest.mark.parametrize("reason", ["private provider data", ["private provider data"], {"private provider data": True}])
def test_unknown_finish_reason_not_echoed_as_error_or_event(client, monkeypatch, reason):
    api, events = client
    stub_payload(monkeypatch, '{"ok":true}', reason)
    with pytest.raises(LLMError) as error:
        api.complete_json("prompt")
    assert error.value.code == "invalid_finish_reason"
    assert "private provider data" not in str(error.value)
    assert "private provider data" not in json.dumps(events)


@pytest.mark.parametrize("repaired", [True, False])
def test_semantic_json_failures_are_visible_without_double_counting_transport(client, monkeypatch, repaired):
    api, events = client
    calls = []

    def fetch(self, request, timeout):
        calls.append(1)
        content = '{"ok":true}' if repaired and len(calls) == 2 else "private malformed response"
        return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}

    monkeypatch.setattr(OpenAICompatibleClient, "_request_payload", fetch)
    if repaired:
        assert api.complete_json("private prompt") == {"ok": True}
    else:
        with pytest.raises(LLMError) as error:
            api.complete_json("private prompt")
        assert error.value.code == "invalid_json"
        assert "private" not in str(error.value)
    assert len(calls) == 2
    assert [m.status for m in api.metrics.llm_requests] == ["ok", "ok"]
    failures = [fields for name, fields in events if name == "llm_validation_failed"]
    assert len(failures) == (1 if repaired else 2)
    assert all(fields["code"] == "invalid_json" for fields in failures)
    assert "private malformed response" not in json.dumps(events)


@pytest.mark.parametrize("error,code", [
    (TimeoutError(), "timeout"),
    (urllib.error.URLError(TimeoutError()), "timeout"),
    (ConnectionResetError(), "network_error"),
])
def test_transport_codes_are_stable(client, monkeypatch, error, code):
    api, _ = client
    api.max_retries = 0

    def fetch(self, request, timeout):
        raise error

    monkeypatch.setattr(OpenAICompatibleClient, "_request_payload", fetch)
    with pytest.raises(LLMError) as raised:
        api.complete_json("prompt")
    assert raised.value.code == code
    assert api.metrics.llm_requests[0].status == code


def test_parent_budget_caps_complete_and_complete_json_and_resets(client, monkeypatch):
    api, _ = client
    seen = stub_payload(monkeypatch, '{"ok":true}', "stop")
    assert current_llm_deadline() is None
    with llm_time_budget(0.5):
        parent_deadline = current_llm_deadline()
        assert parent_deadline <= perf_counter() + 0.5
        with llm_time_budget(10):
            assert current_llm_deadline() == parent_deadline
            assert api.complete_json("prompt") == {"ok": True}
            assert api.complete("prompt") == '{"ok":true}'
        with llm_time_budget(0.1):
            assert current_llm_deadline() < parent_deadline
        assert current_llm_deadline() == parent_deadline
    assert current_llm_deadline() is None
    assert all(0 < timeout <= 0.5 for timeout in seen)


def test_expired_parent_budget_does_not_dispatch_request(client, monkeypatch):
    api, _ = client
    calls = stub_payload(monkeypatch, '{"ok":true}', "stop")
    with llm_time_budget(0):
        with pytest.raises(LLMError) as error:
            api.complete_json("prompt")
    assert error.value.code == "budget_exhausted"
    assert calls == []


def test_base_error_and_json_error_codes():
    assert LLMError("failure").code == "llm_error"
    assert LLMError("failure", code="custom").code == "custom"
    with pytest.raises(LLMError) as error:
        extract_json_object("malformed")
    assert error.value.code == "invalid_json"
