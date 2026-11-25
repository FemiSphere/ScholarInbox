from datetime import date

from literature_digest.cli import _remaining_unread_note
from literature_digest.housekeeping import prune_old_logs


def test_prune_old_logs_removes_only_program_logs_past_retention(tmp_path):
    logs = tmp_path / "logs"
    metrics = logs / "metrics"
    metrics.mkdir(parents=True)
    old = [logs / "digest-20261001-101010.log", metrics / "requests-20261001-101010-123.jsonl",
           metrics / "metrics-20261001-101010-123.log"]
    keep = [logs / "digest-20261120-101010-55.log", metrics / "requests-20261124-101010-1.jsonl",
            logs / "notes-20261001.log", logs / "digest-20261001.txt"]
    for path in old + keep:
        path.write_text("x")

    removed, failed = prune_old_logs([logs, metrics], today=date(2026, 11, 24), retention_days=30)

    assert removed == 3 and failed == []
    assert not any(path.exists() for path in old)
    assert all(path.exists() for path in keep)


def test_zero_retention_keeps_everything(tmp_path):
    (tmp_path / "digest-20200101-000000.log").write_text("x")
    assert prune_old_logs([tmp_path], today=date(2026, 11, 24), retention_days=0) == (0, [])
    assert (tmp_path / "digest-20200101-000000.log").exists()


def test_remaining_unread_note():
    assert _remaining_unread_note(None, 0) == ""
    assert "约 101 封" in _remaining_unread_note(201, 100)
    assert "已无" in _remaining_unread_note(98, 98)


def test_prune_stale_files_and_remove_files(tmp_path):
    import os
    import time
    from literature_digest.housekeeping import prune_stale_files, remove_files

    old, fresh = tmp_path / "old.json", tmp_path / "fresh.json"
    old.write_text("x"); fresh.write_text("x")
    week_old = time.time() - 40 * 86400
    os.utime(old, (week_old, week_old))
    (tmp_path / "sub").mkdir()
    assert prune_stale_files(tmp_path, max_age_days=30) == (1, [])
    assert not old.exists() and fresh.exists() and (tmp_path / "sub").exists()
    assert prune_stale_files(tmp_path / "missing", max_age_days=30) == (0, [])
    assert remove_files([fresh, tmp_path / "gone.json"]) == 1


def test_project_home_prefers_env_then_project_folder(tmp_path, monkeypatch):
    from literature_digest import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SCHOLAR_INBOX_HOME", ".")
    assert cli._project_home() == tmp_path.resolve()
    monkeypatch.delenv("SCHOLAR_INBOX_HOME")
    # an unrelated folder falls back to the source checkout (this repository)
    assert cli._project_home() == cli.Path(cli.__file__).resolve().parent.parent
    (tmp_path / "config.local.yaml").write_text("{}")
    assert cli._project_home() == tmp_path.resolve()


def test_anchor_keeps_relative_config_meaning(tmp_path, monkeypatch):
    from literature_digest import cli

    elsewhere, home = tmp_path / "elsewhere", tmp_path / "home"
    elsewhere.mkdir(); home.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("SCHOLAR_INBOX_HOME", str(home))
    args = cli._anchor_to_project(["--config", "my.yaml", "--quiet"])
    assert cli.Path.cwd() == home.resolve()
    assert args == ["--config", str((elsewhere / "my.yaml").resolve()), "--quiet"]


def test_parse_cache_of_processed_mail_is_deleted_after_mark_read(tmp_path, monkeypatch):
    from copy import deepcopy
    from literature_digest import cli
    from literature_digest.config import DEFAULT_CONFIG
    from literature_digest.llm.offline_stub import OfflineStubClient
    from literature_digest.sample_data import sample_emails

    monkeypatch.chdir(tmp_path)
    (tmp_path / "credentials.json").write_text("{}")
    (tmp_path / "research_interests.md").write_text("COF thermal transport")
    config = deepcopy(DEFAULT_CONFIG)
    config["llm"]["provider"] = "offline_stub"
    config["parsing"]["llm_structure_non_scholar"] = False
    config["ui"]["banner_enabled"] = False
    config["progress"]["enabled"] = False
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "build_llm_client", lambda *a, **k: OfflineStubClient())
    emails = sample_emails()[:2]  # same messages on both runs, as in a real mailbox
    monkeypatch.setattr(cli.GmailClient, "fetch_unread_emails", lambda self, **k: emails)
    monkeypatch.setattr(cli.GmailClient, "mark_as_read", lambda self, ids: None)
    cache = tmp_path / "data" / "cache" / "email_parsing"

    config["gmail"]["mark_as_read"] = False
    assert cli.main(["--no-dry-run", "--quiet", "--date", "2026-11-25"]) == 0
    assert list(cache.glob("*.json"))          # kept: the mail will be read again
    config["gmail"]["mark_as_read"] = True
    assert cli.main(["--no-dry-run", "--quiet", "--date", "2026-11-26"]) == 0
    assert not list(cache.glob("*.json"))      # processed mail is read now; cache removed
