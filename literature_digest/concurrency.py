"""Ordered concurrent work with cooperative cancellation and prompt queue shutdown."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextvars import copy_context
from threading import Event
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def cooperative_map(
    work: Callable[[T], R], items: Iterable[T], *, max_workers: int,
    thread_name_prefix: str, cancel_event: Event | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[R]:
    values = list(items)
    cancel = cancel_event if cancel_event is not None else Event()
    results: dict[int, R] = {}

    def checked_work(item: T) -> R:
        if cancel.is_set():
            raise KeyboardInterrupt
        return work(item)

    executor = None
    try:
        if max_workers <= 1:
            for index, item in enumerate(values):
                results[index] = checked_work(item)
                if progress:
                    progress(index + 1, len(values))
        else:
            executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=thread_name_prefix)
            pending = {executor.submit(copy_context().run, checked_work, item): index for index, item in enumerate(values)}
            while pending:
                if cancel.is_set():
                    raise KeyboardInterrupt
                done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in done:
                    results[pending.pop(future)] = future.result()
                    if progress:
                        progress(len(results), len(values))
        if cancel.is_set():
            raise KeyboardInterrupt
    except BaseException:
        cancel.set()
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        if executor is not None:
            executor.shutdown(wait=True)
    return [results[index] for index in range(len(values))]
