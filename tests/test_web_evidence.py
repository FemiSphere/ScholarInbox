import io
import json
from threading import Event
import time
import urllib.error

import pytest

from literature_digest.models import PaperEntry
from literature_digest.web_evidence import (EvidenceUnavailable, WebEvidenceClient, acquire_evidence,
    extract_abstract, match_identity, public_url)


TITLE = 'Machine learning prediction of thermal transport in covalent organic frameworks'
ABSTRACT = ('We investigate thermal transport in covalent organic frameworks using atomistic simulations. '
            'The calculated conductivity depends on framework connectivity and phonon scattering, '
            'and the results identify structural variables relevant to predicting heat conduction.')
DOI = '10.1234/test.paper'
URL = 'https://pubs.acs.org/doi/10.1234/test.paper'


def paper(**kwargs):
    return PaperEntry(**{'title': TITLE, 'doi': DOI, 'url': URL, **kwargs})


def page(title=TITLE, doi=DOI, abstract=ABSTRACT):
    return {'title': title, 'content': f'# {title}\nDOI: {doi}\n\n## Abstract\n{abstract}\n\n## Introduction\nOther text.'}


class FakeClient:
    def __init__(self, pages=None, results=None):
        self.pages = pages or {}
        self.results = results or []
        self.fetches = []
        self.queries = []
    def fetch(self, url):
        self.fetches.append(url)
        result = self.pages.get(url, EvidenceUnavailable('http_404'))
        if isinstance(result, Exception):
            raise result
        return result
    def search(self, query):
        self.queries.append(query)
        if isinstance(self.results, Exception):
            raise self.results
        return self.results


def test_known_paper_fetch_verifies_identity_and_original_abstract():
    client = FakeClient({URL: page()})
    evidence = acquire_evidence(paper(), client)
    assert evidence.abstract == ABSTRACT
    assert evidence.source_url == URL
    assert evidence.source_kind == 'publisher_abstract'
    assert evidence.matched_by == 'doi'
    assert not client.queries


def test_wrong_doi_or_different_paper_is_never_accepted():
    for response in [page(doi='10.9999/other'), page(title='Another research paper with different title')]:
        assert acquire_evidence(paper(), FakeClient({URL: response})) is None


def test_reference_list_doi_does_not_establish_identity():
    unrelated = page(title='A review article about thermal materials', doi='10.9999/review')
    unrelated['content'] += f'\n## References\n{TITLE} DOI: {DOI}'
    assert acquire_evidence(paper(), FakeClient({URL: unrelated})) is None


def test_doi_landing_page_accepts_case_and_encoded_doi_after_title_match():
    target = 'https://doi.org/10.1234/TEST.paper'
    entry = paper(doi='https://doi.org/10.1234/TEST.paper', url=target)
    client = FakeClient({target: page(doi=DOI)})
    evidence = acquire_evidence(entry, client)
    assert evidence.matched_by == 'doi'
    assert evidence.identity == DOI


def test_search_summary_is_not_an_original_abstract():
    result = {'title': TITLE, 'url': URL, 'summary': ABSTRACT, 'snippet': ABSTRACT}
    evidence = acquire_evidence(paper(url='', doi=''), FakeClient(results=[result]))
    assert evidence is None


def test_search_content_can_supply_source_abstract_without_duplicate_fetch():
    result = {'url': URL, **page()}
    client = FakeClient(results=[result])
    evidence = acquire_evidence(paper(url='', doi=''), client)
    assert evidence.abstract == ABSTRACT
    assert client.fetches == []
    assert len(client.queries[0]) <= 128


def test_search_unknown_domains_are_not_used_even_with_matching_title_and_abstract():
    result = {'url': 'https://random-blog.example/post', **page()}
    client = FakeClient(results=[result])
    assert acquire_evidence(paper(url='', doi=''), client) is None
    assert not client.fetches


def test_title_only_search_handles_long_titles_without_exceeding_query_limit():
    client = FakeClient()
    assert acquire_evidence(paper(title=TITLE * 3, url='', doi=''), client) is None
    assert len(client.queries[0]) == 128
    assert client.queries[0].startswith('"') and client.queries[0].endswith('"')


def test_title_page_without_actual_abstract_or_search_matches_returns_none():
    client = FakeClient({URL: {'title': TITLE, 'content': f'# {TITLE}\nDOI: {DOI}\nSubscribe to access this paper.'}})
    assert acquire_evidence(paper(), client) is None


