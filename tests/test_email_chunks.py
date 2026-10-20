import json
import re
from threading import Event

import pytest

from literature_digest.email_chunks import build_email_chunks
from literature_digest.llm.base import LLMError, LLMOutputTruncatedError
from literature_digest.models import EmailMessage
from literature_digest.parsers import parse_emails


def mail(html):
    return EmailMessage("weekly", "thread", "Weekly materials", "journal@example.org", None, html=html)


def article(index, excerpt=""):
    return (f'<article><img src="https://example.org/figure-{index}.png">'
            f'<a href="https://example.org/paper-{index}">Thermal transport framework study number {index}</a>'
            f'<p>ABSTRACT_{index} {excerpt}</p></article>')


class Extraction:
    def __init__(self, truncate_over=None, always_fail=False, cancel=None):
        self.prompts = []
        self.truncate_over = truncate_over
        self.always_fail = always_fail
        self.cancel = cancel

    def complete_json(self, prompt):
        self.prompts.append(prompt)
        links = json.loads(prompt.split("CANDIDATE_LINKS_JSON:\n")[1].split("\n\nCANDIDATE_IMAGES_JSON:")[0])
        images = json.loads(prompt.split("CANDIDATE_IMAGES_JSON:\n")[1].split("\n\nEMAIL_TEXT:")[0])
        if self.cancel:
            self.cancel.set()
        if self.always_fail or self.truncate_over is not None and len(links) > self.truncate_over:
            raise LLMOutputTruncatedError()
        papers = []
        for link in links:
            match = re.search(r"paper-(\d+)$", link["url"])
            if not match:
                continue
            index = int(match[1])
            matching_image = next((image["index"] for image in images if f"figure-{index}.png" in image["url"]), None)
            papers.append({"title": link["text"], "url": link["url"], "snippet": f"ABSTRACT_{index}", "image_index": matching_image})
        return {"papers": papers}


def test_full_tail_many_links_images_are_partitioned_and_indexes_local():
    client = Extraction()
    entries = parse_emails([mail("".join(article(i, "long abstract " * 100) for i in range(20)))],
                           llm=client, llm_structure_non_scholar=True, llm_text_max_chars=2400,
                           llm_max_links=2, llm_max_images=2, llm_max_chunk_items=2)
    assert len(entries) == 20
    assert entries[-1].url.endswith("paper-19")
    assert any("ABSTRACT_19" in prompt for prompt in client.prompts)
    for entry in entries:
        number = entry.url.rsplit("-", 1)[1]
        assert entry.image_paths == [f"https://example.org/figure-{number}.png"]
    for prompt in client.prompts:
        assert len(prompt.split("EMAIL_TEXT:\n")[1]) <= 2400


def test_truncated_chunk_splits_preserving_success_and_caches_only_final_success(tmp_path):
    client = Extraction(truncate_over=1)
    events = []
    options = dict(llm=client, llm_structure_non_scholar=True, cache_dir=tmp_path, event_callback=events.append)
    entries = parse_emails([mail("".join(article(i) for i in range(4)))], **options)
    assert len(entries) == 4
    assert len(client.prompts) == 7
    assert any("分块拆分" in event for event in events)
    assert not any("回退" in event for event in events)
    assert list(tmp_path.glob("*.json"))
    parse_emails([mail("".join(article(i) for i in range(4)))], **options)
    assert len(client.prompts) == 7


def test_request_cap_bounded_failed_regions_not_cached(tmp_path):
    client = Extraction(always_fail=True)
    events = []
    entries = parse_emails([mail("".join(article(i) for i in range(6)))], llm=client,
                           llm_structure_non_scholar=True, cache_dir=tmp_path,
                           llm_max_requests_per_email=3, event_callback=events.append)
    assert len(client.prompts) == 3
    assert len(entries) == 6
    assert any("request_limit" in event for event in events)
    assert not list(tmp_path.glob("*.json"))


