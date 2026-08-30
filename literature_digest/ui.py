from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import TextIO

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from . import __author__, __version__


APP_NAME = "ScholarPulse"
APP_QUOTE = "循此苦旅，以抵星辰。"
APP_AUTHOR = __author__
_LOGO = (
    "  ____       _           _            ____        _          ",
    " / ___|  ___| |__   ___ | | __ _ _ __|  _ \\ _   _| |___  ___ ",
    " \\___ \\ / __| '_ \\ / _ \\| |/ _` | '__| |_) | | | | / __|/ _ \\",
    "  ___) | (__| | | | (_) | | (_| | |  |  __/| |_| | \\__ \\  __/",
    " |____/ \\___|_| |_|\\___/|_|\\__,_|_|  |_|    \\__,_|_|___/\\___|",
)


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
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._log_handle: TextIO | None = None
        if run_log_path:
            path = Path(run_log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = path.open("a", encoding="utf-8")

    def banner(self, *, provider: str, mode: str, show_banner: bool = True) -> None:
        metadata = f"{APP_AUTHOR} · v{__version__}"
        if self.enabled and show_banner:
            if self._interactive and self.console.width >= 82:
                logo = Align.center(_gradient_text("\n".join(_LOGO), "#8b5cf6", "#22d3ee"))
            else:
                logo = Align.center(Text(APP_NAME, style="bold bright_cyan"))
            content = Group(
                logo,
                Text(""),
                Align.center(Text(APP_QUOTE, style="bold #dbeafe")),
                Align.right(Text(metadata, style="dim")),
            )
            self.console.print(
                Panel(
                    content,
                    border_style="#6366f1",
                    padding=(1, 2),
                    expand=True,
                )
            )
            self.console.print(Align.center(Text(f"{provider} · {mode}", style="dim")))
            self.console.print()
        self._write_log(APP_NAME)
        self._write_log(APP_QUOTE)
        self._write_log(metadata)
        self._write_log(f"{provider} · {mode}")

    def step(self, message: str) -> None:
        self._stop_progress()
        if self.enabled:
            self.console.print(self._line(message, marker="•", style="#93c5fd"))
        self._write_log(message)

    def item(self, current: int, total: int, message: str) -> None:
        if self._interactive:
            self._ensure_progress(total)
            assert self._progress is not None and self._task_id is not None
            self._progress.update(
                self._task_id,
                completed=min(max(0, current), max(0, total)),
                total=max(1, total),
                description=message,
            )
        elif self.enabled and current == total:
            self.console.print(self._line(f"{message}：{current}/{total}", marker="•", style="dim"))
        if current == total:
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

    def error(self, message: str) -> None:
        self._stop_progress()
        self.console.print(message, style="bold red", markup=False)
        self._write_log(message)

    def close(self) -> None:
        self._stop_progress()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def _ensure_progress(self, total: int) -> None:
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
            ),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
            expand=True,
        )
        self._progress.start()
        self._task_id = self._progress.add_task("处理中", total=max(1, total))

    def _stop_progress(self) -> None:
        if self._progress is None:
            return
        self._progress.stop()
        self._progress = None
        self._task_id = None

    def _line(self, message: str, *, marker: str, style: str) -> Text:
        line = Text()
        if self.show_timestamps:
            line.append(f"[{datetime.now().strftime('%H:%M:%S')}] ", style="dim")
        line.append(f"{marker} ", style=style)
        line.append(message)
        return line

    def _write_log(self, message: str) -> None:
        if self._log_handle is None:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_handle.write(f"[{timestamp}] {message}\n")
        self._log_handle.flush()


def _gradient_text(value: str, start: str, end: str) -> Text:
    start_rgb = _hex_rgb(start)
    end_rgb = _hex_rgb(end)
    visible = max(1, sum(1 for char in value if not char.isspace()))
    index = 0
    result = Text()
    for char in value:
        if char.isspace():
            result.append(char)
            continue
        ratio = index / max(1, visible - 1)
        red = round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
        green = round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
        blue = round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
        result.append(char, style=f"bold rgb({red},{green},{blue})")
        index += 1
    return result


def _hex_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.lstrip("#")
    return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
