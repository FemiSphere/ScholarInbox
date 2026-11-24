from literature_digest.interests import analyze_research_interests
from literature_digest.llm import LLMError
from literature_digest.llm.base import extract_json_object
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.models import InterestProfile, PaperEntry
from literature_digest.ranking import rank_papers


def test_ranking_uses_interest_profile_and_returns_chinese_fields():
    llm = OfflineStubClient()
    profile = analyze_research_interests("五边形 COF 纳米管热导率和机器学习势函数。", llm)
    papers = [
        PaperEntry(
            title="Machine-learning interatomic potentials for thermal transport in pentagonal COF nanotubes",
            abstract="Thermal conductivity and phonon transport.",
        ),
        PaperEntry(title="Organic synthesis of unrelated molecules"),
    ]

    ranked = rank_papers(papers, profile, llm)

    assert ranked[0].relevance == "high"
    assert ranked[0].title_zh.startswith("论文：")
    assert ranked[-1].relevance in {"medium", "low"}


class PartialRankingClient:
    def complete(self, prompt: str) -> str:
        return '{"papers":[{"index":0,"relevance":"high","score":0.8}]}'

    def complete_json(self, prompt: str):
        return extract_json_object(self.complete(prompt))


def test_ranking_falls_back_to_local_title_translation_when_title_missing():
    papers = [PaperEntry(title="Metal-modulated phonon transport in porphyrin-based MOFs")]

    ranked = rank_papers(
        papers,
        analyze_research_interests("COF 纳米管 热导率", OfflineStubClient()),
        PartialRankingClient(),
    )

    assert ranked[0].title_zh == "卟啉基 MOFs 中金属调控的声子输运"


class FailingRankingClient:
    def complete(self, prompt: str) -> str:
        return "not json"

    def complete_json(self, prompt: str):
        raise LLMError("test JSON failure")


def test_ranking_failure_uses_local_relevance_heuristic_instead_of_all_low():
    profile = InterestProfile(
        material_systems=["COF", "MOF", "pentagonal materials"],
        methods=["machine-learning interatomic potentials"],
        properties=["thermal conductivity", "phonon transport"],
        high_priority_topics=["COF/MOF thermal conductivity", "machine-learning interatomic potentials"],
        summary_zh="关注 COF/MOF、热导率、声子输运和机器学习势函数。",
    )
    papers = [
        PaperEntry(
            title="Anisotropic Thermal Conductivity Enhancement of Aligned Metal-Organic Frameworks",
            venue="ACS Materials Letters",
            abstract="Thermal conductivity and phonon transport in porous framework materials.",
        ),
        PaperEntry(
            title="Editorial board announcement and subscription information",
            venue="Publisher newsletter",
        ),
    ]

    ranked = rank_papers(papers, profile, FailingRankingClient())

    assert ranked[0].relevance in {"high", "medium"}
    assert ranked[0].score >= 0.28
    assert "热导率" in ranked[0].title_zh
    assert ranked[0].summary_zh
    assert ranked[0].reason_zh
    assert ranked[-1].score <= ranked[0].score
    assert ranked[-1].relevance == "irrelevant"
    assert ranked[-1].score == 0.0


class IrrelevantRankingClient:
    def complete(self, prompt: str) -> str:
        return ""

    def complete_json(self, prompt: str):
        return {
            "papers": [
                {
                    "index": 0,
                    "relevance": "irrelevant",
                    "score": 0,
                    "title_zh": "实验室软件订阅优惠",
                    "summary_zh": "这是软件订阅推广。",
                    "reason_zh": "属于商业推广，不是学术论文。",
                    "matched_topics": [],
                }
            ]
        }


def test_ranking_accepts_irrelevant_as_a_distinct_category():
    papers = [PaperEntry(title="Limited time offer for laboratory software")]

    ranked = rank_papers(papers, InterestProfile(), IrrelevantRankingClient())

    assert ranked[0].relevance == "irrelevant"
    assert ranked[0].score == 0.0


def test_genuine_academic_paper_outside_profile_remains_low():
    papers = [
        PaperEntry(
            title="Tribological behavior of aluminium against tool steel",
            venue="Journal of Tribology",
            abstract="A peer-reviewed study of friction coefficients and wear.",
        )
    ]

    ranked = rank_papers(papers, InterestProfile(), FailingRankingClient())

    assert ranked[0].relevance == "low"


def test_llm_cannot_mark_a_doi_paper_irrelevant_without_promotional_signals():
    paper = PaperEntry(
        title="Tribological behavior of aluminium against tool steel",
        doi="10.1234/tribology.2026.001",
    )

    ranked = rank_papers([paper], InterestProfile(), IrrelevantRankingClient())

    # A real paper is never "irrelevant"; outside the field it is folded as off_topic.
    assert ranked[0].relevance == "off_topic"
    assert ranked[0].score < 0.15
    assert "明确论文身份" in ranked[0].reason_zh


def test_off_topic_is_accepted_from_ranking_and_kept_distinct_from_irrelevant():
    from literature_digest.ranking import _ranked_from_payload

    entry = PaperEntry(title="Long-term clinical outcomes of statin therapy", doi="10.1/x")
    ranked = _ranked_from_payload(entry, {"relevance": "off_topic", "score": 0.05,
                                          "reason_zh": "临床医学，与材料方向无关。", "matched_topics": []})
    assert ranked.relevance == "off_topic"


def test_interest_profile_prompt_requests_broad_fields_and_cache_version_changes():
    from literature_digest import interests

    captured = {}

    class Client:
        def complete_json(self, prompt):
            captured["prompt"] = prompt
            return {"broad_fields": ["computational materials science"], "summary_zh": "计算材料"}

    profile = interests.analyze_research_interests("computational materials", Client())
    assert "broad_fields" in captured["prompt"]
    assert profile.broad_fields == ["computational materials science"]
    assert interests.INTEREST_CACHE_VERSION >= 2
