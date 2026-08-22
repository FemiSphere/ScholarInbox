from __future__ import annotations

import json

from literature_digest import cli
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.sample_data import sample_emails


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
    monkeypatch.setattr(
        cli.GmailClient,
        "fetch_unread_emails",
        lambda self, max_results: sample_emails()[:1],
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
