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
                "model": "deepseek-flash",
            },
        }
    }

    assert _ui_provider_label(config, sample_mode=False) == "DeepSeek API · deepseek-flash"


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


def test_request_details_are_log_only_and_safe_for_concurrent_writers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    output = StringIO()
    reporter = ProgressReporter(console=Console(file=output), run_log_path=tmp_path / "run.log")
    reporter.step("解析论文条目")
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda i: reporter.detail(f"API request {i}"), range(12)))
    reporter.close()

    assert "API request" not in output.getvalue()
    assert (tmp_path / "run.log").read_text().count("API request") == 12


def test_interactive_progress_exists_before_first_completion_and_changes_stage():
    output = StringIO()
    reporter = ProgressReporter(console=Console(file=output, force_terminal=True, width=90, no_color=False, _environ={"TERM": "xterm-256color"}))
    reporter.step("读取 Gmail 未读邮件")
    assert reporter._progress.tasks[0].total is None
    reporter.item(0, 20, "解析论文条目")
    task = reporter._progress.tasks[0]
    assert task.completed == 0 and task.total == 20
    reporter.item(10, 20, "解析论文条目")
    assert reporter._progress.tasks[0].completed == 10
    reporter.step("保存文献日报")
    assert reporter._progress.tasks[0].total is None
    reporter.close()


def test_plain_and_quiet_output_do_not_emit_animation_codes(tmp_path):
    for enabled in (False, True):
        output = StringIO()
        reporter = ProgressReporter(
            enabled=enabled, color_enabled=False,
            console=Console(file=output, force_terminal=True, no_color=True),
            run_log_path=tmp_path / f"{enabled}.log",
        )
        reporter.step("准备邮件")
        for current in range(4):
            reporter.item(current, 3, "解析论文条目")
        reporter.close()
        assert "\x1b[" not in output.getvalue()
        assert output.getvalue().count("解析论文条目") == (1 if enabled else 0)
