from __future__ import annotations

import json
import re
from threading import Event, Lock

from literature_digest.interests import load_or_analyze_research_interests
from literature_digest.models import EmailMessage, InterestProfile, PaperEntry
from literature_digest.parsers import parse_emails
from literature_digest.ranking import rank_papers
from literature_digest.telemetry import RunMetrics, llm_operation


class ConcurrentRankingClient:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self._lock = Lock()
        self._overlap = Event()

    def complete_json(self, prompt: str):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active >= 2:
                self._overlap.set()
        self._overlap.wait(timeout=1)
        papers = json.loads(prompt.rsplit("PAPERS_JSON:\n", 1)[1])
        with self._lock:
            self.active -= 1
        return {
            "papers": [
                {
                    "index": item["index"],
                    "relevance": "medium",
                    "score": 0.5,
                    "title_zh": f"中文：{item['title']}",
                    "summary_zh": "摘要",
                    "reason_zh": "理由",
                    "matched_topics": [],
                }
                for item in papers
            ]
        }


def test_ranking_batches_run_concurrently_and_keep_stable_order():
    entries = [PaperEntry(title=f"Paper title number {index}") for index in range(6)]
    client = ConcurrentRankingClient()

    ranked = rank_papers(
        entries,
        InterestProfile(summary_zh="test"),
        client,
        batch_size=2,
        max_workers=3,
    )

    assert client.max_active >= 2
    assert [paper.entry.title for paper in ranked] == [entry.title for entry in entries]


class ConcurrentExtractionClient:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self._lock = Lock()
        self._overlap = Event()

    def complete_json(self, prompt: str):
        subject = re.search(r"EMAIL_SUBJECT:\n(.+)", prompt).group(1)
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active >= 2:
                self._overlap.set()
        self._overlap.wait(timeout=1)
        with self._lock:
            self.active -= 1
        return {
            "papers": [
                {
                    "title": f"Machine learning thermal transport study from {subject}",
                    "url": f"https://example.org/{subject}",
                    "doi": "",
                    "venue": "Test Journal",
                    "authors": "",
                    "snippet": "thermal transport",
                    "image_index": None,
                }
            ]
        }


def test_non_scholar_extraction_runs_concurrently_and_keeps_email_order():
    emails = [
        EmailMessage(
            id=str(index),
            thread_id="thread",
            subject=f"issue-{index}",
            sender="journal@example.org",
            date=None,
            html=(
                f'<a href="https://example.org/{index}">'
                f"Machine learning thermal transport paper number {index}</a>"
            ),
        )
        for index in range(4)
    ]
    client = ConcurrentExtractionClient()

    entries = parse_emails(
        emails,
        llm=client,
        llm_structure_non_scholar=True,
        max_workers=3,
    )

    assert client.max_active >= 2
    assert [entry.source_subject for entry in entries] == [email.subject for email in emails]


class InterestClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, prompt: str):
        self.calls += 1
        return {
            "current_projects": ["COF thermal transport"],
            "material_systems": ["COF"],
            "methods": [],
            "properties": ["thermal conductivity"],
            "high_priority_topics": ["COF"],
            "medium_priority_topics": [],
            "deprioritized_topics": [],
            "summary_zh": "关注 COF 热输运。",
        }


def test_interest_profile_cache_depends_on_text_and_model(tmp_path):
    cache_path = tmp_path / "cache" / "interests.json"
    client = InterestClient()

    first, first_hit = load_or_analyze_research_interests(
        "COF thermal transport",
        client,
        cache_path=cache_path,
        model_fingerprint="model-a",
    )
    second, second_hit = load_or_analyze_research_interests(
        "COF thermal transport",
        client,
        cache_path=cache_path,
        model_fingerprint="model-a",
    )
    _, changed_model_hit = load_or_analyze_research_interests(
        "COF thermal transport",
        client,
        cache_path=cache_path,
        model_fingerprint="model-b",
    )

    assert first.summary_zh == second.summary_zh
    assert first_hit is False
    assert second_hit is True
    assert changed_model_hit is False
    assert client.calls == 2


def test_metrics_aggregate_usage_without_storing_prompt_content():
    metrics = RunMetrics()
    with llm_operation("paper_ranking", 20):
        metrics.record_llm_request(
            elapsed_seconds=1.25,
            prompt_chars=1234,
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "prompt_cache_hit_tokens": 40,
            },
        )

    request = metrics.llm_requests[0]
    summary = "\n".join(metrics.summary_lines())
    assert request.operation == "paper_ranking"
    assert request.item_count == 20
    assert request.total_tokens == 150
    assert request.cache_hit_tokens == 40
    assert "prompt" not in request.__dataclass_fields__
    assert "tokens=150" in summary
