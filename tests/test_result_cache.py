from copy import deepcopy
import sqlite3

import pytest

from literature_digest import cli
from literature_digest.config import DEFAULT_CONFIG
from literature_digest.llm import LLMError
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.models import PaperEntry, RankedPaper
from literature_digest.result_cache import ResultCache, ResultCacheError, analysis_key, translation_key
from literature_digest.sample_data import sample_emails


def _paper(title="P", **flags):
    return RankedPaper(entry=PaperEntry(title=title), relevance="high", score=.9, title_zh="中文",
                       summary_zh="概述", reason_zh="理由", matched_topics=["COF"], **flags)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_stores_successful_results_only_and_expires(tmp_path):
    clock = Clock()
    cache = ResultCache(tmp_path / "r.sqlite3", ttl_days=1, clock=clock)
    good, bad = _paper("good"), _paper("bad", fallback=True)
    cache.put_analyses([("a:good", good), ("a:bad", bad)])
    cache.put_translations([("t:good", _paper("good", translated=True)), ("t:raw", _paper("raw"))])
    assert cache.get_analysis("a:good")["relevance"] == "high"
    assert cache.get_analysis("a:bad") is None
    assert cache.get_translation("t:good")["title_zh"] == "中文"
    assert cache.get_translation("t:raw") is None
    clock.now += 2 * 86400
    assert cache.get_analysis("a:good") is None


def test_capacity_and_clear(tmp_path):
    cache = ResultCache(tmp_path / "r.sqlite3", max_entries=2)
    cache.put_analyses([(f"a:{i}", _paper(str(i))) for i in range(3)])
    count = sqlite3.connect(tmp_path / "r.sqlite3").execute("SELECT COUNT(*) FROM results").fetchone()[0]
    assert count == 2
    cache.clear()
    assert cache.get_analysis("a:2") is None


def test_unrecognized_database_is_left_alone(tmp_path):
    path = tmp_path / "r.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE mine (x)")
    connection.commit()
    connection.close()
    with pytest.raises(ResultCacheError):
        ResultCache(path)
    assert sqlite3.connect(path).execute("SELECT name FROM sqlite_master").fetchall() == [("mine",)]


def test_keys_change_with_inputs():
    entry = PaperEntry(title="A")
    assert analysis_key(entry, "p1", "m") != analysis_key(entry, "p2", "m")
    assert translation_key(_paper("A"), "m") != translation_key(_paper("B"), "m")


# ---------------------------------------------------------------- CLI behaviour

def _run(tmp_path, monkeypatch, client, *, limits=None, dry_run=False):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "credentials.json").write_text("{}")
    (tmp_path / "research_interests.md").write_text("COF thermal transport")
    config = deepcopy(DEFAULT_CONFIG)
    config["llm"]["provider"] = "offline_stub"
    config["parsing"]["llm_structure_non_scholar"] = False
    config["gmail"]["mark_as_read"] = True
    config["ui"]["banner_enabled"] = False
    config["progress"]["enabled"] = False
    config["digest"].update(limits or {})
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "build_llm_client", lambda *args, **kwargs: client)

    def read(self, **kwargs):
        self.last_result_size_estimate = 2
        return sample_emails()[:2]

    marked = []
    monkeypatch.setattr(cli.GmailClient, "fetch_unread_emails", read)
    monkeypatch.setattr(cli.GmailClient, "mark_as_read", lambda self, ids: marked.extend(ids))
    flag = "--dry-run" if dry_run else "--no-dry-run"
    code = cli.main([flag, "--quiet", "--date", "2026-11-25"])
    return code, marked


class Recorder(OfflineStubClient):
    def __init__(self, fail_translation=False, fail_ranking=False):
        self.translated_titles, self.ranked_titles = [], []
        self.fail_translation, self.fail_ranking = fail_translation, fail_ranking

    def complete_json(self, prompt):
        import json
        papers = json.loads(prompt.split("PAPERS_JSON:")[-1]) if "PAPERS_JSON:" in prompt else []
        if "TRANSLATE_PAPERS_JSON" in prompt:
            self.translated_titles += [paper["title"] for paper in papers]
            if self.fail_translation:
                raise LLMError("offline", code="network_error")
        if "RANK_PAPERS_JSON" in prompt:
            self.ranked_titles += [paper["title"] for paper in papers]
            if self.fail_ranking:
                raise LLMError("offline", code="network_error")
        return super().complete_json(prompt)


def test_only_displayed_papers_are_translated(tmp_path, monkeypatch):
    client = Recorder()
    code, _ = _run(tmp_path, monkeypatch, client, limits={"max_high_relevance": 1, "max_medium_relevance": 0})
    assert code == 0
    html = (tmp_path / "outputs/2026-11-25-digest.html").read_text(encoding="utf-8")
    assert len(client.ranked_titles) >= 3
    assert len(client.translated_titles) < len(client.ranked_titles)
    assert "未在本日报展示" in html


def test_translation_only_failure_still_marks_read_and_updates_registry(tmp_path, monkeypatch):
    code, marked = _run(tmp_path, monkeypatch, Recorder(fail_translation=True))
    assert code == 0
    assert marked
    assert (tmp_path / "data/paper_registry.json").exists()
    html = (tmp_path / "outputs/2026-11-25-digest.html").read_text(encoding="utf-8")
    assert "中文翻译未完整完成" in html and "评级不受影响" in html


def test_rerun_reuses_cached_results_and_successful_real_run_clears_cache(tmp_path, monkeypatch):
    # A dry run (like a run that ended in a core fallback) leaves results for the next attempt.
    first = Recorder()
    code, marked = _run(tmp_path, monkeypatch, first, dry_run=True)
    assert code == 0 and not marked
    cache_file = tmp_path / "data/cache/results.sqlite3"
    assert cache_file.exists()
    second = Recorder()
    code, marked = _run(tmp_path, monkeypatch, second)
    assert code == 0 and marked
    assert second.ranked_titles == [] and second.translated_titles == []
    count = sqlite3.connect(cache_file).execute("SELECT COUNT(*) FROM results").fetchone()[0]
    assert count == 0
