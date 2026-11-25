from __future__ import annotations

import sys
from types import ModuleType

import pytest

from literature_digest.gmail_client import GMAIL_SCOPES, GmailAuthenticationError, GmailConnectionError, GmailClient


def test_invalid_grant_refresh_starts_new_browser_authorization(tmp_path, monkeypatch):
    _clear_proxy_env(monkeypatch)

    class FakeRefreshError(Exception):
        pass

    class ExpiredCredentials:
        valid = False
        expired = True
        refresh_token = "refresh-token"

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            captured["token_path"] = path
            captured["load_scopes"] = scopes
            return cls()

        def refresh(self, request):
            raise FakeRefreshError("invalid_grant: Token has been expired or revoked.")

    class FreshCredentials:
        valid = True
        expired = False
        refresh_token = "fresh-refresh-token"

        def to_json(self):
            return '{"authorized": true}'

    class FakeInstalledAppFlow:
        @classmethod
        def from_client_secrets_file(cls, path, scopes):
            captured["credentials_path"] = path
            captured["flow_scopes"] = scopes
            return cls()

        def run_local_server(self, port):
            captured["port"] = port
            return FreshCredentials()

    captured = {}
    service = object()

    def fake_build(api_name, version, **kwargs):
        captured["api_name"] = api_name
        captured["version"] = version
        captured["http"] = kwargs["http"]
        return service

    _install_fake_google_modules(
        monkeypatch,
        credentials_cls=ExpiredCredentials,
        flow_cls=FakeInstalledAppFlow,
        refresh_error_cls=FakeRefreshError,
        build_fn=fake_build,
    )
    (tmp_path / "token.json").write_text("stale-token", encoding="utf-8")
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")

    client = GmailClient(_config(), base_dir=tmp_path)

    assert client._get_service() is service
    assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"authorized": true}'
    assert captured["load_scopes"] == GMAIL_SCOPES
    assert captured["flow_scopes"] == GMAIL_SCOPES
    assert captured["port"] == 0
    assert captured["api_name"] == "gmail"
    assert captured["version"] == "v1"
    assert isinstance(captured["http"].credentials, FreshCredentials)
    assert captured["http"].http.timeout == 30
    assert captured["http"].http.proxy_info is None


def test_gmail_service_uses_proxy_from_environment(tmp_path, monkeypatch):
    class ValidCredentials:
        valid = True
        expired = False
        refresh_token = "refresh-token"

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            return cls()

    captured = {}

    def fake_build(api_name, version, **kwargs):
        captured["http"] = kwargs["http"]
        return object()

    _install_fake_google_modules(
        monkeypatch,
        credentials_cls=ValidCredentials,
        flow_cls=object,
        refresh_error_cls=Exception,
        build_fn=fake_build,
    )
    monkeypatch.setenv("CODEX_PROXY_URL", "http://127.0.0.1:7897")
    monkeypatch.setenv("CODEX_NO_PROXY", "localhost,127.0.0.1")
    (tmp_path / "token.json").write_text("token", encoding="utf-8")

    GmailClient(_config(), base_dir=tmp_path)._get_service()

    assert captured["http"].http.proxy_info == {
        "url": "http://127.0.0.1:7897",
        "method": "https",
        "noproxy": "localhost,127.0.0.1",
    }


def test_non_invalid_refresh_error_is_not_silently_reauthorized(tmp_path, monkeypatch):
    class FakeRefreshError(Exception):
        pass

    class ExpiredCredentials:
        valid = False
        expired = True
        refresh_token = "refresh-token"

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            return cls()

        def refresh(self, request):
            raise FakeRefreshError("temporarily_unavailable")

    class FakeInstalledAppFlow:
        @classmethod
        def from_client_secrets_file(cls, path, scopes):  # pragma: no cover - must not be called
            raise AssertionError("OAuth flow should not start for transient refresh errors")

    _install_fake_google_modules(
        monkeypatch,
        credentials_cls=ExpiredCredentials,
        flow_cls=FakeInstalledAppFlow,
        refresh_error_cls=FakeRefreshError,
        build_fn=lambda *args, **kwargs: object(),
    )
    (tmp_path / "token.json").write_text("stale-token", encoding="utf-8")
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")

    client = GmailClient(_config(), base_dir=tmp_path)

    with pytest.raises(GmailAuthenticationError, match="token refresh failed"):
        client._get_service()


def test_fetch_unread_timeout_has_actionable_error(tmp_path, monkeypatch):
    class ValidCredentials:
        valid = True
        expired = False
        refresh_token = "refresh-token"

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            return cls()

    class TimeoutRequest:
        def execute(self):
            raise TimeoutError("timed out")

    class FakeMessages:
        def list(self, **kwargs):
            return TimeoutRequest()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    _install_fake_google_modules(
        monkeypatch,
        credentials_cls=ValidCredentials,
        flow_cls=object,
        refresh_error_cls=Exception,
        build_fn=lambda *args, **kwargs: FakeService(),
    )
    (tmp_path / "token.json").write_text("token", encoding="utf-8")

    client = GmailClient(_config(), base_dir=tmp_path)

    with pytest.raises(GmailConnectionError, match="文献 --dry-run --sample"):
        client.fetch_unread_emails(max_results=1)


