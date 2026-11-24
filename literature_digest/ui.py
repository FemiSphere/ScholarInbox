from __future__ import annotations

from datetime import datetime
from math import exp
from pathlib import Path
from time import perf_counter
from threading import RLock
from typing import TextIO

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.live import Live
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
        return Text("") if task.total is None else super().render(task)


class ProgressReporter:
    """Rich terminal output with a stable, plain-text run log."""

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
        self._live: Live | None = None
        self._banner_view: _ShimmerBanner | None = None
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._lock = RLock()
        self._stage = ""
        self._log_handle: TextIO | None = None
        self.run_log_path = Path(run_log_path) if run_log_path else None
        if self.run_log_path:
            path = self.run_log_path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = path.open("a", encoding="utf-8")

    def banner(self, *, provider: str, mode: str, show_banner: bool = True, display_name: str = "") -> None:
        metadata = _banner_metadata(display_name)
        if self.enabled and show_banner:
            self._banner_view = _ShimmerBanner(self.console, provider, mode, animated=self._interactive,
                                               metadata=metadata)
            if self._interactive:
                self._live = Live(get_renderable=self._live_renderable, console=self.console,
                    refresh_per_second=8, transient=False, vertical_overflow="crop")
                self._live.start(refresh=True)
            else:
                self.console.print(self._banner_view)
                self.console.print()
        self._write_log(APP_NAME)
        self._write_log(APP_QUOTE)
        self._write_log(metadata)
        self._write_log(f"{provider} · {mode}")

    def step(self, message: str) -> None:
        """Switch stage without adding permanent lines in an interactive terminal."""
        with self._lock:
            self._stage = message
            if self._interactive:
                self._ensure_progress(None, message)
                assert self._progress is not None and self._task_id is not None
                self._progress.remove_task(self._task_id)
                self._task_id = self._progress.add_task(message, total=None)
            elif self.enabled:
                self.console.print(self._line(message, marker="•", style="#93c5fd"))
            self._write_log(message)

    def detail(self, message: str) -> None:
        """Persist diagnostics without disturbing the live progress display."""
        with self._lock:
            self._write_log(message)

    def item(self, current: int, total: int, message: str) -> None:
        with self._lock:
            current = min(max(0, current), max(0, total))
            if self._interactive:
                self._ensure_progress(total, message)
                assert self._progress is not None and self._task_id is not None
                if self._stage != message:
                    self._progress.reset(self._task_id, total=max(1, total), description=message)
                self._progress.update(
                    self._task_id, completed=current, total=max(1, total), description=message,
                )
            elif self.enabled and self._stage != message:
                self.console.print(self._line(message, marker="•", style="#93c5fd"))
            self._stage = message
            self._write_log(f"{message}: {current}/{total}")

    def done(self, message: str) -> None:
        self._stop_progress()
        elapsed = perf_counter() - self.started_at
        rendered = f"{message}，耗时 {elapsed:.1f}s"
        if self.enabled:
            self.console.print(self._line(rendered, marker="✓", style="bold green"))
        self._write_log(rendered)

    def output(self, message: str, *, style: str | None = None) -> None:
        self._stop_progress()
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

    def _ensure_progress(self, total: int | None, description: str) -> None:
        if self._progress is not None:
            return
        self._progress = Progress(
            SpinnerColumn(style="#a78bfa"),
            TextColumn("{task.description}", markup=False, style="#e0e7ff"),
            BarColumn(
                bar_width=None,
                style="#312e81",
                complete_style="#22d3ee",
                finished_style="green",
                pulse_style="#22d3ee",
            ),
            _CountColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
            expand=True,
        )
        if self._live is None:
            self._progress.start()
        self._task_id = self._progress.add_task(description, total=None if total is None else max(1, total))

    def _live_renderable(self):
        parts = [self._banner_view] if self._banner_view is not None else []
        progress = self._progress
        if progress is not None:
            parts.append(progress.get_renderable())
        return Group(*parts)

    def _stop_progress(self) -> None:
        if self._live is not None:
            # Freeze the header and remove the transient task before printing results.
            self._progress = None
            self._task_id = None
            self._banner_view.freeze()
            self._live.stop()
            self._live = None
        elif self._progress is not None:
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


def _banner_metadata(display_name: str) -> str:
    """Banner subtitle: the configured ui.display_name (if any) and the version."""
    name = (display_name or "").strip()
    return f"{name} · v{__version__}" if name else f"v{__version__}"


def _hex_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.lstrip("#")
    return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


class _ShimmerBanner:
    """A time-based renderable refreshed by the same Live surface as progress."""

    def __init__(self, console: Console, provider: str, mode: str, *, animated: bool, metadata: str = ""):
        self.console = console
        self.metadata = metadata or _banner_metadata("")
        self.provider = provider
        self.mode = mode
        self.animated = animated
        self.started_at = perf_counter()
        self.frozen_phase = 0.35

    def freeze(self) -> None:
        if self.animated:
            self.frozen_phase = ((perf_counter() - self.started_at) / 4.5) % 1
        self.animated = False

    def __rich__(self):
        phase = ((perf_counter() - self.started_at) / 4.5) % 1 if self.animated else self.frozen_phase
        wide = self.console.is_terminal and self.console.width >= _LOGO_MIN_CONSOLE_WIDTH and not self.console.no_color
        logo = "\n".join(_LOGO) if wide else APP_NAME
        border = _palette_color(phase)
        return Group(
            Panel(Group(
                Align.center(_shimmer_text(logo, phase)),
                Text(""),
                Align.center(Text(APP_QUOTE, style="bold #dbeafe")),
                Align.right(Text(self.metadata, style="dim")),
            ), border_style=border, padding=(1, 2), expand=True),
            Align.center(Text(f"{self.provider} · {self.mode}", style="dim")),
            Text(""),
        )


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
