from __future__ import annotations

import sys
from types import ModuleType

import pytest

from literature_digest.gmail_client import GMAIL_SCOPES, GmailAuthenticationError, GmailClient


def test_invalid_grant_refresh_starts_new_browser_authorization(tmp_path, monkeypatch):
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

    def fake_build(api_name, version, credentials):
        captured["api_name"] = api_name
        captured["version"] = version
        captured["credentials"] = credentials
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
    assert isinstance(captured["credentials"], FreshCredentials)


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


def _config():
    return {
        "gmail": {
            "credentials_path": "credentials.json",
            "token_path": "token.json",
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
    flow_module = ModuleType("google_auth_oauthlib.flow")
    api_client_module = _package("googleapiclient")
    discovery_module = ModuleType("googleapiclient.discovery")

    class FakeRequest:
        pass

    requests_module.Request = FakeRequest
    exceptions_module.RefreshError = refresh_error_cls
    credentials_module.Credentials = credentials_cls
    flow_module.InstalledAppFlow = flow_cls
    discovery_module.build = build_fn

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
        oauthlib_module,
        flow_module,
        api_client_module,
        discovery_module,
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)


def _package(name: str) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = []
    return module