def test_arxiv_abstract_blockquote_and_identity():
    url = 'https://arxiv.org/abs/2610.12345'
    content = {'title': f'[2610.12345] {TITLE}', 'content': f'Title: {TITLE}\narXiv:2610.12345\n>Abstract: {ABSTRACT}\n## Subjects\nMaterials Science'}
    evidence = acquire_evidence(paper(url=url, doi=''), FakeClient({url: content}))
    assert evidence.source_kind == 'preprint_abstract'
    assert evidence.matched_by == 'arxiv'
    assert evidence.abstract == ABSTRACT


def test_short_generic_title_needs_identifier_or_author_corroboration():
    entry = paper(title='Thermal transport', doi='', url='')
    content = page(title='Thermal transport', doi='')
    assert match_identity(entry, content, URL) is None
    content['content'] = content['content'].replace('## Abstract', 'Authors: Alice Smith\n## Abstract')
    entry.authors = 'Alice Smith'
    assert match_identity(entry, content, URL)[0] == 'title'


def test_navigation_abstract_link_is_not_accepted_as_abstract_section():
    content = f'[Abstract](#abstract)\n# {TITLE}\nMenu\n## Abstract\n{ABSTRACT}\n## References\nOther material'
    assert extract_abstract(content) == ABSTRACT


def test_ai_extraction_must_return_exact_source_passage_and_cannot_invent():
    class Model:
        def __init__(self, text):
            self.text = text
        def complete_json(self, prompt):
            assert 'untrusted data' in prompt
            return {'abstract': self.text}
    no_heading = {'title': TITLE, 'content': f'# {TITLE}\nDOI: {DOI}\nSource Abstract — {ABSTRACT}'}
    assert acquire_evidence(paper(), FakeClient({URL: no_heading}), Model(ABSTRACT)).abstract == ABSTRACT
    hallucination = 'A wholly invented result. ' * 15
    assert acquire_evidence(paper(), FakeClient({URL: no_heading}), Model(hallucination)) is None


def test_transport_failure_propagates_instead_of_becoming_negative_cacheable_none():
    client = FakeClient({URL: EvidenceUnavailable('timeout')})
    with pytest.raises(EvidenceUnavailable, match='timeout'):
        acquire_evidence(paper(), client)
    with pytest.raises(EvidenceUnavailable, match='http_401'):
        acquire_evidence(paper(), FakeClient({URL: EvidenceUnavailable('http_401')}))


@pytest.mark.parametrize('url', ['http://127.0.0.1/a', 'http://[::1]/a', 'http://localhost/a',
    'https://192.168.1.10/a', 'https://10.0.0.1/a', 'file:///tmp/page', 'https://user:pass@nature.com/a',
    'https://example.local/a', 'https://nature.com:1234/a', 'https://localhost./a',
    'https://127.1/a', 'https://%31%32%37.0.0.1/a', 'https://127.0。0.1/a'])
def test_private_or_credential_urls_are_rejected(url):
    assert not public_url(url)


class Response:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.body[:size]


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv('TEST_WEB_KEY', 'offline-only-key')
    return WebEvidenceClient('https://api.deepseek.com', 'TEST_WEB_KEY', min_interval_seconds=0, max_retries=0)


def test_transport_payloads_use_independent_search_fetch_endpoints(transport, monkeypatch):
    captured = []
    def fake_open(request, timeout):
        captured.append((request.full_url, json.loads(request.data)))
        return Response(json.dumps({'results': []} if request.full_url.endswith('search') else page()).encode())
    monkeypatch.setattr('urllib.request.urlopen', fake_open)
    assert transport.search('DOI 10.1234/test.paper') == []
    assert transport.fetch(URL)['content']
    assert captured[0] == ('https://api.deepseek.com/v1/tools/search', {'query':'DOI 10.1234/test.paper','count':3,'need_content':True})
    assert captured[1] == ('https://api.deepseek.com/v1/tools/fetch', {'url':URL})


def test_transport_body_size_and_request_count_are_bounded(transport, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: Response(b'x' * 60))
    transport.max_response_bytes = 20
    with pytest.raises(EvidenceUnavailable, match='response_too_large'):
        transport.fetch(URL)
    transport.max_requests = transport.request_count
    with pytest.raises(EvidenceUnavailable, match='request_limit'):
        transport.search('test')


def test_transport_logs_metadata_without_keys_queries_or_page_content(transport, monkeypatch, tmp_path):
    from literature_digest.telemetry import RunMetrics
    metrics = RunMetrics()
    path = tmp_path / 'events.jsonl'
    metrics.configure_journal(path)
    transport.metrics = metrics
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: Response(json.dumps({'results':[]}).encode()))
    transport.search('private paper query')
    log = path.read_text()
    assert 'evidence_request_started' in log
    assert 'offline-only-key' not in log
    assert 'private paper query' not in log


