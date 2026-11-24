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
