"""Offline coverage of deadlines, cancellation, and retry classification."""
import io
import json
import threading
import time
import urllib.error

import pytest

from literature_digest.llm.base import LLMError
from literature_digest.llm.openai_compatible import OpenAICompatibleClient
from literature_digest.telemetry import RunMetrics, llm_operation


class Response:
    def __init__(self, content='{"ok":true}'):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TEST_RESILIENCE_KEY", "not-a-real-key")
    return OpenAICompatibleClient(
        base_url="https://unused.invalid", api_key_env="TEST_RESILIENCE_KEY",
        model="offline-test", metrics=RunMetrics(), retry_backoff_seconds=0,
    )


def test_operation_timeout_overrides_legacy_300_seconds(client, monkeypatch):
    seen = []

    def fetch(request, timeout):
        seen.append(timeout)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    client.timeout_seconds = 300
    with llm_operation("email_extraction", 1):
        assert client.complete_json("private text") == {"ok": True}
    with llm_operation("paper_ranking", 1):
        client.complete_json("private text")
    assert seen == [45, 90]


@pytest.mark.parametrize("code", [400, 401, 402, 403, 404])
def test_permanent_http_errors_do_not_retry(client, monkeypatch, code):
    calls = []

    def fetch(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, code, "private error", {}, io.BytesIO(b"private text"))

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    with pytest.raises(LLMError, match=f"HTTP {code}") as error:
        client.complete_json("private text")
    assert "private" not in str(error.value)
    assert len(calls) == 1


def test_invalid_envelope_does_not_transport_retry(client, monkeypatch):
    calls = []

    def fetch(request, timeout):
        calls.append(1)
        return Response(None)

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    with pytest.raises(LLMError, match="invalid response"):
        client.complete_json("prompt")
    assert len(calls) == 1


def test_total_budget_includes_json_repair(client, monkeypatch):
    calls = []
    release = threading.Event()

    def fetch(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            time.sleep(0.04)
            return Response("not json")
        release.wait(1)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    client.request_budget_seconds = 0.15
    started = time.monotonic()
    try:
        with pytest.raises(LLMError, match="budget"):
            client.complete_json("prompt")
    finally:
        release.set()
    assert time.monotonic() - started < 0.5
    assert len(calls) == 2
    assert calls[1] < calls[0]


def test_cancel_interrupts_blocked_network(client, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    cancel = threading.Event()
    client.metrics.cancel_event = cancel

    def fetch(request, timeout):
        entered.set()
        release.wait(2)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    timer = threading.Timer(0.05, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(LLMError, match="cancelled"):
            client.complete_json("prompt")
    finally:
        release.set()
        timer.join()
    assert entered.is_set()
    assert time.monotonic() - started < 0.5
    assert client.metrics.llm_requests[-1].status == "cancelled"


def test_cancel_interrupts_retry_backoff(client, monkeypatch):
    cancel = threading.Event()
    client.metrics.cancel_event = cancel
    client.retry_backoff_seconds = 20
    calls = []

    def fetch(request, timeout):
        calls.append(1)
        threading.Timer(0.05, cancel.set).start()
        raise urllib.error.HTTPError(request.full_url, 429, "busy", {}, io.BytesIO())

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    started = time.monotonic()
    with pytest.raises(LLMError, match="cancelled"):
        client.complete_json("prompt")
    assert time.monotonic() - started < 0.5
    assert len(calls) == 1


def test_certificate_errors_do_not_retry(client, monkeypatch):
    import ssl
    calls = []

    def fetch(request, timeout):
        calls.append(1)
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "invalid certificate"))

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    with pytest.raises(LLMError, match="network_error"):
        client.complete_json("prompt")
    assert len(calls) == 1


def test_transient_transport_error_retries_once(client, monkeypatch):
    calls = []

    def fetch(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.URLError(ConnectionResetError("reset"))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fetch)
    assert client.complete_json("prompt") == {"ok": True}
    assert len(calls) == 2
    assert [item.status for item in client.metrics.llm_requests] == ["network_error", "ok"]


def test_process_exits_promptly_after_sigint_with_blocked_http(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    script = r"""
import os, time, urllib.request
from literature_digest import cli
from literature_digest.llm.openai_compatible import OpenAICompatibleClient
os.environ['CANCEL_TEST_KEY'] = 'fake'
def blocked(request, timeout):
    print('READY', flush=True)
    time.sleep(60)
urllib.request.urlopen = blocked
def run(argv, metrics, resources):
    client = OpenAICompatibleClient(base_url='https://unused.invalid',
        api_key_env='CANCEL_TEST_KEY', model='test', metrics=metrics)
    client.complete_json('test')
cli._main = run
raise SystemExit(cli.main([]))
"""
    process = subprocess.Popen([sys.executable, '-B', '-c', script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'READY'
        process.send_signal(signal.SIGINT)
        _, stderr = process.communicate(timeout=3)
        assert process.returncode == 130
        assert 'Traceback' not in stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_keepalive_before_json_is_logged_without_body(client, monkeypatch, tmp_path):
    class KeepaliveResponse(Response):
        status = 200
        def __init__(self):
            self.chunks = iter([b"\n\n", Response().read(), b""])
        def read1(self, size):
            return next(self.chunks)
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: KeepaliveResponse())
    journal = tmp_path / 'requests.jsonl'
    client.metrics.configure_journal(journal)
    assert client.complete_json('private prompt') == {'ok': True}
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert any(r['event'] == 'llm_response_headers' and r['http_status'] == 200 for r in records)
    assert any(r['event'] == 'llm_server_keepalive' for r in records)
    assert 'private prompt' not in journal.read_text()
