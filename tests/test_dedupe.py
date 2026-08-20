from literature_digest.dedupe import canonicalize_url, deduplicate_entries, normalize_title
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


def test_normalizers():
    assert normalize_title("  A Study: Thermal-Conductivity! ") == "a study thermal conductivity"
    assert canonicalize_url("HTTPS://Example.org/A/?utm_source=x&keep=1#frag") == "https://example.org/A?keep=1"


def test_canonicalize_url_tolerates_malformed_bracketed_url():
    malformed = "https://www.apple.com... 阅读更多内容 | [链接](https://click.example.org/article"

    assert canonicalize_url(malformed) == malformed.lower()
