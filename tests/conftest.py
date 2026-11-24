import pytest

_PROXY_VARIABLES = (
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "CODEX_PROXY_URL", "CODEX_NO_PROXY", "SCHOLAR_INBOX_PROXY_URL",
)


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    """Keep tests independent of the developer's shell (proxies, colour settings)."""
    for name in _PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name in ("FORCE_COLOR", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)
