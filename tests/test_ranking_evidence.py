import json
from dataclasses import replace
from html.parser import HTMLParser

from literature_digest.digest import render_html, render_markdown
from literature_digest.llm import LLMError
from literature_digest.models import DigestRun, EvidenceRecord, InterestProfile, PaperEntry, RankedPaper, RunStats
from literature_digest.ranking import rank_papers, translate_ranked_papers
from literature_digest.telemetry import current_llm_operation


def evidence(url='https://pubs.example.org/paper?x=1&y=2'):
    return EvidenceRecord(abstract='Verified source abstract. ' * 200, source_url=url,
        source_kind='publisher_abstract', fetched_at='2026-10-22T00:00:00+00:00',
        matched_by='doi', identity='10.1234/example')


class EvidenceClient:
    def __init__(self, fail_translation=False):
        self.calls = []
        self.fail_translation = fail_translation

    def complete_json(self, prompt):
        operation = current_llm_operation()
        self.calls.append((operation, prompt))
        items = json.loads(prompt.rsplit('PAPERS_JSON:\n', 1)[1])
        if operation == 'paper_ranking':
            return {'papers': [dict(index=item['index'], relevance='high', score=0.91,
                reason_zh='材料体系和研究方法相关。', matched_topics=['COF'],
                title_zh='不应使用的思考翻译', summary_zh='不应使用的思考概述') for item in items]}
        if self.fail_translation:
            raise LLMError('Unavailable')
        return {'papers': [dict(index=item['index'], title_zh='来源支持的中文标题',
            summary_zh='依据来源摘要生成的中文概述。', relevance='low', score=0) for item in items]}


def test_analysis_only_uses_one_call_and_discards_unasked_translations():
    client = EvidenceClient()
    ranked = rank_papers([PaperEntry(title='Thermal transport in COF', abstract='Email excerpt.')],
        InterestProfile(), client, analysis_only=True)
    assert [operation for operation, _ in client.calls] == ['paper_ranking']
    schema = client.calls[0][1].split('Schema:')[1].split('Rules:')[0]
    assert 'title_zh' not in schema
    assert ranked[0].title_zh != '不应使用的思考翻译'
    assert ranked[0].summary_zh != '不应使用的思考概述'


def test_verified_abstract_reaches_analysis_and_final_translation_without_mutating_email():
    client = EvidenceClient()
    source = evidence()
    entry = PaperEntry(title='Thermal transport in COF', abstract='Original short email excerpt.')
    ranked = rank_papers([entry], InterestProfile(), client, analysis_only=True,
        evidence_by_index={0: source})
    analyzed_input = json.loads(client.calls[0][1].rsplit('PAPERS_JSON:\n', 1)[1])[0]
    assert analyzed_input['source_status'] == 'publisher_abstract'
    assert len(analyzed_input['abstract']) > 2000
    assert analyzed_input['abstract'] == source.abstract
    assert analyzed_input['original_email_excerpt'] == entry.abstract
    assert analyzed_input['abstract_source_url'] == source.source_url
    assert ranked[0].evidence is source
    assert '仅有标题' not in ranked[0].reason_zh
    final = translate_ranked_papers(ranked, client)
    assert [operation for operation, _ in client.calls] == ['paper_ranking', 'paper_translation']
    translated_input = json.loads(client.calls[1][1].rsplit('PAPERS_JSON:\n', 1)[1])[0]
    assert translated_input['source_status'] == 'publisher_abstract'
    assert translated_input['abstract'] == source.abstract
    assert final[0].title_zh == '来源支持的中文标题'
    assert final[0].score == ranked[0].score == 0.91
    assert final[0].relevance == ranked[0].relevance == 'high'
    assert final[0].reason_zh == ranked[0].reason_zh
    assert final[0].evidence is source
    assert entry.abstract == 'Original short email excerpt.'


def test_evidence_global_index_across_multiple_batches():
    client = EvidenceClient()
    entries = [PaperEntry(title=f'Paper {i}', abstract='Email excerpt.') for i in range(3)]
    ranked = rank_papers(entries, InterestProfile(), client, analysis_only=True,
        batch_size=1, evidence_by_index={2: evidence()})
    by_title = {paper.entry.title: paper for paper in ranked}
    assert by_title['Paper 2'].evidence is not None
    assert by_title['Paper 0'].evidence is None
    assert by_title['Paper 1'].evidence is None


def test_translation_failure_keeps_analytical_result_and_evidence():
    client = EvidenceClient(fail_translation=True)
    original = RankedPaper(PaperEntry(title='Paper title'), 'medium', 0.6,
        '已有标题', '已有概述', '已有判断', ['COF'], evidence=evidence())
    events = []
    final = translate_ranked_papers([original], client, event_callback=events.append)
    assert final == [original]
    assert final[0].evidence is original.evidence
    assert any('回退本地规则' in event for event in events)


def make_run(source):
    return DigestRun('2026-10-22', RunStats(paper_entries_extracted=1), InterestProfile(), [
        RankedPaper(PaperEntry(title='Source paper', url='https://example.org/paper'),
            'high', 0.9, '中文标题', '中文概述', '简短理由', evidence=source)])


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.details_depth = 0
    def handle_starttag(self, tag, attrs):
        if tag == 'details': self.details_depth += 1
        if tag == 'a': self.links.append((dict(attrs), self.details_depth))
    def handle_endtag(self, tag):
        if tag == 'details': self.details_depth -= 1


def test_render_adds_only_minimal_source_link_inside_existing_details():
    run = make_run(evidence())
    html = render_html(run)
    markdown = render_markdown(run)
    parser = Links(); parser.feed(html)
    matched = [(attrs, depth) for attrs, depth in parser.links if attrs.get('href') == run.papers[0].evidence.source_url]
    assert len(matched) == 1 and matched[0][1] == 1
    assert '摘要来源' in html and '摘要来源' in markdown
    assert '评级变化' not in html
    assert 'matched_by' not in html
    assert 'fetched_at' not in html
    assert 'Verified source abstract.' not in html  # Source text stays in bounded cache, not the reader.
    assert '摘要来源' not in render_html(make_run(None))


def test_source_link_rejects_non_web_or_credential_urls():
    for url in ['javascript:alert(1)', 'file:///tmp/example', 'https://user:password@example.org/paper', 'https://example.org/paper\nnew']:
        run = make_run(evidence(url))
        assert '摘要来源' not in render_html(run)
        assert '摘要来源' not in render_markdown(run)
