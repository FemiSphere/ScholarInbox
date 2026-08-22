from __future__ import annotations

import json
from datetime import date

from literature_digest.models import PaperEntry
from literature_digest.paper_registry import (
    PaperRegistry,
    bootstrap_registry_from_markdown,
    extract_arxiv_ids,
)


def test_registry_matches_doi_page_variants_and_arxiv_versions(tmp_path):
    registry = PaperRegistry(tmp_path / "registry.json")
    registry.record_entries(
        [
            PaperEntry(
                title="Thermal transport in a layered material",
                doi="10.1088/1361-648X/ae74a5/meta",
                url="https://iopscience.iop.org/article/10.1088/1361-648X/ae74a5/meta",
            ),
            PaperEntry(
                title="Machine learning potentials for porous frameworks",
                url="https://arxiv.org/abs/2608.01234v1",
            ),
        ],
        seen_on=date(2026, 8, 20),
    )

    doi_match = registry.find_match(
        PaperEntry(
            title="Different source title",
            url="https://iopscience.iop.org/article/10.1088/1361-648X/ae74a5/pdf",
        )
    )
    arxiv_match = registry.find_match(
        PaperEntry(
            title="Updated title for machine learning potentials",
            url="https://arxiv.org/pdf/2608.01234v2.pdf",
        )
    )

    assert doi_match is not None and doi_match.reason == "doi"
    assert arxiv_match is not None and arxiv_match.reason == "arxiv"
    assert extract_arxiv_ids("arXiv:2608.01234v3") == ["2608.01234"]


def test_registry_prunes_by_last_seen_and_keeps_recently_repeated_papers(tmp_path):
    registry = PaperRegistry(tmp_path / "registry.json", retention_days=30)
    registry.record_entries(
        [PaperEntry(title="Old paper that never appeared again")],
        seen_on=date(2026, 7, 20),
    )
    repeated = PaperEntry(title="Old paper repeated within the active window")
    registry.record_entries([repeated], seen_on=date(2026, 7, 10))
    registry.record_entries([repeated], seen_on=date(2026, 8, 10))

    removed = registry.prune(date(2026, 8, 23))

    assert removed == 1
    assert len(registry.papers) == 1
    remaining = next(iter(registry.papers.values()))
    assert remaining["last_seen"] == "2026-08-10"
    assert remaining["seen_count"] == 2


def test_registry_save_is_atomic_and_round_trips(tmp_path):
    path = tmp_path / "data" / "paper_registry.json"
    registry = PaperRegistry(path, retention_days=30)
    registry.record_entries(
        [
            PaperEntry(
                title="Pentagonal COF thermal transport",
                doi="10.1000/example",
                source_subject="COF alert",
            )
        ],
        seen_on=date(2026, 8, 22),
    )

    registry.save(reference_date=date(2026, 8, 23))
    loaded = PaperRegistry.load(path, reference_date=date(2026, 8, 23), retention_days=30)

    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
    assert loaded.loaded_from_disk is True
    assert loaded.find_match(PaperEntry(title="Other", doi="10.1000/EXAMPLE")).reason == "doi"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["retention_days"] == 30
    assert len(payload["papers"]) == 1


def test_registry_fuzzy_match_has_version_and_containment_guards(tmp_path):
    registry = PaperRegistry(tmp_path / "registry.json", fuzzy_title_threshold=90)
    registry.record_entries(
        [
            PaperEntry(
                title="Machine-learning interatomic potentials for thermal transport in pentagonal frameworks Part I"
            ),
            PaperEntry(title="Thermal transport in graphene"),
        ],
        seen_on=date(2026, 8, 20),
    )

    similar = registry.find_match(
        PaperEntry(
            title="Machine learning interatomic potentials for thermal transport in pentagonal framework, Part I"
        )
    )
    different_part = registry.find_match(
        PaperEntry(
            title="Machine learning interatomic potentials for thermal transport in pentagonal framework Part II"
        )
    )
    contained = registry.find_match(
        PaperEntry(title="Thermal transport in graphene and hexagonal boron nitride heterostructures")
    )

    assert similar is not None and similar.reason == "fuzzy_title"
    assert different_part is None
    assert contained is None


def test_registry_filter_reports_match_reasons(tmp_path):
    registry = PaperRegistry(tmp_path / "registry.json")
    registry.record_entries(
        [
            PaperEntry(title="Paper with DOI", doi="10.1000/doi"),
            PaperEntry(title="Exact historical title"),
        ],
        seen_on=date(2026, 8, 20),
    )

    result = registry.filter_new(
        [
            PaperEntry(title="Another title", doi="10.1000/doi"),
            PaperEntry(title="Exact historical title"),
            PaperEntry(title="A genuinely new paper"),
        ]
    )

    assert result.duplicates_removed == 2
    assert result.reasons == {"doi": 1, "exact_title": 1}
    assert [entry.title for entry in result.unique_entries] == ["A genuinely new paper"]


def test_bootstrap_uses_only_markdown_within_retention_window(tmp_path):
    old = tmp_path / "2026-07-01-digest.md"
    recent = tmp_path / "2026-08-10-digest.md"
    old.write_text("### 1. Old\n- 英文原题：Old historical paper\n", encoding="utf-8")
    recent.write_text("### 1. Recent\n- 英文原题：Recent historical paper\n", encoding="utf-8")
    registry = PaperRegistry(tmp_path / "registry.json", retention_days=30)

    files, entries = bootstrap_registry_from_markdown(
        registry,
        tmp_path,
        reference_date=date(2026, 8, 23),
    )

    assert files == 1
    assert entries == 1
    assert registry.find_match(PaperEntry(title="Recent historical paper")) is not None
    assert registry.find_match(PaperEntry(title="Old historical paper")) is None


def test_registry_records_all_source_aliases_for_same_paper(tmp_path):
    registry = PaperRegistry(tmp_path / "registry.json")
    registry.record_entries(
        [
            PaperEntry(
                title="Thermal conductivity of pentagonal frameworks",
                doi="10.1000/same",
                source_subject="pentagonal materials alert",
            ),
            PaperEntry(
                title="Thermal conductivity of pentagonal frameworks",
                doi="10.1000/same",
                source_subject="thermal transport alert",
            ),
        ],
        seen_on=date(2026, 8, 23),
    )

    record = next(iter(registry.papers.values()))
    assert record["seen_count"] == 2
    assert record["source_subjects"] == [
        "pentagonal materials alert",
        "thermal transport alert",
    ]


def test_registry_ignores_ambiguous_shared_context_identifiers(tmp_path):
    shared_body = "arXiv:2608.00001 and arXiv:2608.00002; DOI 10.1000/one and 10.1000/two"
    registry = PaperRegistry(tmp_path / "registry.json")

    registry.record_entries(
        [
            PaperEntry(title="First distinct paper title", raw_text=shared_body),
            PaperEntry(title="Second unrelated article name", raw_text=shared_body),
        ],
        seen_on=date(2026, 8, 23),
    )

    assert len(registry.papers) == 2
    assert all(not record["dois"] for record in registry.papers.values())
    assert all(not record["arxiv_ids"] for record in registry.papers.values())
