#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from literature_digest.models import InterestProfile, PaperEntry
from literature_digest.ranking import rank_papers


class SimulatedLLMClient:
    """A deterministic latency model for measuring orchestration overhead only."""

    def __init__(self, *, base_delay: float, per_item_delay: float) -> None:
        self.base_delay = base_delay
        self.per_item_delay = per_item_delay
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def complete_json(self, prompt: str):
        papers = json.loads(prompt.rsplit("PAPERS_JSON:\n", 1)[1])
        with self._lock:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(self.base_delay + self.per_item_delay * len(papers))
        with self._lock:
            self.active -= 1
        return {
            "papers": [
                {
                    "index": paper["index"],
                    "relevance": "medium",
                    "score": 0.5,
                    "title_zh": f"中文：{paper['title']}",
                    "summary_zh": "离线基准摘要",
                    "reason_zh": "离线基准理由",
                    "matched_topics": [],
                }
                for paper in papers
            ]
        }


def run_case(
    entries: list[PaperEntry],
    *,
    batch_size: int,
    max_workers: int,
    repeats: int,
    base_delay: float,
    per_item_delay: float,
) -> tuple[float, int, int]:
    elapsed_values: list[float] = []
    calls = max_active = 0
    for _ in range(repeats):
        client = SimulatedLLMClient(base_delay=base_delay, per_item_delay=per_item_delay)
        started_at = time.perf_counter()
        ranked = rank_papers(
            entries,
            InterestProfile(summary_zh="offline benchmark"),
            client,
            batch_size=batch_size,
            max_workers=max_workers,
        )
        elapsed_values.append(time.perf_counter() - started_at)
        calls = client.calls
        max_active = client.max_active
        if len(ranked) != len(entries):
            raise RuntimeError("benchmark lost ranked entries")
    return statistics.median(elapsed_values), calls, max_active


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline concurrency/batch-size benchmark.")
    parser.add_argument("--papers", type=int, default=240)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--base-delay", type=float, default=0.02)
    parser.add_argument("--per-item-delay", type=float, default=0.001)
    args = parser.parse_args()
    entries = [PaperEntry(title=f"Synthetic paper {index}") for index in range(args.papers)]

    print("workers,batch_size,requests,max_active,median_seconds")
    cases = [(workers, 20) for workers in (1, 2, 3, 4)]
    cases.extend((3, batch_size) for batch_size in (10, 30, 40))
    for workers, batch_size in cases:
        elapsed, calls, max_active = run_case(
            entries,
            batch_size=batch_size,
            max_workers=workers,
            repeats=max(1, args.repeats),
            base_delay=max(0.0, args.base_delay),
            per_item_delay=max(0.0, args.per_item_delay),
        )
        print(f"{workers},{batch_size},{calls},{max_active},{elapsed:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
