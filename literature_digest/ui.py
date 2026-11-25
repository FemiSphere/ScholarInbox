from __future__ import annotations

from datetime import datetime
from math import exp
from pathlib import Path
from time import perf_counter
from threading import RLock
from typing import TextIO

from rich.align import Align
from rich.console import Console, Group
from rich.rule import Rule
from rich.table import Table
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    Task,
    TimeElapsedColumn,
)
from rich.text import Text

from . import __author__, __version__


APP_NAME = "ScholarInbox"
APP_QUOTE = "循此苦旅，以抵星辰。"
APP_AUTHOR = __author__
_LOGO = (
    "█████ █████ █   █ █████ █      ███  ████  ███ █   █ ████  █████ █   █",
    "█     █     █   █ █   █ █     █   █ █   █  █  ██  █ █   █ █   █  █ █ ",
    "█████ █     █████ █   █ █     █████ ████   █  █ █ █ ████  █   █   █  ",
    "    █ █     █   █ █   █ █     █   █ █  █   █  █  ██ █   █ █   █  █ █ ",
    "█████ █████ █   █ █████ █████ █   █ █   █ ███ █   █ ████  █████ █   █",
)
_LOGO_MIN_CONSOLE_WIDTH = max(len(line) for line in _LOGO) + 6


class _CountColumn(MofNCompleteColumn):
    def render(self, task: Task) -> Text:
        if task.total is None:
            return Text("")
        return Text(f"{int(task.completed)}/{int(task.total)}", style="#7d8799")


# Quiet, legible palette: one accent, one success colour, neutral greys.
_ACCENT = "#8ab4f8"
_SUCCESS = "#7fd8b0"
_MUTED = "#7d8799"
_TRACK = "#2b3245"
# Content column width: wide enough for the wordmark, narrow enough to read as one block.
_COLUMN = 72


