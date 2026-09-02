"""Daily academic literature digest workflow."""

from importlib.metadata import PackageNotFoundError, distribution

__all__ = ["__author__", "__version__"]

try:
    _distribution = distribution("scholar-inbox")
    __version__ = _distribution.version
    __author__ = _distribution.metadata.get("Author") or "马心远"
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.2.0"
    __author__ = "马心远"