def test_unknown_format_no_title_anchor_still_sends_full_tail_to_ai():
    client = Extraction()
    html = "".join(f"<div>Weekly result {i} " + "opaque source content " * 80 + "</div>" for i in range(20))
    entries = parse_emails([mail(html)], llm=client, llm_structure_non_scholar=True,
                           llm_text_max_chars=2000, llm_max_requests_per_email=100)
    assert entries == []  # Successful empty responses never trigger whole-email heuristics.
    assert any("Weekly result 19" in prompt for prompt in client.prompts)
    assert len(client.prompts) > 1


def test_zero_limits_disable_arrays_but_retain_ordered_source():
    chunks = build_email_chunks(html=article(3), text="", image_paths=[],
        is_article=lambda title, href: True, accept_link=lambda *args: True,
        accept_image=lambda src: True, text_max_chars=1000, max_links=0, max_images=0, max_items=8)
    assert all(not chunk.links and not chunk.images for chunk in chunks)
    assert "paper-3" in "".join(chunk.text for chunk in chunks)
    assert "figure-3" in "".join(chunk.text for chunk in chunks)


def test_cancellation_between_chunks_stops_new_calls():
    cancel = Event()
    client = Extraction(cancel=cancel)
    with pytest.raises(KeyboardInterrupt):
        parse_emails([mail(article(1) + article(2))], llm=client, llm_structure_non_scholar=True,
                     llm_max_chunk_items=1, cancel_event=cancel)
    assert len(client.prompts) == 1


def test_invalid_payload_is_split_and_valid_empty_is_preserved():
    class InvalidFirst(Extraction):
        def complete_json(self, prompt):
            if not self.prompts:
                self.prompts.append(prompt)
                return {"papers": None}
            return super().complete_json(prompt)
    client = InvalidFirst()
    entries = parse_emails([mail(article(1) + article(2))], llm=client, llm_structure_non_scholar=True)
    assert len(entries) == 2


def test_oversized_article_keeps_own_title_and_image_context_on_tail():
    client = Extraction()
    entries = parse_emails([mail(article(7, "source details " * 2000 + " END_OF_LONG_ABSTRACT"))],
                           llm=client, llm_structure_non_scholar=True,
                           llm_text_max_chars=1500, llm_max_requests_per_email=100)
    tail = [prompt for prompt in client.prompts if "END_OF_LONG_ABSTRACT" in prompt]
    assert tail
    assert "paper-7" in tail[-1].split("CANDIDATE_LINKS_JSON:")[1].split("CANDIDATE_IMAGES_JSON:")[0]
    assert "figure-7.png" in tail[-1].split("CANDIDATE_IMAGES_JSON:")[1].split("EMAIL_TEXT:")[0]
    assert len(entries) == 1
    assert all(len(prompt.split("EMAIL_TEXT:\n")[1]) <= 1500 for prompt in client.prompts)


def test_successful_chunks_preserved_when_other_chunk_fails(tmp_path):
    class OneFails(Extraction):
        def complete_json(self, prompt):
            if "paper-2" in prompt:
                self.prompts.append(prompt)
                raise LLMError("not for logs", code="timeout")
            return super().complete_json(prompt)
    client = OneFails()
    results = parse_emails([mail(article(1) + article(2))], llm=client, llm_structure_non_scholar=True,
                          llm_max_chunk_items=1, cache_dir=tmp_path)
    assert len(results) == 2
    assert results[0].abstract == "ABSTRACT_1"
    assert not list(tmp_path.glob("*.json"))


def test_zero_email_time_budget_skips_api_and_cannot_cache_degraded(tmp_path):
    client = Extraction()
    events = []
    results = parse_emails([mail(article(1))], llm=client, llm_structure_non_scholar=True,
                          llm_email_budget_seconds=0, cache_dir=tmp_path, event_callback=events.append)
    assert len(results) == 1
    assert not client.prompts
    assert any("budget_exhausted" in event for event in events)
    assert not list(tmp_path.glob("*.json"))


