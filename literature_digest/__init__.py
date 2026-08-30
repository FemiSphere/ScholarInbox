"""Daily academic literature digest workflow."""

from importlib.metadata import PackageNotFoundError, distribution

__all__ = ["__author__", "__version__"]

try:
    _distribution = distribution("literature-digest")
    __version__ = _distribution.version
    __author__ = _distribution.metadata.get("Author") or "马心远"
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.1.0"
    __author__ = "马心远"
