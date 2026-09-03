from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.text import Text

from literature_digest import __version__
from literature_digest.cli import _ui_provider_label
from literature_digest.ui import APP_AUTHOR, APP_NAME, APP_QUOTE, ProgressReporter


def test_rich_banner_uses_large_logo_quote_and_dim_metadata(tmp_path):
    output = StringIO()
    console = Console(
        file=output,
        force_terminal=True,
        color_system="truecolor",
        width=100,
        _environ={"TERM": "xterm-256color"},
    )
    log_path = tmp_path / "logs" / "digest.log"
    reporter = ProgressReporter(console=console, run_log_path=log_path)

    reporter.banner(provider="Codex CLI · gpt-5.4-mini", mode="正式运行")
    reporter.close()

    rendered = Text.from_ansi(output.getvalue()).plain
    log_text = log_path.read_text(encoding="utf-8")
    assert "█████" in rendered
    assert APP_QUOTE in rendered
    assert f"{APP_AUTHOR} · v{__version__}" in rendered
    assert "Codex CLI · gpt-5.4-mini · 正式运行" in rendered
    assert "\x1b[" not in log_text
    assert APP_NAME in log_text
    assert APP_QUOTE in log_text


def test_narrow_terminal_falls_back_to_compact_name():
    output = StringIO()
    console = Console(
        file=output,
        force_terminal=True,
        width=60,
        _environ={"TERM": "xterm-256color"},
    )
    reporter = ProgressReporter(console=console)

    reporter.banner(provider="本地离线模型", mode="样例 dry-run")
    reporter.close()

    rendered = Text.from_ansi(output.getvalue()).plain
    assert APP_NAME in rendered
    assert APP_QUOTE in rendered
    assert "█████" not in rendered


def test_provider_label_uses_deepseek_runtime_model():
    config = {
        "llm": {
            "provider": "openai_compatible",
            "model": "gpt-5.4-mini",
            "openai_compatible": {
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
            },
        }
    }

    assert _ui_provider_label(config, sample_mode=False) == "DeepSeek API · deepseek-v4-flash"


def test_provider_label_uses_custom_api_for_other_compatible_endpoints():
    config = {
        "llm": {
            "provider": "openai_compatible",
            "openai_compatible": {
                "base_url": "https://llm.example.com/v1",
                "model": "custom-model",
            },
        }
    }

    assert _ui_provider_label(config, sample_mode=False) == "自定义 API · custom-model"
