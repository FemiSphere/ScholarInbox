from literature_digest.dedupe import canonicalize_url, deduplicate_entries, normalize_doi, normalize_title
from literature_digest.models import PaperEntry


def test_dedupe_by_doi_url_and_fuzzy_title():
    entries = [
        PaperEntry(title="Thermal transport in pentagonal COF nanotubes", doi="10.1000/ABC.1"),
        PaperEntry(title="Different title", doi="https://doi.org/10.1000/abc.1"),
        PaperEntry(title="Machine learning potentials for COFs", url="https://example.org/a?utm_source=x"),
        PaperEntry(title="Machine learning potentials for COFs", url="https://example.org/a"),
        PaperEntry(title="Pentagonal framework materials for thermal conductivity"),
        PaperEntry(title="Thermal conductivity of pentagonal framework materials"),
    ]

    result = deduplicate_entries(entries, fuzzy_title_threshold=80)

    assert result.duplicates_removed == 3
    assert len(result.unique_entries) == 3


def test_dedupe_can_filter_against_existing_entries():
    historical = [
        PaperEntry(title="Thermal transport in pentagonal COF nanotubes", doi="10.1000/old"),
        PaperEntry(title="Machine learning interatomic potentials for atomistic simulations"),
        PaperEntry(title="URL duplicate", url="https://example.org/paper?utm_source=alert"),
    ]
    entries = [
        PaperEntry(title="Different title", doi="https://doi.org/10.1000/OLD"),
        PaperEntry(title="Machine-learning potentials for atomistic simulation"),
        PaperEntry(title="Same URL", url="https://example.org/paper"),
        PaperEntry(title="New paper about phonons"),
    ]

    result = deduplicate_entries(entries, fuzzy_title_threshold=80, existing_entries=historical)

    assert result.duplicates_removed == 3
    assert [entry.title for entry in result.unique_entries] == ["New paper about phonons"]


def test_dedupe_does_not_fuzzy_merge_numbered_parts():
    entries = [
        PaperEntry(title="Thermal transport in pentagonal frameworks: Part I"),
        PaperEntry(title="Thermal transport in pentagonal frameworks: Part II"),
    ]

    result = deduplicate_entries(entries, fuzzy_title_threshold=80)

    assert result.duplicates_removed == 0
    assert len(result.unique_entries) == 2


def test_shared_email_body_with_multiple_dois_does_not_merge_distinct_entries():
    shared_body = "First DOI 10.1000/first and second DOI 10.1000/second"
    entries = [
        PaperEntry(title="First distinct paper title", raw_text=shared_body),
        PaperEntry(title="Second unrelated article name", raw_text=shared_body),
    ]

    result = deduplicate_entries(entries, fuzzy_title_threshold=80)

    assert result.duplicates_removed == 0
    assert len(result.unique_entries) == 2


def test_normalizers():
    assert normalize_title("  A Study: Thermal-Conductivity! ") == "a study thermal conductivity"
    assert canonicalize_url("HTTPS://Example.org/A/?utm_source=x&keep=1#frag") == "https://example.org/A?keep=1"


def test_canonicalize_url_tolerates_malformed_bracketed_url():
    malformed = "https://www.apple.com... 阅读更多内容 | [链接](https://click.example.org/article"

    assert canonicalize_url(malformed) == malformed.lower()


def test_doi_normalization_removes_publisher_page_route_suffixes():
    assert normalize_doi("https://example.org/10.1088/1361-648X/ae74a5/meta") == "10.1088/1361-648x/ae74a5"
    assert normalize_doi("https://example.org/10.1088/1361-648X/ae74a5/pdf") == "10.1088/1361-648x/ae74a5"


def test_dedupe_checks_doi_in_all_fields_and_merges_richer_metadata():
    entries = [
        PaperEntry(
            title="Thermal transport in a framework",
            doi="not-a-valid-doi",
            url="https://example.org/doi/10.1000/merged",
        ),
        PaperEntry(
            title="Different representation of the same paper",
            doi="10.1000/MERGED",
            authors="A. Researcher",
            abstract="A longer and more useful abstract for the retained paper.",
        ),
    ]

    result = deduplicate_entries(entries)

    assert result.duplicates_removed == 1
    assert result.unique_entries[0].doi == "10.1000/merged"
    assert result.unique_entries[0].authors == "A. Researcher"
    assert result.unique_entries[0].abstract.startswith("A longer")


def test_title_normalization_handles_unicode_greek_and_subscripts():
    assert normalize_title("β-Ga₂O₃ thermal transport") == normalize_title("beta Ga2O3 thermal transport")