def test_transport_permanent_error_does_not_retry(transport, monkeypatch):
    calls = []
    def fake_open(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 401, 'secret', {}, io.BytesIO())
    monkeypatch.setattr('urllib.request.urlopen', fake_open)
    transport.max_retries = 1
    with pytest.raises(EvidenceUnavailable, match='http_401'):
        transport.search('test')
    assert len(calls) == 1


def test_transport_cancel_interrupts_wait(transport, monkeypatch):
    transport.cancel_event = Event()
    transport.cancel_event.set()
    with pytest.raises(KeyboardInterrupt):
        transport.search('test')


def test_transport_wall_clock_budget_bounds_blocking_network(transport, monkeypatch):
    release = Event()
    def fake_open(request, timeout):
        release.wait(2)
        return Response(json.dumps({'results':[]}).encode())
    monkeypatch.setattr('urllib.request.urlopen', fake_open)
    transport.timeout_seconds = 0.05
    started = time.monotonic()
    try:
        with pytest.raises(EvidenceUnavailable, match='timeout'):
            transport.search('test')
    finally:
        release.set()
    assert time.monotonic() - started < 0.5


def test_abstracting_navigation_is_not_an_abstract_label():
    assert extract_abstract('Abstracting and indexing services\n' + ABSTRACT) is None


def test_ai_cannot_relabel_unmarked_source_prose_as_an_abstract():
    class Model:
        def complete_json(self, prompt):
            return {'abstract': ABSTRACT}
    content = {'title': TITLE, 'content': f'# {TITLE}\nDOI: {DOI}\nIntroduction\n{ABSTRACT}'}
    assert acquire_evidence(paper(), FakeClient({URL: content}), Model()) is None


def test_arxiv_explicit_version_conflict_and_wrong_metadata_id_rejected():
    entry = paper(doi='', url='https://arxiv.org/abs/2610.12345v1')
    metadata = {'title': TITLE, 'content': f'Title: {TITLE}\narXiv:2610.12345v2\n## Abstract\n{ABSTRACT}'}
    assert match_identity(entry, metadata, 'https://arxiv.org/abs/2610.12345v2') is None
    metadata['content'] = metadata['content'].replace('2610.12345v2', '2610.99999')
    assert match_identity(entry, metadata, entry.url) is None


def test_arxiv_escaped_abstract_colon_extracts_source_and_stops_metadata():
    content = f"# {TITLE}\n            Abstract\\: {ABSTRACT}\n\nComments\\: 13 pages\nSubjects\\: Materials science\nSubmission history\nMore source metadata"
    assert extract_abstract(content) == ABSTRACT


def test_arxiv_pdf_is_canonicalized_to_abstract_page_without_spending_pdf_fetch():
    url = 'https://arxiv.org/abs/2610.12345v2'
    client = FakeClient({url: {'title': TITLE, 'content': f'Title: {TITLE}\narXiv:2610.12345v2\nAbstract\\: {ABSTRACT}\nComments: 12 pages'}})
    evidence = acquire_evidence(paper(url='https://arxiv.org/pdf/2610.12345v2.pdf', doi=''), client)
    assert evidence.source_url == url
    assert client.fetches == [url]


def test_title_prefix_does_not_prevent_distinctive_title_identity():
    assert match_identity(paper(), page(title='Title: ' + TITLE), URL)[0] == 'doi'
    assert match_identity(paper(), page(title='Title\\: ' + TITLE + ' - ScienceDirect'), URL)[0] == 'doi'


def test_scientific_comparisons_and_latex_are_preserved_by_source_normalization():
    from literature_digest.web_evidence import _plain
    text = r'The domain q < 0.5 and T > 300 contains modes with \kappa < 2; x > 0.'
    assert _plain(text) == text
    assert _plain('<p>H<sub>2</sub>O with q &lt; 0.5 and T &gt; 300.</p>') == 'H2O with q < 0.5 and T > 300.'


def test_known_pmc_repository_is_labeled_honestly_and_structured_abstract_complete():
    url = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC13672694/'
    structured = f'## Abstract\n### Background\n{ABSTRACT}\n### Methods\nSimulations and measurements were compared across the sampled structures.\n## Introduction\nBody of the paper'
    response = {'title': TITLE, 'content': f'# {TITLE}\nDOI: {DOI}\n' + structured}
    evidence = acquire_evidence(paper(url=url), FakeClient({url: response}))
    assert evidence.source_kind == 'repository_abstract'
    assert 'Simulations and measurements' in evidence.abstract
    assert 'Body of the paper' not in evidence.abstract
