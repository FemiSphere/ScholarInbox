import pytest

from literature_digest.models import PaperEntry
from literature_digest.scholarly_sources import ScholarlyClient, acquire_from_metadata, titles_match
from literature_digest.web_evidence import EvidenceUnavailable, acquire_evidence

TITLE = "Phonon transport in pentagonal covalent organic frameworks from machine learning potentials"
ABSTRACT = ("We compute lattice thermal conductivity of pentagonal covalent organic frameworks using a "
            "machine-learning interatomic potential and find strong anharmonic phonon scattering.")


class Fake(ScholarlyClient):
    def __init__(self, routes):
        super().__init__()
        self.routes, self.urls = routes, []

    def get_json(self, url):
        self.urls.append(url)
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        return None


def crossref(doi=None, abstract=ABSTRACT, title=TITLE, kind="journal-article"):
    return {"message": {"DOI": doi or "10.1021/x.1", "title": [title], "abstract": f"<jats:p>{abstract}</jats:p>", "type": kind}}


def inverted(text):
    index = {}
    for position, word in enumerate(text.split()):
        index.setdefault(word, []).append(position)
    return index


def test_entry_doi_uses_crossref_abstract_and_links_doi():
    client = Fake({"api.crossref.org/works/10.1021/jacs.5c1": crossref("10.1021/jacs.5c1")})
    record = acquire_from_metadata(PaperEntry(title=TITLE, doi="10.1021/jacs.5c1"), client)
    assert record.abstract == ABSTRACT
    assert record.source_url == "https://doi.org/10.1021/jacs.5c1"
    assert record.source_kind == "publisher_abstract" and record.matched_by == "doi"


def test_doi_from_url_falls_back_to_openalex_when_crossref_has_no_abstract():
    client = Fake({
        "api.crossref.org/works/10.1103/physrevb.1": crossref(abstract=""),
        "api.openalex.org/works/doi:10.1103/physrevb.1": {"title": TITLE, "abstract_inverted_index": inverted(ABSTRACT)},
    })
    entry = PaperEntry(title=TITLE, url="https://journals.aps.org/prb/abstract/10.1103/PhysRevB.1")
    record = acquire_from_metadata(entry, client)
    assert record.abstract == ABSTRACT and record.identity == "10.1103/physrevb.1"


def test_sciencedirect_pii_is_resolved_through_crossref():
    client = Fake({
        "alternative-id:S0301010426001234": {"message": {"items": [{"DOI": "10.1016/j.cp.2026.1", "title": [TITLE]}]}},
        "api.crossref.org/works/10.1016/j.cp.2026.1": crossref("10.1016/j.cp.2026.1"),
    })
    entry = PaperEntry(title=TITLE, url="https://www.sciencedirect.com/science/article/pii/S0301010426001234")
    assert acquire_from_metadata(entry, client).identity == "10.1016/j.cp.2026.1"


def test_title_search_requires_a_strict_match():
    good = {"results": [{"title": TITLE, "doi": "https://doi.org/10.48550/arxiv.2601.1", "type": "preprint",
                         "abstract_inverted_index": inverted(ABSTRACT)}]}
    record = acquire_from_metadata(PaperEntry(title=TITLE, url="https://click.example/track"),
                                   Fake({"api.openalex.org/works?": good}))
    assert record.matched_by == "title" and record.source_kind == "preprint_abstract"

    other = {"results": [{"title": "Phonon transport in hexagonal boron nitride", "doi": "https://doi.org/10.1/y",
                          "abstract_inverted_index": inverted(ABSTRACT)}]}
    assert acquire_from_metadata(PaperEntry(title=TITLE), Fake({"api.openalex.org/works?": other})) is None


def test_mismatched_doi_title_is_rejected():
    client = Fake({"api.crossref.org/works/10.1/z": crossref(title="An unrelated paper about catalysis kinetics"),
                   "api.openalex.org/works/doi:10.1/z": {"title": "An unrelated paper about catalysis kinetics",
                                                          "abstract_inverted_index": inverted(ABSTRACT)}})
    assert acquire_from_metadata(PaperEntry(title=TITLE, doi="10.1/z"), client) is None


def test_truncated_email_title_matches_with_doi_but_not_by_search():
    truncated = TITLE[:60] + "…"
    assert titles_match(truncated, TITLE, strict=False)
    assert not titles_match(truncated, TITLE, strict=True)


def test_source_errors_are_swallowed_but_budget_errors_propagate():
    entry = PaperEntry(title=TITLE, doi="10.1/a")
    assert acquire_from_metadata(entry, Fake({"crossref": EvidenceUnavailable("http_503")})) is None
    with pytest.raises(EvidenceUnavailable):
        acquire_from_metadata(entry, Fake({"crossref": EvidenceUnavailable("budget_exhausted")}))


class PaidClient:
    def __init__(self):
        self.calls = []

    def search(self, query):
        self.calls.append(("search", query))
        return []

    def fetch(self, url):
        self.calls.append(("fetch", url))
        raise EvidenceUnavailable("http_404")


def test_metadata_hit_avoids_paid_search_and_fetch():
    paid = PaidClient()
    metadata = Fake({"api.crossref.org/works/10.1021/a": crossref("10.1021/a")})
    record = acquire_evidence(PaperEntry(title=TITLE, doi="10.1021/a", url="https://pubs.acs.org/doi/10.1021/a"),
                              paid, metadata=metadata)
    assert record is not None and paid.calls == []


def test_sciencedirect_pages_are_not_fetched_after_metadata_miss():
    paid = PaidClient()
    entry = PaperEntry(title=TITLE, doi="10.1016/j.x.1",
                       url="https://www.sciencedirect.com/science/article/pii/S0000000000000001")
    assert acquire_evidence(entry, paid, metadata=Fake({})) is None
    assert [kind for kind, _ in paid.calls] == ["search"]