def test_nested_layout_rows_do_not_consume_article_item_budget():
    html = "".join('<table><tr><td>' + article(i) + '</td></tr><tr><td>layout spacer</td></tr></table>'
                   for i in range(12))
    chunks = build_email_chunks(html=html, text="", image_paths=[],
        is_article=lambda title, href: "paper-" in href, accept_link=lambda *args: True,
        accept_image=lambda src: True, text_max_chars=12000, max_links=50, max_images=20, max_items=8)
    assert len(chunks) == 2
    assert sum(len(chunk.links) for chunk in chunks) == 12


def test_image_only_article_link_retains_href_alt_and_image():
    from literature_digest.parsers import _is_likely_title
    chunks = build_email_chunks(html='<a href="https://doi.org/10.1000/example"><img '
        'src="https://example.org/fig.png" alt="Thermal transport framework study"></a>',
        text="", image_paths=[], is_article=_is_likely_title, accept_link=lambda *args: True,
        accept_image=lambda src: True, text_max_chars=12000, max_links=50, max_images=20, max_items=8)
    assert len(chunks) == 1
    assert chunks[0].links == [("https://doi.org/10.1000/example", "Thermal transport framework study")]
    assert chunks[0].images == ["https://example.org/fig.png"]
    assert "Thermal transport framework study" in chunks[0].text


def test_layout_row_pre_title_image_stays_with_its_article_across_chunk_boundary():
    html = "<table>" + "".join(f'<tr><td><img src="https://example.org/figure-{i}.png"></td>'
            f'<td><a href="https://example.org/paper-{i}">Thermal transport framework study number {i}</a>'
            f'<p>Article abstract {i}</p></td></tr>' for i in range(12)) + "</table>"
    client = Extraction()
    results = parse_emails([mail(html)], llm=client, llm_structure_non_scholar=True,
                          llm_max_chunk_items=8, llm_text_max_chars=12000)
    assert len(results) == 12
    assert len(client.prompts) == 2
    for result in results:
        number = result.url.rsplit("-", 1)[1]
        assert result.image_paths == [f"https://example.org/figure-{number}.png"]
    first_links = client.prompts[0].split("CANDIDATE_LINKS_JSON:")[1].split("CANDIDATE_IMAGES_JSON:")[0]
    first_images = client.prompts[0].split("CANDIDATE_IMAGES_JSON:")[1].split("EMAIL_TEXT:")[0]
    assert "paper-8" not in first_links
    assert "figure-8" not in first_images


def test_context_does_not_exceed_single_link_cap_for_pdf_atom():
    html = '<article><a href="https://example.org/paper-1">Thermal transport framework study number 1</a>'
    html += '<p>' + 'Long abstract content ' * 80 + '</p>'
    html += '<a href="https://example.org/paper-1.pdf">PDF</a></article>'
    from literature_digest.parsers import _is_likely_title
    chunks = build_email_chunks(html=html, text="", image_paths=[], is_article=_is_likely_title,
        accept_link=lambda *args: True, accept_image=lambda src: True,
        text_max_chars=600, max_links=1, max_images=1, max_items=8)
    assert all(len(chunk.links) <= 1 for chunk in chunks)
    assert all(len(chunk.text) <= 600 for chunk in chunks)
    assert any(any(url.endswith('.pdf') for url, title in chunk.links) for chunk in chunks)


def test_recursive_split_keeps_pre_title_row_images_with_article():
    html = '<table>' + ''.join(f'<tr><td><img src="https://example.org/figure-{i}.png"></td>'
           f'<td><a href="https://example.org/paper-{i}">Thermal transport framework study number {i}</a>'
           '<p>Article abstract</p></td></tr>' for i in range(4)) + '</table>'
    client = Extraction(truncate_over=1)
    results = parse_emails([mail(html)], llm=client, llm_structure_non_scholar=True)
    assert len(results) == 4
    for result in results:
        number = result.url.rsplit('-', 1)[1]
        assert result.image_paths == [f'https://example.org/figure-{number}.png']
