import json
from pathlib import Path

from literature_digest.telemetry import RunMetrics, llm_operation
from literature_digest import cli


def test_request_metrics_persist_before_run_finishes(tmp_path):
    path = tmp_path / 'requests.jsonl'
    metrics = RunMetrics()
    metrics.configure_journal(path)
    with llm_operation('email_extraction', 1):
        metrics.record_llm_request(elapsed_seconds=0.1, prompt_chars=123, status='timeout')
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert records[-1]['event'] == 'llm_request_metric'
    assert records[-1]['operation'] == 'email_extraction'
    assert records[-1]['status'] == 'timeout'
    assert 'prompt' not in records[-1]


def test_cli_interrupt_preserves_partial_metrics_and_returns_130(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def interrupted(argv, metrics, resources):
        resources['config'] = {'telemetry': {'log_dir': 'logs/metrics'}}
        metrics.configure_journal(tmp_path / 'requests.jsonl')
        metrics.record_llm_request(elapsed_seconds=0.1, prompt_chars=1)
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, '_main', interrupted)
    assert cli.main([]) == 130
    assert list((tmp_path / 'logs/metrics').glob('metrics-*.log'))
    records = [json.loads(line) for line in (tmp_path / 'requests.jsonl').read_text().splitlines()]
    assert records[-1]['status'] == 'cancelled'


def test_cli_exception_preserves_partial_metrics(tmp_path, monkeypatch):
    import pytest
    monkeypatch.chdir(tmp_path)
    def failed(argv, metrics, resources):
        resources['config'] = {'telemetry': {'log_dir': 'logs/metrics'}}
        metrics.record_io_request(operation='test', item_count=1, elapsed_seconds=0.1)
        raise RuntimeError('test failure')
    monkeypatch.setattr(cli, '_main', failed)
    with pytest.raises(RuntimeError):
        cli.main([])
    assert list((tmp_path / 'logs/metrics').glob('metrics-*.log'))
