from threading import Event

import pytest

from literature_digest.concurrency import cooperative_map
from literature_digest.llm import LLMError
from literature_digest.models import EmailMessage
from literature_digest.parsers import parse_emails


def email():
    return EmailMessage(id="one", thread_id="t", subject="issue", sender="journal@example.org", date=None,
                        html='<a href="https://example.org/paper">Thermal transport in covalent organic frameworks</a>')


class Client:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def complete_json(self, prompt):
        self.calls += 1
        if self.fail:
            raise LLMError("secret-email-body-do-not-log")
        return {"papers": [{"title": "Thermal transport in covalent organic frameworks", "url": "https://example.org/paper"}]}


def test_cache_reuses_success_and_invalidates_for_content_and_model(tmp_path):
    client = Client()
    messages = []
    options = dict(llm=client, llm_structure_non_scholar=True, cache_dir=tmp_path, event_callback=messages.append)
    first = parse_emails([email()], cache_namespace="model-a", **options)
    second = parse_emails([email()], cache_namespace="model-a", **options)
    assert first == second
    assert client.calls == 1
    assert any("缓存命中" in message for message in messages)
    parse_emails([email()], cache_namespace="model-b", **options)
    changed = email()
    changed.html += "changed"
    parse_emails([changed], cache_namespace="model-b", **options)
    assert client.calls == 3


def test_fallback_is_visible_but_not_cached(tmp_path):
    client = Client(fail=True)
    messages = []
    options = dict(llm=client, llm_structure_non_scholar=True, cache_dir=tmp_path, event_callback=messages.append)
    assert len(parse_emails([email()], **options)) == 1
    parse_emails([email()], **options)
    assert client.calls == 2
    assert not list(tmp_path.glob("*.json"))
    assert any("LLMError" in message and "回退" in message for message in messages)
    assert all("secret-email-body" not in message for message in messages)


def test_corrupt_cache_is_recomputed(tmp_path):
    client = Client()
    options = dict(llm=client, llm_structure_non_scholar=True, cache_dir=tmp_path)
    parse_emails([email()], **options)
    next(tmp_path.glob("*.json")).write_text("broken")
    assert len(parse_emails([email()], **options)) == 1
    assert client.calls == 2


def test_parser_progress_for_cached_and_uncached_emails(tmp_path):
    completed = []
    options = dict(cache_dir=tmp_path, progress=lambda done, total: completed.append((done, total)))
    parse_emails([email()], **options)
    parse_emails([email()], **options)
    assert completed == [(1, 1), (1, 1)]


def test_cancel_prevents_any_work():
    cancel = Event()
    cancel.set()
    calls = []
    with pytest.raises(KeyboardInterrupt):
        cooperative_map(calls.append, range(3), max_workers=2, thread_name_prefix="test", cancel_event=cancel)
    assert not calls


def test_interrupt_cancels_queue_and_does_not_wait_for_running_work():
    started = Event()
    release = Event()
    cancel = Event()

    def work(index):
        if index == 0:
            assert started.wait(1)
            raise KeyboardInterrupt
        if index == 1:
            started.set()
            assert release.wait(2)
        return index

    try:
        with pytest.raises(KeyboardInterrupt):
            cooperative_map(work, range(10), max_workers=2, thread_name_prefix="test", cancel_event=cancel)
        assert cancel.is_set()
        assert not release.is_set()  # Main thread returned while the worker is still blocked.
    finally:
        release.set()
