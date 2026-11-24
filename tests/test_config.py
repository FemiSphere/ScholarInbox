import io
import json
import urllib.error
from pathlib import Path

from literature_digest.config import DEFAULT_CONFIG, load_config
from literature_digest.llm import LLMError
from literature_digest.llm.base import extract_json_object
from literature_digest.llm.openai_compatible import OpenAICompatibleClient
from literature_digest.telemetry import RunMetrics, llm_operation


def test_load_config_merges_external_llm_config(tmp_path, monkeypatch):
    llm_dir = tmp_path / "config" / "llm"
    llm_dir.mkdir(parents=True)
    (llm_dir / "deepseek.local.yaml").write_text(
        """
provider: "openai_compatible"
timeout_seconds: 300
max_output_tokens: 4000
openai_compatible:
  base_url: "https://api.deepseek.com"
  api_key_env: "DEEPSEEK_API_KEY"
  model: "deepseek-flash"
  extra_body:
    thinking:
      type: "disabled"
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.local.yaml"
    config_path.write_text(
        """
llm:
  config_path: "config/llm/deepseek.local.yaml"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config(config_path)

    assert config["llm"]["provider"] == "openai_compatible"
    assert config["llm"]["timeout_seconds"] == 300
    assert config["llm"]["openai_compatible"]["model"] == "deepseek-flash"
    assert config["llm"]["openai_compatible"]["extra_body"]["thinking"]["type"] == "disabled"


def test_default_digest_config_includes_irrelevant_outputs():
    assert DEFAULT_CONFIG["digest"]["include_irrelevant"] is True
    assert DEFAULT_CONFIG["digest"]["max_irrelevant"] == 80


def test_openai_compatible_rejects_api_key_as_env_name():
    fake_key = "sk-" + "testsecret1234567890"
    client = OpenAICompatibleClient(
        base_url="https://api.deepseek.com",
        api_key_env=fake_key,
        model="deepseek-flash",
    )

    try:
        client.complete("hello")
    except LLMError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected LLMError")

    assert "looks like an API key" in message
    assert fake_key not in message


class RetryJSONClient(OpenAICompatibleClient):
    def __init__(self):
        super().__init__(
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
            model="deepseek-flash",
        )
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return "not json"
        return '{"ok": true}'


def test_openai_compatible_complete_json_retries_non_json_response():
    client = RetryJSONClient()

    payload = client.complete_json("Return JSON.")

    assert payload == {"ok": True}
    assert client.calls == 2


class RetryMalformedJSONClient(OpenAICompatibleClient):
    def __init__(self):
        super().__init__(
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
            model="deepseek-flash",
        )
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return '{"papers": [{"title": "Broken" "url": "https://example.com"}]}'
        return '{"papers": []}'


def test_extract_json_object_wraps_malformed_sliced_json():
    try:
        extract_json_object('prefix {"papers": [{"title": "Broken" "url": "https://example.com"}]} suffix')
    except LLMError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected LLMError")

    assert "malformed JSON object" in message


def test_openai_compatible_complete_json_retries_malformed_json_response():
    client = RetryMalformedJSONClient()

    payload = client.complete_json("Return JSON.")

    assert payload == {"papers": []}
    assert client.calls == 2


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_openai_compatible_records_usage_and_transport_retry(monkeypatch):
    calls = 0
    metrics = RunMetrics()

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                {},
                io.BytesIO(b'{"error":"busy"}'),
            )
        return FakeHTTPResponse(
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                    "prompt_cache_hit_tokens": 3,
                },
            }
        )

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-logged")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        model="test-model",
        retry_backoff_seconds=0,
        metrics=metrics,
    )

    with llm_operation("paper_ranking", 20):
        payload = client.complete_json("return json")

    assert payload == {"ok": True}
    assert calls == 2
    assert [metric.status for metric in metrics.llm_requests] == ["http_429", "ok"]
    assert metrics.llm_requests[1].retry is True
    assert metrics.llm_requests[1].total_tokens == 14
    assert metrics.llm_requests[1].cache_hit_tokens == 3


def test_llm_preset_is_loaded_and_inline_keys_override_it(tmp_path):
    from literature_digest.config import load_config

    config_path = tmp_path / "config.local.yaml"
    config_path.write_text(
        'llm:\n  preset: deepseek\n  openai_compatible:\n    temperature: 0.1\n', encoding="utf-8")
    config = load_config(config_path)
    assert config["llm"]["provider"] == "openai_compatible"
    assert config["llm"]["openai_compatible"]["base_url"] == "https://api.deepseek.com"
    assert config["llm"]["openai_compatible"]["temperature"] == 0.1
    assert config["llm"]["operation_settings"]["paper_ranking"]["thinking"] == "enabled"


def test_unknown_preset_is_reported(tmp_path):
    import pytest
    from literature_digest.config import load_config

    config_path = tmp_path / "config.local.yaml"
    config_path.write_text("llm:\n  preset: nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match="available"):
        load_config(config_path)


def test_legacy_example_config_path_maps_to_packaged_preset(tmp_path):
    from literature_digest.config import load_config

    config_path = tmp_path / "config.local.yaml"
    config_path.write_text('llm:\n  config_path: "config/llm/codex_cli.example.yaml"\n', encoding="utf-8")
    assert load_config(config_path)["llm"]["provider"] == "codex_cli"
