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

    reporter.banner(provider="Codex CLI · gpt-5.4-mini", mode="正式运行", display_name="测试用户")
    reporter.close()

    rendered = Text.from_ansi(output.getvalue()).plain
    log_text = log_path.read_text(encoding="utf-8")
    assert "█████" in rendered
    assert APP_QUOTE in rendered
    assert f"测试用户 · v{__version__}" in rendered
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
    rendered = Text.from_ansi(output.getvalue()).plain
    # Each finished stage leaves one permanent check line with its count.
    assert rendered.count("✓") == 3
    assert "读取 Gmail 未读邮件" in rendered and "解析论文条目" in rendered and "20" in rendered


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


def test_file_output_emits_osc8_with_encoded_uri_and_plain_log(tmp_path):
    target = tmp_path / "中文 folder" / "日报 阅读版.html"
    log = tmp_path / "run.log"
    for no_color in (False, True):
        output = StringIO()
        console = Console(file=output, force_terminal=True, color_system="truecolor",
            no_color=no_color, width=20, _environ={"TERM": "xterm-256color"})
        reporter = ProgressReporter(console=console, run_log_path=log)
        reporter.output_file(target)
        reporter.close()
        raw = output.getvalue()
        assert "\x1b]8;" in raw
        assert target.resolve().as_uri() in raw
        assert "HTML 阅读版" in Text.from_ansi(raw).plain
        # Terminal auto-wraps long labels; Rich must not insert broken path lines.
        assert raw.count("\n") == 1
    assert str(target.resolve()) in log.read_text()
    assert "\x1b" not in log.read_text()


def test_redirected_file_output_is_complete_plain_path(tmp_path):
    target = tmp_path / "nested" / "a-long-file-name.html"
    output = StringIO()
    reporter = ProgressReporter(console=Console(file=output, force_terminal=False, width=20))
    reporter.output_file(target)
    reporter.close()
    assert output.getvalue() == f"  {target.resolve()}\n"
    assert "\x1b" not in output.getvalue()


def test_wordmark_colors_do_not_change_geometry():
    from literature_digest.ui import _shimmer_text, _LOGO
    logo = "\n".join(_LOGO)
    assert _shimmer_text(logo, 0.1).plain == _shimmer_text(logo, 0.6).plain == logo


def test_banner_is_printed_once_and_only_progress_is_live():
    """Regression for terminal flicker: the header must not live in a refreshing region."""
    output = StringIO()
    reporter = ProgressReporter(console=Console(file=output, force_terminal=True,
        color_system="truecolor", width=100, _environ={"TERM": "xterm-256color"}))
    reporter.banner(provider="DeepSeek API", mode="正式运行")
    assert reporter._progress is None
    after_banner = output.getvalue()
    reporter.item(0, 10, "论文相关性评级")
    assert reporter._progress is not None and reporter._progress.live.is_started
    reporter.item(5, 10, "论文相关性评级")
    reporter.done("完成")
    assert reporter._progress is None
    reporter.close()
    rendered = Text.from_ansi(output.getvalue()).plain
    assert rendered.count(APP_QUOTE) == 1
    assert output.getvalue().startswith(after_banner)
    assert "完成" in rendered


def test_summary_renders_counts_and_facts(tmp_path):
    for terminal in (True, False):
        output = StringIO()
        reporter = ProgressReporter(console=Console(file=output, force_terminal=terminal, width=100,
                                                    _environ={"TERM": "xterm-256color"}),
                                    run_log_path=tmp_path / f"{terminal}.log")
        reporter.summary([("高相关", 4), ("中相关", 14), ("不相关", 0)], ["33 封邮件", "83 篇新论文"])
        reporter.close()
        rendered = Text.from_ansi(output.getvalue()).plain
        assert "4 高相关" in rendered or "高相关 4" in rendered
        assert "83 篇新论文" in rendered
        assert "高相关 4" in (tmp_path / f"{terminal}.log").read_text(encoding="utf-8")


def test_noninteractive_banner_is_static_and_compact():
    output = StringIO()
    reporter = ProgressReporter(console=Console(file=output, force_terminal=False, width=100))
    reporter.banner(provider="DeepSeek API", mode="正式运行")
    reporter.close()
    assert "ScholarInbox" in output.getvalue()
    assert "█████" not in output.getvalue()
    assert "\x1b" not in output.getvalue()


def test_disabled_banner_keeps_existing_progress_and_osc8_behavior():
    output = StringIO()
    reporter = ProgressReporter(console=Console(file=output, force_terminal=True,
        color_system="truecolor", _environ={"TERM": "xterm-256color"}))
    reporter.banner(provider="DeepSeek API", mode="正式运行", show_banner=False)
    reporter.item(0, 2, "处理")
    reporter.output_file('/tmp/digest.html')
    reporter.close()
    assert "\x1b]8;" in output.getvalue()


def test_banner_without_display_name_shows_only_version():
    from literature_digest.ui import _banner_metadata
    assert _banner_metadata("") == f"v{__version__}"
    assert _banner_metadata("  Alice ") == f"Alice · v{__version__}"