def test_fetch_unread_exposes_gmail_result_size_estimate(tmp_path):
    class ListRequest:
        def execute(self):
            return {"messages": [], "resultSizeEstimate": 137}

    class FakeMessages:
        def list(self, **kwargs):
            return ListRequest()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    client = GmailClient(_config(), base_dir=tmp_path)
    client._service = FakeService()

    emails = client.fetch_unread_emails(max_results=100)

    assert emails == []
    assert client.last_result_size_estimate == 137


def test_reauthorize_backs_up_existing_token_and_writes_new_token(tmp_path, monkeypatch):
    class FreshCredentials:
        def to_json(self):
            return '{"authorized": true}'

    class FakeInstalledAppFlow:
        @classmethod
        def from_client_secrets_file(cls, path, scopes):
            captured["credentials_path"] = path
            captured["scopes"] = scopes
            return cls()

        def run_local_server(self, port):
            captured["port"] = port
            return FreshCredentials()

    captured = {}
    _install_fake_google_modules(
        monkeypatch,
        credentials_cls=object,
        flow_cls=FakeInstalledAppFlow,
        refresh_error_cls=Exception,
        build_fn=lambda *args, **kwargs: object(),
    )
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / "token.json").write_text("old-token", encoding="utf-8")

    token_path = GmailClient(_config(), base_dir=tmp_path).reauthorize()

    assert token_path == tmp_path / "token.json"
    assert token_path.read_text(encoding="utf-8") == '{"authorized": true}'
    # exactly one backup, kept inside the project's data folder (not next to token.json)
    assert not list(tmp_path.glob("token.backup*.json"))
    backup = tmp_path / "data" / "config_backups" / "token.backup.json"
    assert backup.read_text(encoding="utf-8") == "old-token"
    assert captured["credentials_path"] == str(tmp_path / "credentials.json")
    assert captured["scopes"] == GMAIL_SCOPES
    assert captured["port"] == 0


def test_fetch_emails_uses_batch_request_and_preserves_order(tmp_path):
    class MessageRequest:
        def __init__(self, message_id):
            self.message_id = message_id

    class FakeMessages:
        def get(self, **kwargs):
            return MessageRequest(kwargs["id"])

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeBatch:
        def __init__(self, callback):
            self.callback = callback
            self.requests = []

        def add(self, request, request_id):
            self.requests.append((request, request_id))

        def execute(self):
            for request, request_id in reversed(self.requests):
                self.callback(
                    request_id,
                    {
                        "id": request.message_id,
                        "threadId": f"thread-{request.message_id}",
                        "labelIds": ["UNREAD"],
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": f"subject-{request.message_id}"},
                                {"name": "From", "value": "journal@example.org"},
                            ]
                        },
                    },
                    None,
                )

    class FakeService:
        def users(self):
            return FakeUsers()

        def new_batch_http_request(self, callback):
            return FakeBatch(callback)

    client = GmailClient(_config(), base_dir=tmp_path)
    client._service = FakeService()

    emails = client._fetch_emails(["a", "b", "c"])

    assert [email.id for email in emails] == ["a", "b", "c"]
    assert [email.subject for email in emails] == ["subject-a", "subject-b", "subject-c"]


def test_fetch_emails_retries_only_transient_batch_failures(tmp_path):
    class FakeResponse(dict):
        status = 429

    class TransientError(Exception):
        resp = FakeResponse()
        reason = "Too many concurrent requests for user."

    class MessageRequest:
        def __init__(self, message_id):
            self.message_id = message_id

    class FakeMessages:
        def get(self, **kwargs):
            return MessageRequest(kwargs["id"])

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeBatch:
        def __init__(self, service, callback):
            self.service = service
            self.callback = callback
            self.requests = []

        def add(self, request, request_id):
            self.requests.append((request, request_id))

        def execute(self):
            self.service.batch_ids.append([request_id for _, request_id in self.requests])
            for request, request_id in self.requests:
                if request_id == "b" and len(self.service.batch_ids) == 1:
                    self.callback(request_id, None, TransientError())
                else:
                    self.callback(request_id, _message_payload(request.message_id), None)

    class FakeService:
        def __init__(self):
            self.batch_ids = []

        def users(self):
            return FakeUsers()

        def new_batch_http_request(self, callback):
            return FakeBatch(self, callback)

    config = _config()
    config["gmail"].update(
        {
            "batch_fetch_size": 3,
            "batch_fetch_max_retries": 2,
            "batch_fetch_retry_backoff_seconds": 0,
        }
    )
    service = FakeService()
    client = GmailClient(config, base_dir=tmp_path)
    client._service = service

    emails = client._fetch_emails(["a", "b", "c"])

    assert [email.id for email in emails] == ["a", "b", "c"]
    assert service.batch_ids == [["a", "b", "c"], ["b"]]


