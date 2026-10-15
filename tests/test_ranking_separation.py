import json

import pytest

from literature_digest.llm import LLMError
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.models import InterestProfile, PaperEntry
from literature_digest.ranking import rank_papers
from literature_digest.telemetry import current_llm_operation


class SplitClient:
    def __init__(self, analysis=None, translation=None):
        self.calls = []
        self.analysis = analysis or {"papers": [{
            "index": 0, "relevance": "high", "score": 0.93,
            "reason_zh": "材料体系与目标研究直接相关。", "matched_topics": ["COF"],
        }]}
        self.translation = translation or {"papers": [{
            "index": 0, "title_zh": "框架中的热输运", "summary_zh": "来源片段涉及框架热输运。",
            # Extra unsolicited fields must not override the analysis.
            "score": 0, "relevance": "low", "reason_zh": "错误覆盖",
        }]}

    def complete_json(self, prompt):
        self.calls.append((current_llm_operation(), prompt))
        result = self.analysis if "RANK_PAPERS_JSON" in prompt else self.translation
        if isinstance(result, Exception):
            raise result
        return result


def test_separate_calls_have_disjoint_responsibilities_and_preserve_analysis():
    llm = SplitClient()
    paper = PaperEntry(title="Thermal transport in COF", abstract="Measured thermal transport.")
    ranked = rank_papers([paper], InterestProfile(), llm, separate_translation=True)
    assert [operation for operation, _ in llm.calls] == ["paper_ranking", "paper_translation"]
    analysis_prompt = llm.calls[0][1]
    analysis_schema = analysis_prompt.split("Schema:")[1].split("Rules:")[0]
    assert '"title_zh"' not in analysis_schema
    assert '"summary_zh"' not in analysis_schema
    assert "Shared keywords alone do not require medium/high" in analysis_prompt
    assert ranked[0].score == 0.93
    assert ranked[0].relevance == "high"
    assert ranked[0].reason_zh == "材料体系与目标研究直接相关。"
    assert ranked[0].title_zh == "框架中的热输运"


def test_excerpt_limit_and_source_boundaries_are_explicit():
    llm = SplitClient()
    rank_papers([PaperEntry(title="COF", abstract="x" * 2500)], InterestProfile(), llm,
                separate_translation=True, abstract_max_chars=1800)
    for _, prompt in llm.calls:
        source = json.loads(prompt.split("PAPERS_JSON:")[-1])[0]
        assert len(source["abstract"]) == 1800
        assert source["abstract_original_chars"] == 2500
        assert source["source_status"] == "email_excerpt"
        assert source["abstract_truncated"] is True


def test_title_only_remains_high_but_evidence_limit_is_visible():
    llm = SplitClient()
    ranked = rank_papers([PaperEntry(title="COF")], InterestProfile(), llm,
                         separate_translation=True)
    assert ranked[0].relevance == "high"
    assert "仅有标题及元数据" in ranked[0].reason_zh
    source = json.loads(llm.calls[0][1].split("PAPERS_JSON:")[-1])[0]
    assert source["source_status"] == "title_only"


def test_translation_failure_keeps_successful_scientific_analysis():
    llm = SplitClient(translation=LLMError("translation unavailable"))
    llm.analysis["papers"][0].update(title_zh="不应使用思考输出的翻译", summary_zh="不应使用")
    events = []
    ranked = rank_papers([PaperEntry(title="Thermal transport in COF")], InterestProfile(), llm,
                         separate_translation=True, event_callback=events.append)
    assert ranked[0].score == 0.93
    assert ranked[0].relevance == "high"
    assert ranked[0].matched_topics == ["COF"]
    assert ranked[0].title_zh != "不应使用思考输出的翻译"
    assert ranked[0].summary_zh != "不应使用"
    assert any("回退本地规则" in message for message in events)


def test_analysis_failure_still_performs_nonreasoning_translation():
    llm = SplitClient(analysis=LLMError("analysis unavailable"))
    events = []
    ranked = rank_papers([PaperEntry(title="Thermal transport in COF")], InterestProfile(), llm,
                         separate_translation=True, event_callback=events.append)
    assert [operation for operation, _ in llm.calls] == ["paper_ranking", "paper_translation"]
    assert ranked[0].title_zh == "框架中的热输运"
    assert "本地规则" in ranked[0].reason_zh
    assert events


@pytest.mark.parametrize("items", [
    [],
    [{"index": 1}],
    [{"index": 0}, {"index": 0}],
    [{"index": "0"}],
    [{"index": 0, "relevance": "high", "score": float("nan"), "reason_zh": "理由", "matched_topics": []}],
])
def test_malformed_analysis_emits_degraded_callback_and_falls_back(items):
    events = []
    llm = SplitClient(analysis={"papers": items})
    ranked = rank_papers([PaperEntry(title="Thermal transport in COF")], InterestProfile(), llm,
                         separate_translation=True, event_callback=events.append)
    assert events
    assert "本地规则" in ranked[0].reason_zh
    assert ranked[0].title_zh == "框架中的热输运"


def test_missing_translation_index_does_not_change_ranking():
    llm = SplitClient(translation={"papers": []})
    events = []
    ranked = rank_papers([PaperEntry(title="COF")], InterestProfile(), llm,
                         separate_translation=True, event_callback=events.append)
    assert ranked[0].score == 0.93
    assert events


def test_offline_stub_supports_separate_mode():
    ranked = rank_papers([PaperEntry(title="COF thermal conductivity")], InterestProfile(),
                         OfflineStubClient(), separate_translation=True)
    assert ranked[0].relevance == "high"
    assert ranked[0].title_zh.startswith("论文：")
    assert "stub" in ranked[0].summary_zh
