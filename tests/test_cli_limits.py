from literature_digest.cli import _apply_digest_limits
from literature_digest.models import PaperEntry, RankedPaper


def test_apply_digest_limits_can_limit_low_relevance_items():
    ranked = [
        RankedPaper(
            entry=PaperEntry(title=f"paper {index}"),
            relevance="low",
            score=0.0,
            title_zh=f"论文 {index}",
            summary_zh="摘要",
            reason_zh="理由",
        )
        for index in range(3)
    ]
    config = {
        "digest": {
            "max_high_relevance": 20,
            "max_medium_relevance": 30,
            "max_low_relevance": 2,
        }
    }

    limited = _apply_digest_limits(ranked, config)

    assert [paper.entry.title for paper in limited] == ["paper 0", "paper 1"]


def test_apply_digest_limits_can_limit_irrelevant_items_independently():
    ranked = [
        RankedPaper(
            entry=PaperEntry(title=f"promotion {index}"),
            relevance="irrelevant",
            score=0.0,
            title_zh=f"推广 {index}",
            summary_zh="非学术内容",
            reason_zh="商业推广",
        )
        for index in range(3)
    ]
    config = {
        "digest": {
            "max_high_relevance": 20,
            "max_medium_relevance": 30,
            "max_irrelevant": 1,
        }
    }

    limited = _apply_digest_limits(ranked, config)

    assert [paper.entry.title for paper in limited] == ["promotion 0"]


def test_omitted_by_limits_note_reports_hidden_counts_per_level():
    from literature_digest.cli import _omitted_by_limits_note
    from literature_digest.models import PaperEntry, RankedPaper

    def paper(level, i):
        return RankedPaper(entry=PaperEntry(title=f"{level}{i}"), relevance=level, score=.5,
                           title_zh="题", summary_zh="概述", reason_zh="理由")

    ranked = [paper("medium", i) for i in range(5)] + [paper("low", i) for i in range(3)]
    displayed = ranked[:2] + ranked[5:]
    note = _omitted_by_limits_note(ranked, displayed)
    assert "中相关 3 篇" in note and "低相关" not in note
    assert _omitted_by_limits_note(ranked, ranked) == ""
