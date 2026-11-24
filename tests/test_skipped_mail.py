from copy import deepcopy

import pytest

from literature_digest import cli
from literature_digest.config import DEFAULT_CONFIG
from literature_digest.llm.offline_stub import OfflineStubClient
from literature_digest.models import EmailMessage
from literature_digest.sample_data import sample_emails


def _promo():
    return EmailMessage(id="promo-1", thread_id="t", subject="Big discount offer",
                        sender="shop@example.com", date=None, text="Coupon deal. Buy now. Unsubscribe.")


@pytest.mark.parametrize("enabled", [False, True])
def test_skipped_mail_is_marked_read_only_when_enabled(tmp_path, monkeypatch, enabled):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "credentials.json").write_text("{}")
    (tmp_path / "research_interests.md").write_text("COF thermal transport")
    config = deepcopy(DEFAULT_CONFIG)
    config["parsing"]["llm_structure_non_scholar"] = False
    config["gmail"]["mark_as_read"] = True
    config["filtering"]["mark_skipped_as_read"] = enabled
    config["web_enrichment"]["enabled"] = False
    config["ui"]["banner_enabled"] = False
    config["progress"]["enabled"] = False
    monkeypatch.setattr(cli, "load_config", lambda path: config)
    monkeypatch.setattr(cli, "build_llm_client", lambda *args, **kwargs: OfflineStubClient())
    academic = sample_emails()[:1]

    def read(self, **kwargs):
        self.last_result_size_estimate = 2
        return academic + [_promo()]

    marked = []
    monkeypatch.setattr(cli.GmailClient, "fetch_unread_emails", read)
    monkeypatch.setattr(cli.GmailClient, "mark_as_read", lambda self, ids: marked.extend(ids))

    assert cli.main(["--no-dry-run", "--quiet", "--date", "2026-11-24"]) == 0
    assert academic[0].id in marked
    assert ("promo-1" in marked) is enabled