class ProgressReporter:
    """Rich terminal output with a stable, plain-text run log.

    Interactive layout: a static header printed once, one permanent "✓ stage" line per
    finished stage, and a single-line live progress bar for the current stage. Only that
    one line is redrawn, which keeps terminals (including VS Code) from flickering.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        show_timestamps: bool = True,
        color_enabled: bool = True,
        run_log_path: str | Path | None = None,
        console: Console | None = None,
    ) -> None:
        self.enabled = enabled
        self.show_timestamps = show_timestamps
        self.started_at = perf_counter()
        self.console = (
            console
            if console is not None
            else Console(
                highlight=False,
                no_color=not color_enabled,
            )
        )
        self._interactive = enabled and self.console.is_terminal and not bool(self.console.no_color)
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._lock = RLock()
        self._stage = ""
        self._stage_started = perf_counter()
        self._stage_counts: tuple[int, int] | None = None
        self._log_handle: TextIO | None = None
        self.run_log_path = Path(run_log_path) if run_log_path else None
        if self.run_log_path:
            path = self.run_log_path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = path.open("a", encoding="utf-8")

    # ------------------------------------------------------------------ header
    def banner(self, *, provider: str, mode: str, show_banner: bool = True, display_name: str = "") -> None:
        metadata = _banner_metadata(display_name)
        if self.enabled and show_banner:
            self.console.print(_header(self.console, provider, mode, metadata, rich=self._interactive),
                               width=min(_COLUMN, self.console.width))
        self._write_log(APP_NAME)
        self._write_log(APP_QUOTE)
        self._write_log(metadata)
        self._write_log(f"{provider} · {mode}")

    # ------------------------------------------------------------------ stages
    def step(self, message: str) -> None:
        """Start a stage without a known size."""
        with self._lock:
            if self._interactive:
                if message != self._stage:
                    self._finish_stage()
                    self._begin_stage(message)
                self._ensure_progress(None, message)
                assert self._progress is not None and self._task_id is not None
                # reset(total=None) keeps the old total in Rich, so replace the task instead.
                self._progress.remove_task(self._task_id)
                self._task_id = self._progress.add_task(message, total=None)
            elif self.enabled:
                self.console.print(self._line(message, marker="•", style=_ACCENT))
            self._stage = message
            self._write_log(message)

    def detail(self, message: str) -> None:
        """Persist diagnostics without disturbing the live progress display."""
        with self._lock:
            self._write_log(message)

    def item(self, current: int, total: int, message: str) -> None:
        with self._lock:
            current = min(max(0, current), max(0, total))
            if self._interactive:
                if self._stage != message:
                    self._finish_stage()
                    self._begin_stage(message)
                self._ensure_progress(total, message)
                assert self._progress is not None and self._task_id is not None
                if self._progress.tasks[0].description != message:
                    self._progress.remove_task(self._task_id)
                    self._task_id = self._progress.add_task(message, total=max(1, total))
                self._progress.update(self._task_id, completed=current, total=max(1, total), description=message)
                self._stage_counts = (current, total)
            elif self.enabled and self._stage != message:
                self.console.print(self._line(message, marker="•", style=_ACCENT))
            self._stage = message
            self._write_log(f"{message}: {current}/{total}")

    def done(self, message: str) -> None:
        self._stop_progress()
        elapsed = perf_counter() - self.started_at
        rendered = f"{message}，耗时 {_duration(elapsed)}"
        if self.enabled:
            if self._interactive:
                self.console.print()
                self.console.print(Text.assemble(("  ✓ ", f"bold {_SUCCESS}"), (message, "bold"),
                                                 (f"  ·  {_duration(elapsed)}", _MUTED)))
            else:
                self.console.print(self._line(rendered, marker="✓", style="bold green"))
        self._write_log(rendered)

    def summary(self, counts: list[tuple[str, int]], facts: list[str]) -> None:
        """Result block: relevance counts as a row, then a one-line fact strip."""
        plain_counts = " · ".join(f"{label} {value}" for label, value in counts)
        plain = " · ".join(facts + [plain_counts])
        self._stop_progress()
        if self._interactive:
            row = Text("  ")
            for index, (label, value) in enumerate(counts):
                if index:
                    row.append("   ")
                row.append(str(value), style=f"bold {_ACCENT}" if value else _MUTED)
                row.append(f" {label}", style="" if value else _MUTED)
            self.console.print(row)
            self.console.print(Text("  " + "  ·  ".join(facts), style=_MUTED))
        elif self.enabled:
            self.console.print(plain, markup=False)
        self._write_log(plain)

    def output(self, message: str, *, style: str | None = None) -> None:
        self._stop_progress()
        if self._interactive:
            self.console.print(Text("  " + message, style=style or ""))
        else:
            self.console.print(message, style=style, markup=False)
        self._write_log(message)

    def output_file(self, path: str | Path) -> None:
        """Emit an explicit OSC 8 file link in terminals and a plain path in logs."""
        target = Path(path).resolve()
        self._stop_progress()
        if self.console.is_terminal:
            label = "HTML 阅读版" if target.suffix.lower() == ".html" else "Markdown 文件"
            text = Text("  ")
            text.append(f"{label} ↗ {target.name}", style=f"link {target.as_uri()}")
            self.console.print(text, soft_wrap=True)
        else:
            self.console.print(f"  {target}", markup=False, soft_wrap=True)
        self._write_log(f"  {target}")

    def error(self, message: str) -> None:
        self._stop_progress()
        self.console.print(message, style="bold red", markup=False)
        self._write_log(message)

    def close(self) -> None:
        with self._lock:
            self._stop_progress()
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None

    # ------------------------------------------------------------------ internals
    def _begin_stage(self, message: str) -> None:
        self._stage = message
        self._stage_started = perf_counter()
        self._stage_counts = None

    def _finish_stage(self) -> None:
        """Print a permanent line for the stage that just ended (interactive only)."""
        if not self._interactive or not self._stage:
            return
        elapsed = perf_counter() - self._stage_started
        counts = ""
        if self._stage_counts and self._stage_counts[1] > 0:
            counts = f"{self._stage_counts[1]} 项"
        line = Table.grid(expand=True, padding=(0, 1))
        line.add_column(width=3)
        line.add_column(ratio=1)
        line.add_column(justify="right", width=8)
        line.add_column(justify="right", width=8)
        line.add_row(Text(" ✓", style=_SUCCESS), Text(self._stage), Text(counts, style=_MUTED),
                     Text(_duration(elapsed), style=_MUTED))
        target = self._progress.console if self._progress is not None else self.console
        target.print(line, width=min(_COLUMN, target.width))
        self._stage = ""

    def _ensure_progress(self, total: int | None, description: str) -> None:
        if self._progress is not None:
            return
        self._progress = Progress(
            TextColumn("  "),
            SpinnerColumn("dots", style=_ACCENT),
            TextColumn("{task.description}", markup=False),
            BarColumn(bar_width=28, style=_TRACK, complete_style=_ACCENT,
                      finished_style=_SUCCESS, pulse_style=_ACCENT),
            _CountColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
            refresh_per_second=8,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(description, total=None if total is None else max(1, total))

    def _stop_progress(self) -> None:
        with self._lock:
            self._finish_stage()
            if self._progress is not None:
                self._progress.stop()
                self._progress = None
                self._task_id = None

    def _line(self, message: str, *, marker: str, style: str) -> Text:
        line = Text()
        # Rich still emits bold/dim codes under no_color; plain output must stay escape-free.
        plain = bool(self.console.no_color)
        if self.show_timestamps:
            line.append(f"[{datetime.now().strftime('%H:%M:%S')}] ", style="" if plain else "dim")
        line.append(f"{marker} ", style="" if plain else style)
        line.append(message)
        return line

    def _write_log(self, message: str) -> None:
        with self._lock:
            if self._log_handle is None:
                return
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._log_handle.write(f"[{timestamp}] {message}\n")
            self._log_handle.flush()


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}m{rest:02d}s"


def _header(console: Console, provider: str, mode: str, metadata: str, *, rich: bool):
    """Static header. Wide colour terminals get the gradient wordmark; others a compact title."""
    wide = rich and console.width >= _LOGO_MIN_CONSOLE_WIDTH
    quote = Table.grid(expand=True)
    quote.add_column(ratio=1)
    quote.add_column(justify="right")
    quote.add_row(Text(APP_QUOTE, style="#c9d4ea" if rich else ""), Text(metadata, style=_MUTED if rich else ""))
    parts = [Text("")]
    if wide:
        parts += [Align.center(_shimmer_text("\n".join(_LOGO), 0.35)), Text("")]
    else:
        parts.append(Text(APP_NAME, style=f"bold {_ACCENT}" if rich else ""))
    parts += [quote, Rule(style=_TRACK if rich else ""),
              Text(f"{provider} · {mode}", style=_MUTED if rich else ""), Text("")]
    return Group(*parts)


def _banner_metadata(display_name: str) -> str:
    """Banner subtitle: the configured ui.display_name (if any) and the version."""
    name = (display_name or "").strip()
    return f"{name} · v{__version__}" if name else f"v{__version__}"


def _hex_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.lstrip("#")
    return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _palette_color(position: float) -> str:
    palette = ((139, 92, 246), (94, 165, 250), (34, 211, 238), (167, 139, 250))
    value = (position % 1) * len(palette)
    index = int(value)
    mix = value - index
    left, right = palette[index], palette[(index + 1) % len(palette)]
    rgb = [round(a + (b - a) * mix) for a, b in zip(left, right)]
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def _shimmer_text(value: str, phase: float) -> Text:
    """Horizontal color flow with a soft highlight; content and geometry stay fixed."""
    width = max(1, max(map(len, value.splitlines()), default=1) - 1)
    result = Text()
    x = 0
    for char in value:
        if char == "\n":
            result.append(char)
            x = 0
            continue
        if char.isspace():
            result.append(char)
        else:
            position = x / width
            color = _hex_rgb(_palette_color(position * 0.65 - phase))
            # Highlight enters/leaves beyond the edges instead of jumping across the logo.
            shine = 0.65 * exp(-((position - (phase * 1.5 - 0.25)) / 0.13) ** 2)
            rgb = [round(channel + (245 - channel) * shine) for channel in color]
            result.append(char, style="bold rgb(" + ",".join(map(str, rgb)) + ")")
        x += 1
    return result
