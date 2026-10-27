from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from literature_digest import enrichment as module
from literature_digest.models import PaperEntry, RankedPaper, EvidenceRecord, InterestProfile
from literature_digest.web_evidence import EvidenceUnavailable


def paper(name, level, score):
    return RankedPaper(PaperEntry(title=name, url='https://arxiv.org/abs/2601.12345', abstract='original email'),
        level, score, '标题', '原概述', '原理由')


def evidence():
    return EvidenceRecord('A verified source abstract describing thermal transport in frameworks. '*4,
        'https://arxiv.org/abs/2601.12345', 'preprint_abstract', '2026-10-22T00:00:00Z', 'arxiv', '2601.12345')


def configuration(**overrides):
    return {'web_enrichment': {'cache_path': 'cache.sqlite3', **overrides}, 'performance': {'ranking_batch_size': 10}}


def refine(entries, profile, llm, **kwargs):
    return [replace(paper(entry.title, 'low', 0.1), entry=entry, evidence=kwargs['evidence_by_index'][i])
            for i, entry in enumerate(entries)]


def test_verified_evidence_can_downgrade_without_touching_original_or_low_papers(tmp_path, monkeypatch):
    calls=[]
    monkeypatch.setattr(module, 'acquire_evidence', lambda entry,*args: calls.append(entry.title) or evidence())
    monkeypatch.setattr(module, 'rank_papers', refine)
    original=[paper('High paper title', 'high', .9), paper('Medium paper title', 'medium', .5), paper('Low paper title', 'low', .2)]
    updated=module.enrich_ranked_papers(original, InterestProfile(), object(), configuration(),base_dir=tmp_path,client=object())
    assert set(calls)=={'High paper title','Medium paper title'}
    assert all(p.relevance=='low' for p in updated)
    assert original[0].relevance=='high' and original[0].evidence is None
    assert all(p.entry.abstract=='original email' for p in updated)
    assert next(p for p in updated if p.entry.title.startswith('Low')) is original[-1]
    assert len(list(tmp_path.iterdir()))==1
    module.enrich_ranked_papers(original, InterestProfile(),object(),configuration(),base_dir=tmp_path,client=object())
    assert len(calls)==2  # verified abstracts are reused across runs


def test_optional_network_failure_is_not_negative_cached_or_core_failure(tmp_path, monkeypatch):
    calls=[];logs=[]
    def fail(*args):
        calls.append(1);raise EvidenceUnavailable('timeout')
    monkeypatch.setattr(module,'acquire_evidence',fail)
    original=[paper('High title with missing evidence', 'high', .9)]
    for _ in range(2):
        assert module.enrich_ranked_papers(original,InterestProfile(),object(),configuration(),base_dir=tmp_path,
            client=object(),detail=logs.append)==original
    assert len(calls)==2
    assert not any('回退本地规则' in log for log in logs)
    assert not list(tmp_path.glob('*-journal'))


