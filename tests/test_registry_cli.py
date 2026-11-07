from __future__ import annotations

import json

from literature_digest import cli
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.sample_data import sample_emails
from literature_digest.telemetry import RunMetrics, llm_operation


def _write_config(tmp_path) -> str:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "gmail": {
                    "credentials_path": "credentials.json",
                    "mark_as_read": False,
                },
                "research_interests": {
                    "path": "research_interests.md",
                    "cache_path": "data/cache/interests.json",
                },
                "parsing": {"llm_structure_non_scholar": False},
                "deduplication": {
                    "registry_path": "data/paper_registry.json",
                    "retention_days": 30,
                    "bootstrap_from_outputs": True,
                },
                "digest": {
                    "output_dir": "outputs",
                    "output_formats": ["md"],
                    "overwrite_existing": True,
                },
                "progress": {"enabled": False},
                "performance": {
                    "parsing_max_workers": 1,
                    "ranking_max_workers": 1,
                    "ranking_batch_size": 20,
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / "research_interests.md").write_text("COF thermal transport", encoding="utf-8")
    return str(config_path)


def _patch_external_clients(monkeypatch) -> None:
    def fake_fetch(self, max_results):
        self.last_result_size_estimate = 137
        return sample_emails()[:1]

    monkeypatch.setattr(
        cli.GmailClient,
        "fetch_unread_emails",
        fake_fetch,
    )
    monkeypatch.setattr(
        cli,
        "build_llm_client",
        lambda config, sample_mode, metrics: OfflineStubClient(),
    )


def test_dry_run_reads_but_does_not_write_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    _patch_external_clients(monkeypatch)

    result = cli.main(["--config", config_path, "--dry-run", "--date", "2026-08-20", "--quiet"])

    assert result == 0
    assert (tmp_path / "outputs" / "2026-08-20-digest.md").exists()
    assert not (tmp_path / "data" / "paper_registry.json").exists()


def test_completed_runs_update_registry_and_filter_the_next_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    _patch_external_clients(monkeypatch)

    first_result = cli.main(
        ["--config", config_path, "--no-dry-run", "--date", "2026-08-20", "--quiet"]
    )
    second_result = cli.main(
        ["--config", config_path, "--no-dry-run", "--date", "2026-08-21", "--quiet"]
    )

    registry_path = tmp_path / "data" / "paper_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    second_digest = (tmp_path / "outputs" / "2026-08-21-digest.md").read_text(encoding="utf-8")

    assert first_result == second_result == 0
    assert registry["updated_at"] == "2026-08-21"
    assert len(registry["papers"]) == 2
    assert {record["seen_count"] for record in registry["papers"].values()} == {2}
    assert "近 30 天 JSON 身份索引移除 2 篇重复论文" in second_digest


def test_cli_reports_unread_estimate(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    config["progress"]["enabled"] = True
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    _patch_external_clients(monkeypatch)

    result = cli.main(["--config", config_path, "--dry-run", "--date", "2026-08-20"])

    output = capsys.readouterr().out
    assert result == 0
    assert "邮箱中符合当前查询条件" not in output
    logs = list((tmp_path / "logs").glob("digest-*.log"))
    assert len(logs) == 1
    assert "邮箱中符合当前查询条件的未读邮件约 137 封；本次读取 1 封" in logs[0].read_text()


def test_zero_emails_stops_before_llm_and_digest(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    config["progress"]["enabled"] = True
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

    def fake_fetch(self, max_results):
        self.last_result_size_estimate = 0
        return []

    monkeypatch.setattr(cli.GmailClient, "fetch_unread_emails", fake_fetch)
    monkeypatch.setattr(
        cli,
        "build_llm_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM client must not be built")),
    )
    monkeypatch.setattr(
        cli,
        "write_digests",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("digest must not be written")),
    )

    result = cli.main(["--config", config_path, "--dry-run", "--date", "2026-09-02"])

    output = capsys.readouterr().out
    assert result == 0
    log = next((tmp_path / "logs").glob("digest-*.log")).read_text()
    assert "邮箱中符合当前查询条件的未读邮件约 0 封；本次读取 0 封" in log
    assert "需要提取的邮件为 0，无需进行后续处理" in output
    assert "Digest written:" not in output
    assert not (tmp_path / "outputs").exists()
    assert not (tmp_path / "data" / "paper_registry.json").exists()


def test_detailed_metrics_are_written_to_log_only(tmp_path):
    metrics = RunMetrics()
    with llm_operation("paper_ranking", 20):
        metrics.record_llm_request(
            elapsed_seconds=21.04,
            prompt_chars=23387,
            usage={"prompt_tokens": 6277, "completion_tokens": 3267, "total_tokens": 9544},
        )

    compact = "\n".join(metrics.summary_lines(include_request_details=False))
    path = cli._write_detailed_metrics_log(
        metrics,
        base_dir=tmp_path,
        config={"detailed_log_enabled": True, "log_dir": "logs/metrics"},
    )

    assert path is not None and path.exists()
    assert "request#1" not in compact
    assert "request#1: operation=paper_ranking" in path.read_text(encoding="utf-8")


def test_degraded_api_run_preserves_unread_emails_and_registry(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = json.loads((tmp_path / "config.json").read_text())
    config["gmail"]["mark_as_read"] = True
    (tmp_path / "config.json").write_text(json.dumps(config))
    _patch_external_clients(monkeypatch)
    original_rank = cli.rank_papers

    def degraded_rank(*args, **kwargs):
        kwargs["event_callback"]("论文排序 1/1：LLM 失败（LLMError，code=output_length），回退本地规则")
        return original_rank(*args, **kwargs)

    def unexpected_mark(*args, **kwargs):
        raise AssertionError("degraded output must not mark emails as read")

    monkeypatch.setattr(cli, "rank_papers", degraded_rank)
    monkeypatch.setattr(cli.GmailClient, "mark_as_read", unexpected_mark)
    result = cli.main(["--config", config_path, "--no-dry-run", "--date", "2026-08-20", "--quiet"])

    output = capsys.readouterr().out
    assert result == 0
    assert not (tmp_path / "data" / "paper_registry.json").exists()
    assert "本地规则回退" in output
    assert "邮件保持未读" in output
    assert "输出超长" in output
    assert "API 恢复后" not in output
    digest = (tmp_path / "outputs" / "2026-08-20-digest.md").read_text()
    assert "部分条目或推荐使用本地规则回退" in digest
    log = next((tmp_path / "logs").glob("digest-*.log")).read_text()
    assert "LLM 失败（LLMError，code=output_length）" in log
    assert "LLM 失败（LLMError，code=output_length）" not in output


def test_old_outputs_are_pruned_only_after_enabled_formal_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    _patch_external_clients(monkeypatch)
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    old = outputs / '2020-01-01-digest.html'
    old.touch()
    args = ['--config', config_path, '--date', '2020-01-02', '--quiet']

    assert cli.main([*args, '--no-dry-run']) == 0
    assert old.exists()
    config = json.loads((tmp_path / 'config.json').read_text())
    config['digest']['cleanup_old_outputs'] = True
    (tmp_path / 'config.json').write_text(json.dumps(config))
    assert cli.main([*args, '--dry-run']) == 0
    assert old.exists()
    assert cli.main([*args, '--no-dry-run']) == 0
    assert not old.exists()
    assert (outputs / '2020-01-02-digest.md').exists()