def test_fetch_emails_does_not_retry_permanent_batch_failure(tmp_path):
    class FakeResponse(dict):
        status = 404

    class PermanentError(Exception):
        resp = FakeResponse()
        reason = "Message not found."

    class MessageRequest:
        pass

    class FakeMessages:
        def get(self, **kwargs):
            return MessageRequest()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeBatch:
        def __init__(self, callback):
            self.callback = callback
            self.requests = []

        def add(self, request, request_id):
            self.requests.append(request_id)

        def execute(self):
            for request_id in self.requests:
                self.callback(request_id, None, PermanentError())

    class FakeService:
        def users(self):
            return FakeUsers()

        def new_batch_http_request(self, callback):
            return FakeBatch(callback)

    config = _config()
    config["gmail"].update(
        {
            "batch_fetch_size": 2,
            "batch_fetch_max_retries": 3,
            "batch_fetch_retry_backoff_seconds": 0,
        }
    )
    client = GmailClient(config, base_dir=tmp_path)
    client._service = FakeService()

    with pytest.raises(GmailConnectionError, match="HTTP 404: Message not found"):
        client._fetch_emails(["a", "b"])


def test_mark_as_read_uses_batch_modify(tmp_path):
    captured = []

    class Request:
        def execute(self):
            return {}

    class FakeMessages:
        def batchModify(self, **kwargs):
            captured.append(kwargs["body"])
            return Request()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    config = _config()
    config["gmail"]["batch_modify_size"] = 2
    client = GmailClient(config, base_dir=tmp_path)
    client._service = FakeService()

    client.mark_as_read(["a", "b", "c"])

    assert captured == [
        {"ids": ["a", "b"], "removeLabelIds": ["UNREAD"]},
        {"ids": ["c"], "removeLabelIds": ["UNREAD"]},
    ]


def _message_payload(message_id):
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "labelIds": ["UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": f"subject-{message_id}"},
                {"name": "From", "value": "journal@example.org"},
            ]
        },
    }


def _config():
    return {
        "gmail": {
            "credentials_path": "credentials.json",
            "token_path": "token.json",
            "request_timeout_seconds": 30,
        },
        "parsing": {},
    }


def _install_fake_google_modules(
    monkeypatch,
    *,
    credentials_cls,
    flow_cls,
    refresh_error_cls,
    build_fn,
) -> None:
    google_module = _package("google")
    auth_module = _package("google.auth")
    transport_module = _package("google.auth.transport")
    requests_module = ModuleType("google.auth.transport.requests")
    exceptions_module = ModuleType("google.auth.exceptions")
    oauth2_module = _package("google.oauth2")
    credentials_module = ModuleType("google.oauth2.credentials")
    oauthlib_module = _package("google_auth_oauthlib")
    auth_httplib2_module = ModuleType("google_auth_httplib2")
    flow_module = ModuleType("google_auth_oauthlib.flow")
    api_client_module = _package("googleapiclient")
    discovery_module = ModuleType("googleapiclient.discovery")
    httplib2_module = ModuleType("httplib2")

    class FakeRequest:
        pass

    class FakeAuthorizedHttp:
        def __init__(self, credentials, http):
            self.credentials = credentials
            self.http = http

    class FakeHttp:
        def __init__(self, timeout=None, proxy_info=None):
            self.timeout = timeout
            self.proxy_info = proxy_info

    def fake_proxy_info_from_url(url, method="http", noproxy=None):
        return {"url": url, "method": method, "noproxy": noproxy}

    requests_module.Request = FakeRequest
    exceptions_module.RefreshError = refresh_error_cls
    credentials_module.Credentials = credentials_cls
    auth_httplib2_module.AuthorizedHttp = FakeAuthorizedHttp
    flow_module.InstalledAppFlow = flow_cls
    discovery_module.build = build_fn
    httplib2_module.Http = FakeHttp
    httplib2_module.proxy_info_from_url = fake_proxy_info_from_url

    google_module.auth = auth_module
    auth_module.transport = transport_module
    auth_module.exceptions = exceptions_module
    transport_module.requests = requests_module
    google_module.oauth2 = oauth2_module
    oauth2_module.credentials = credentials_module
    oauthlib_module.flow = flow_module
    api_client_module.discovery = discovery_module

    for module in (
        google_module,
        auth_module,
        transport_module,
        requests_module,
        exceptions_module,
        oauth2_module,
        credentials_module,
        auth_httplib2_module,
        oauthlib_module,
        flow_module,
        api_client_module,
        discovery_module,
        httplib2_module,
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)


def _package(name: str) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = []
    return module


def _clear_proxy_env(monkeypatch) -> None:
    for name in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
        "no_proxy",
        "NO_PROXY",
        "CODEX_PROXY_URL",
        "CODEX_ALL_PROXY_URL",
        "CODEX_NO_PROXY",
    ):
        monkeypatch.delenv(name, raising=False)
