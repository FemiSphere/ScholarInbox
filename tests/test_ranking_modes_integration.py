import json
from pathlib import Path

from literature_digest.config import load_config
from literature_digest.llm.factory import build_llm_client
from literature_digest.models import InterestProfile, PaperEntry
from literature_digest.ranking import rank_papers
from literature_digest.telemetry import RunMetrics


def test_example_policy_reaches_real_ranking_and_translation_payloads(tmp_path, monkeypatch):
    example = Path(__file__).resolve().parents[1] / 'literature_digest/presets/deepseek.yaml'
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(f'llm:\n  config_path: "{example}"\n')
    config = load_config(config_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'offline-test-key')
    requests = []
    class Response:
        status = 200
        def __init__(self, item):
            self.item = item
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({'choices': [{'message': {'content': json.dumps({'papers': [self.item]})}, 'finish_reason': 'stop'}]}).encode()
    def fake_open(request, timeout):
        body = json.loads(request.data)
        requests.append(body)
        if body['messages'][0]['content'].startswith('RANK_PAPERS_JSON'):
            return Response({'index': 0, 'relevance': 'high', 'score': 0.9,
                'reason_zh': '涉及目标材料的热输运，依据邮件片段。', 'matched_topics': ['thermal transport']})
        return Response({'index': 0, 'title_zh': '共价有机框架的热输运', 'summary_zh': '邮件片段讨论热输运，信息有限。'})
    monkeypatch.setattr('urllib.request.urlopen', fake_open)
    client = build_llm_client(config, metrics=RunMetrics())
    papers = rank_papers([PaperEntry(title='Thermal transport in COFs', abstract='Source excerpt')],
        InterestProfile(summary_zh='COF热输运'), client, separate_translation=True)
    assert len(requests) == 2
    assert requests[0]['thinking']['type'] == 'enabled'
    assert requests[0]['reasoning_effort'] == 'high'
    assert requests[0]['max_tokens'] == 12000
    assert 'temperature' not in requests[0]
    assert requests[1]['thinking']['type'] == 'disabled'
    assert 'reasoning_effort' not in requests[1]
    assert requests[1]['temperature'] == 0.2
    assert papers[0].score == 0.9
    assert papers[0].title_zh == '共价有机框架的热输运'
