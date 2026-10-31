import json

import pytest

from literature_digest.llm import LLMError, current_llm_deadline, llm_time_budget
from literature_digest.models import InterestProfile, PaperEntry, RankedPaper
from literature_digest.ranking import (
    TranslationRecoveryError, _request_translations, rank_papers, translate_ranked_papers,
)
from literature_digest.telemetry import RunMetrics, current_llm_operation


def row(index, **fields):
    return dict(index=index, title_zh=f"中文标题{index}", summary_zh="来源信息有限。", **fields)


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.metrics = RunMetrics()

    def complete_json(self, prompt):
        self.calls.append((prompt, current_llm_operation(), current_llm_deadline()))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def request(client, count=2, offset=20):
    entries = [PaperEntry(title=f"Source paper {i}") for i in range(count)]
    sources = [dict(index=offset+i, title=e.title, abstract="") for i, e in enumerate(entries)]
    return _request_translations(sources, entries, client, offset)


def test_only_bad_field_is_repaired_with_original_global_index_and_source():
    bad = row(21)
    bad["summary_zh"] = []
    client = Client([{"papers": [row(20), bad]},
                     {"papers": [dict(index=21, summary_zh="修复概述。")]}])
    result = request(client)
    assert result[20] == row(20)
    assert result[21]["title_zh"] == bad["title_zh"]
    assert result[21]["summary_zh"] == "修复概述。"
    prompt, operation, _ = client.calls[1]
    assert operation == "paper_translation"
    schema = prompt.split("Return only JSON:\n")[1].split("\nUse the exact")[0]
    assert json.loads(schema)["papers"][0]["index"] == 21
    assert 'failed_fields: ["summary_zh"]' in prompt
    source = json.loads(prompt.split("PAPERS_JSON:")[-1])
    assert [s["index"] for s in source] == [21]
    assert "Source paper 0" not in prompt
    assert "仅为期刊/栏目名，无法确认具体论文" in prompt


@pytest.mark.parametrize("rows", [[row(20)], [row(20), row(21), row(21)],
                                  [row(20), dict(index="21", title_zh="错误索引")]])
def test_missing_duplicate_or_noninteger_index_only_repairs_affected_entry(rows):
    client = Client([{"papers": rows}, {"papers": [row(21)]}])
    assert set(request(client)) == {20, 21}
    assert len(client.calls) == 2
    assert json.loads(client.calls[1][0].split("PAPERS_JSON:")[-1])[0]["index"] == 21


@pytest.mark.parametrize("code", ["invalid_json", "output_length"])
def test_untrusted_batch_gets_one_request_per_entry(code):
    client = Client([LLMError("invalid", code=code), {"papers": [row(20)]}, {"papers": [row(21)]}])
    assert set(request(client)) == {20, 21}
    assert len(client.calls) == 3
    assert len({deadline for _, _, deadline in client.calls}) == 1


@pytest.mark.parametrize("code", ["authentication", "network_error", "budget_exhausted", "cancelled"])
def test_system_failure_is_not_repeated_per_entry(code):
    client = Client([LLMError("system error", code=code)])
    with pytest.raises(LLMError) as caught:
        request(client)
    assert caught.value.code == code
    assert len(client.calls) == 1


def test_partial_error_retains_success_and_does_not_repeat_bad_repair():
    bad = row(21)
    bad["title_zh"] = {"bad": "type"}
    client = Client([{"papers": [row(20), bad]}, {"papers": [bad]}])
    events = []
    client.metrics.event_callback = lambda name, fields: events.append((name, fields))
    with pytest.raises(TranslationRecoveryError) as caught:
        request(client)
    assert caught.value.translations == {20: row(20)}
    assert caught.value.failed_indices == {21}
    assert len(client.calls) == 2
    assert all("Source paper" not in str(event) for event in events)
    assert any(fields.get("operation") == "paper_translation" for _, fields in events)


def test_cancel_and_external_budget_are_checked_before_request():
    client = Client([])
    client.metrics.cancel_event.set()
    with pytest.raises(LLMError, match="cancelled"):
        request(client)
    assert not client.calls
    client.metrics.cancel_event.clear()
    with llm_time_budget(0), pytest.raises(LLMError, match="budget"):
        request(client)
    assert not client.calls


def ranked(index):
    return RankedPaper(entry=PaperEntry(title=f"Source {index}"), relevance="high", score=.9,
                       title_zh="原有标题", summary_zh="原有概述", reason_zh="保留理由", matched_topics=["COF"])


def test_final_translation_keeps_success_and_original_failed_entry():
    client = Client([{"papers": [row(0)]}, {"papers": []}])
    events = []
    papers = [ranked(0), ranked(1)]
    result = translate_ranked_papers(papers, client, event_callback=events.append)
    assert result[0].title_zh == row(0)["title_zh"]
    assert result[1] is papers[1]
    assert result[0].entry is papers[0].entry
    assert result[0].score == .9 and result[0].reason_zh == "保留理由"
    assert len(events) == 1 and "回退本地规则" in events[0]


def test_rank_separate_translation_applies_partial_success_without_analysis_changes():
    analysis = {"papers": [dict(index=i, relevance="high", score=.9,
                 reason_zh="保留理由", matched_topics=["COF"]) for i in range(2)]}
    client = Client([analysis, {"papers": [row(0)]}, {"papers": []}])
    result = rank_papers([PaperEntry(title=f"Source {i}", abstract="Evidence") for i in range(2)],
                         InterestProfile(), client, separate_translation=True)
    assert result[0].title_zh == row(0)["title_zh"]
    assert all(p.score == .9 and p.reason_zh == "保留理由" for p in result)


def test_successful_recovery_does_not_trigger_core_failure_callback():
    client = Client([{"papers": []}, {"papers": [row(0)]}])
    events = []
    result = translate_ranked_papers([ranked(0)], client, event_callback=events.append)
    assert result[0].title_zh == row(0)["title_zh"]
    assert not events


def test_existing_chinese_title_can_remain_unchanged():
    client = Client([{"papers": [dict(index=5, title_zh="中文原题", summary_zh="证据有限。")]}])
    result = _request_translations([dict(index=5, title="中文原题")], [PaperEntry(title="中文原题")], client, 5)
    assert result[5]["title_zh"] == "中文原题"
    assert len(client.calls) == 1


def test_system_failure_during_repair_stops_remaining_repairs_and_keeps_success():
    client = Client([{"papers": [row(20)]}, LLMError("offline", code="network_error")])
    with pytest.raises(TranslationRecoveryError) as caught:
        request(client, count=3)
    assert caught.value.code == "network_error"
    assert caught.value.translations == {20: row(20)}
    assert caught.value.failed_indices == {21, 22}
    assert len(client.calls) == 2
