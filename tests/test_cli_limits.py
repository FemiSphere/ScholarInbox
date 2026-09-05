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
