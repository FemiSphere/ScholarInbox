"""Recovered item validation must not suppress normal read-state/index updates."""
from copy import deepcopy
import json

from literature_digest import cli
from literature_digest.config import DEFAULT_CONFIG
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.sample_data import sample_emails


def test_recovered_translation_can_complete_normal_processing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'credentials.json').write_text('{}')
    (tmp_path/'research_interests.md').write_text('COF thermal transport')
    config = deepcopy(DEFAULT_CONFIG)
    config['llm']['provider'] = 'offline_stub'
    config['parsing']['llm_structure_non_scholar'] = False
    config['gmail']['mark_as_read'] = True
    config['ui']['banner_enabled'] = False
    config['progress']['enabled'] = False
    calls = []
    class FaultOnce(OfflineStubClient):
        def complete_json(self, prompt):
            result = super().complete_json(prompt)
            if 'TRANSLATE_PAPERS_JSON' in prompt:
                calls.append(len(result['papers']))
                if len(calls) == 1:
                    result['papers'][0]['summary_zh'] = ''
            return result
    monkeypatch.setattr(cli, 'load_config', lambda path: config)
    monkeypatch.setattr(cli, 'build_llm_client', lambda *args, **kwargs: FaultOnce())
    def read(self, **kwargs):
        self.last_result_size_estimate = 1
        return sample_emails()[:1]
    marked = []
    monkeypatch.setattr(cli.GmailClient, 'fetch_unread_emails', read)
    monkeypatch.setattr(cli.GmailClient, 'mark_as_read', lambda self, ids: marked.extend(ids))
    assert cli.main(['--no-dry-run', '--quiet', '--date', '2026-10-31']) == 0
    assert calls and calls[-1] == 1 and len(calls) == 2
    assert marked
    assert (tmp_path/'data/paper_registry.json').exists()
    assert not list((tmp_path/'outputs').glob('*.md'))
    output=(tmp_path/'outputs/2026-10-31-digest.html').read_text()
    assert '项 LLM 任务失败' not in output
