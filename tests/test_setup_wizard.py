import os

from literature_digest import setup_wizard
from literature_digest.cli import main
from literature_digest.config import load_config


def _answers(*values):
    iterator = iter(values)
    return lambda prompt: next(iterator)


def test_init_writes_minimal_preset_config_env_and_interests(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    # provider 1 (DeepSeek), 30 emails, mark read yes, display name
    code = setup_wizard.run_init([], ask=_answers("1", "30", "y", "Alice"),
                                 ask_secret=lambda prompt: "sk-test-secret-value", base_dir=tmp_path)
    assert code == 0
    config = load_config(tmp_path / "config.local.yaml")
    assert config["llm"]["provider"] == "openai_compatible"
    assert config["gmail"]["max_emails_per_run"] == 30 and config["gmail"]["mark_as_read"] is True
    assert config["ui"]["display_name"] == "Alice"
    assert "DEEPSEEK_API_KEY=sk-test-secret-value" in (tmp_path / ".env").read_text()
    assert "大方向" in (tmp_path / "research_interests.md").read_text(encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_init_keeps_existing_config_and_interests(tmp_path, monkeypatch):
    (tmp_path / "config.local.yaml").write_text("llm:\n  preset: codex_cli\n", encoding="utf-8")
    (tmp_path / "research_interests.md").write_text("mine", encoding="utf-8")
    assert setup_wizard.run_init([], ask=_answers(""), ask_secret=lambda p: "", base_dir=tmp_path) == 0
    assert (tmp_path / "config.local.yaml").read_text() == "llm:\n  preset: codex_cli\n"
    assert (tmp_path / "research_interests.md").read_text() == "mine"


def test_doctor_reports_missing_pieces_without_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / "config.local.yaml").write_text("llm:\n  preset: deepseek\n", encoding="utf-8")
    checks = setup_wizard.collect_checks(base_dir=tmp_path)
    failed = " ".join(check.title for check in checks if check.status == "fail")
    assert "DEEPSEEK_API_KEY" in failed and "credentials.json" in failed and "研究兴趣" in failed
    assert main(["doctor"]) == 1


def test_doctor_passes_when_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.local.yaml").write_text("llm:\n  preset: deepseek\ngmail:\n  mark_as_read: true\n", encoding="utf-8")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-x\n")
    (tmp_path / "credentials.json").write_text("{}")
    (tmp_path / "token.json").write_text("{}")
    (tmp_path / "research_interests.md").write_text("## 大方向\n- 计算材料\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert main(["doctor"]) == 0
    os.environ.pop("DEEPSEEK_API_KEY", None)