def test_no_abstract_is_short_negative_cached(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(module,'acquire_evidence',lambda *args:calls.append(1))
    original=[paper('Absent abstract distinctive title','high',.9)]
    for _ in range(2):
        module.enrich_ranked_papers(original,InterestProfile(),object(),configuration(),base_dir=tmp_path,client=object())
    assert len(calls)==1


def test_interrupt_cleans_cache_transactions(tmp_path,monkeypatch):
    cancel=Event()
    def interrupt(*args):
        cancel.set();raise KeyboardInterrupt
    monkeypatch.setattr(module,'acquire_evidence',interrupt)
    with pytest.raises(KeyboardInterrupt):
        module.enrich_ranked_papers([paper('Interrupted title','high',.9)],InterestProfile(),object(),
            configuration(),base_dir=tmp_path,client=object(),cancel_event=cancel)
    assert not list(tmp_path.glob('*-journal'))
    assert not list(tmp_path.glob('*-wal'))


def test_refinement_failure_preserves_initial_ranking(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'acquire_evidence',lambda *args:evidence())
    def invalid(entries,*args,**kwargs):
        kwargs['event_callback']('回退本地规则');return []
    monkeypatch.setattr(module,'rank_papers',invalid)
    original=[paper('Distinctive original title','high',.9)]
    updated = module.enrich_ranked_papers(original,InterestProfile(),object(),configuration(),base_dir=tmp_path,client=object())
    assert updated[0].relevance == original[0].relevance
    assert updated[0].evidence == evidence()


def test_candidates_and_disabled_cache_are_bounded(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(module,'acquire_evidence',lambda entry,*args:calls.append(entry.title))
    original=[paper('High priority','high',.8),paper('Medium higher numeric score','medium',.9)]
    module.enrich_ranked_papers(original,InterestProfile(),object(),configuration(max_papers=1,cache_enabled=False),base_dir=tmp_path,client=object())
    assert calls==['High priority']
    assert not list(tmp_path.iterdir())


def test_cli_optional_enrichment_failure_still_finishes_and_marks_processed(tmp_path,monkeypatch):
    from copy import deepcopy
    from literature_digest import cli
    from literature_digest.config import DEFAULT_CONFIG
    from literature_digest.llm.offline_stub import OfflineStubClient
    from literature_digest.sample_data import sample_emails
    monkeypatch.chdir(tmp_path)
    (tmp_path/'credentials.json').write_text('{}')
    (tmp_path/'research_interests.md').write_text('COF thermal transport')
    config=deepcopy(DEFAULT_CONFIG)
    config['llm']['provider']='openai_compatible'
    config['llm']['openai_compatible']['base_url']='https://api.deepseek.com'
    config['parsing']['llm_structure_non_scholar']=False
    config['gmail']['mark_as_read']=True
    config['ui']['banner_enabled']=False
    config['progress']['enabled']=False
    monkeypatch.setattr(cli,'load_config',lambda path:config)
    monkeypatch.setattr(cli,'build_llm_client',lambda *args,**kwargs:OfflineStubClient())
    def read(self,**kwargs):
        self.last_result_size_estimate=1
        return sample_emails()[:1]
    marked=[]
    monkeypatch.setattr(cli.GmailClient,'fetch_unread_emails',read)
    monkeypatch.setattr(cli.GmailClient,'mark_as_read',lambda self,ids:marked.extend(ids))
    calls=[]
    def unavailable(*args,**kwargs):
        calls.append(1);raise RuntimeError('Optional stage failure')
    monkeypatch.setattr(cli,'enrich_ranked_papers',unavailable)
    assert cli.main(['--no-dry-run','--quiet','--date','2026-10-22'])==0
    assert calls==[1]
    assert marked
    assert (tmp_path/'data/paper_registry.json').exists()
    rendered=(tmp_path/'outputs/2026-10-22-digest.md').read_text()
    assert '本次 1 项 LLM 任务失败' not in rendered
    assert '中文摘要' in rendered


def test_unexpected_optional_refinement_error_does_not_cancel_run(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'acquire_evidence', lambda *args: evidence())
    class BrokenClient:
        def complete_json(self, *args, **kwargs):
            raise RuntimeError('unexpected optional failure')
    cancel = Event()
    original = [paper('Distinctive original title', 'high', .9)]
    updated = module.enrich_ranked_papers(original, InterestProfile(), BrokenClient(),
        configuration(), base_dir=tmp_path, client=object(), cancel_event=cancel)
    assert updated[0].relevance == original[0].relevance
    assert updated[0].evidence == evidence()
    assert not cancel.is_set()


def test_optional_task_still_observes_parent_cancellation():
    parent = Event()
    child = module._OptionalTaskCancel(parent)
    assert not child.is_set()
    parent.set()
    assert child.is_set()


def test_repository_abstract_cache_is_reusable():
    from dataclasses import asdict
    item = replace(evidence(), source_kind='repository_abstract')
    assert module._cached_evidence({'status': 'verified', 'evidence': asdict(item)}) == item


def test_acquisition_receives_per_paper_deadline(tmp_path, monkeypatch):
    from literature_digest.llm.base import current_llm_deadline
    from time import perf_counter
    remaining = []
    def acquire(*args):
        remaining.append(current_llm_deadline() - perf_counter())
    monkeypatch.setattr(module, 'acquire_evidence', acquire)
    module.enrich_ranked_papers([paper('Bounded paper', 'high', .9)], InterestProfile(), object(),
        configuration(paper_budget_seconds=2,cache_enabled=False), base_dir=tmp_path,client=object())
    assert 0 < remaining[0] <= 2


def test_old_negative_cache_does_not_hide_new_source_strategy(tmp_path, monkeypatch):
    from literature_digest.evidence_cache import EvidenceCache
    original = [paper('Retry old missing source', 'high', .9)]
    with EvidenceCache(tmp_path/'cache.sqlite3') as cache:
        cache.put(module.evidence_key(original[0].entry), {'status': 'missing'}, negative=True)
    calls = []
    monkeypatch.setattr(module, 'acquire_evidence', lambda *args: calls.append(1))
    module.enrich_ranked_papers(original, InterestProfile(), object(), configuration(), base_dir=tmp_path,client=object())
    assert calls == [1]


def test_expanded_budget_and_search_timeout_are_wired(tmp_path, monkeypatch):
    from literature_digest.config import DEFAULT_CONFIG
    captured = {}
    def client(**kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr(module, 'WebEvidenceClient', client)
    monkeypatch.setattr(module, 'acquire_evidence', lambda *args: None)
    module.enrich_ranked_papers([paper('Budget test', 'high', .9)], InterestProfile(), object(),
        DEFAULT_CONFIG, base_dir=tmp_path)
    assert captured['budget_seconds'] == 360
    assert captured['timeout_seconds'] == 40
    assert captured['search_timeout_seconds'] == 12
    assert captured['max_requests'] == 80
    assert captured['max_retries'] == 0
    assert DEFAULT_CONFIG['performance']['run_timeout_seconds'] == 900


def test_fetch_404_is_not_negative_cached_in_real_acquisition(tmp_path):
    class UnavailableSource:
        def __init__(self):
            self.fetches = 0
        def search(self, query):
            return []
        def fetch(self, url):
            self.fetches += 1
            raise EvidenceUnavailable('http_404')
    client = UnavailableSource()
    original = [paper('Missing fetch does not prove missing abstract', 'high', .9)]
    for _ in range(2):
        assert module.enrich_ranked_papers(original, InterestProfile(), object(), configuration(),
            base_dir=tmp_path, client=client) == original
    assert client.fetches == 2
