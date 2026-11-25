from __future__ import annotations

import copy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "gmail": {
        "query": "is:unread",
        "max_emails_per_run": 50,
        "mark_as_read": False,
        "include_spam_trash": False,
        "credentials_path": "credentials.json",
        "token_path": "token.json",
        "request_timeout_seconds": 30,
        "proxy_url": "",
        "batch_fetch_size": 10,
        "batch_fetch_max_retries": 3,
        "batch_fetch_retry_backoff_seconds": 1.0,
        "batch_modify_size": 1000,
    },
    "llm": {
        "provider": "codex_cli",
        "model": "gpt-5.4-mini",
        "reasoning_effort": "low",
        "timeout_seconds": 120,
        "max_output_tokens": 4000,
        "operation_timeouts": {"email_extraction": 45, "paper_ranking": 90},
        "request_budget_seconds": 120,
        "operation_settings": {},
        "codex_cli": {"executable": "codex", "ephemeral": True, "extra_args": []},
        "openai_compatible": {
            "base_url": "",
            "api_key_env": "OPENAI_API_KEY",
            "model": "",
            "temperature": 0.2,
            "reasoning_effort": "",
            "response_format_json": True,
            "max_retries": 1,
            "retry_backoff_seconds": 1.0,
            "extra_body": {},
        },
    },
    "web_enrichment": {
        "enabled": True,
        # Covers every displayed high/medium paper (max_high_relevance 20 + max_medium_relevance 30).
        "max_papers": 50,
        # Free Crossref/OpenAlex lookups run before the paid DeepSeek Search/Fetch.
        "metadata_sources_enabled": True,
        "metadata_timeout_seconds": 10,
        "metadata_max_requests": 300,
        "max_requests": 80,
        "max_workers": 3,
        "budget_seconds": 480,
        "retrieval_budget_seconds": 360,
        "paper_budget_seconds": 60,
        "max_retries": 0,
        "request_timeout_seconds": 40,
        "search_timeout_seconds": 12,
        "cache_enabled": True,
        "cache_path": "data/cache/web_evidence.sqlite3",
        "cache_max_entries": 300,
        "cache_max_bytes": 8 * 1024 * 1024,
        "cache_ttl_days": 30,
    },
    "result_cache": {
        # Per-paper ranking/translation results reused after a fallback rerun; cleared after a
        # successful real run, otherwise expired after ttl_days and capped at max_entries.
        "enabled": True,
        "path": "data/cache/results.sqlite3",
        "ttl_days": 7,
        "max_entries": 5000,
    },
    "research_interests": {
        "path": "research_interests.md",
        "refresh_each_run": False,
        "cache_path": "data/cache/research_interests.json",
    },
    "filtering": {
        "skip_promotional": True,
        "audit_skipped_emails": True,
        "mark_skipped_as_read": False,
        "academic_sender_allowlist": [],
        "sender_blocklist": [],
        "promotional_keywords": [
            "sale",
            "webinar",
            "discount",
            "offer",
            "unsubscribe",
            "sponsored",
            "marketing",
        ],
    },
    "parsing": {
        "cache_enabled": True,
        "cache_dir": "data/cache/email_parsing",
        "save_toc_images": True,
        "toc_image_dir": "data/toc_images",
        "max_images_per_email": 20,
        "fuzzy_title_threshold": 92,
        "llm_structure_non_scholar": True,
    },
    "deduplication": {
        "registry_enabled": True,
        "registry_path": "data/paper_registry.json",
        "retention_days": 30,
        "fuzzy_title_threshold": 94,
        "bootstrap_from_outputs": True,
    },
    "digest": {
        "output_dir": "outputs",
        "output_formats": ["html"],
        # HTML reading style. Bright: fresh, pop, bauhaus, riso. Academic: editorial, swiss, calm.
        "theme": "fresh",
        "cleanup_old_outputs": False,
        "include_low_relevance": True,
        "include_off_topic": True,
        "include_irrelevant": True,
        "language": "zh-CN",
        "max_high_relevance": 20,
        "max_medium_relevance": 30,
        "max_off_topic": None,
        "max_irrelevant": 80,
    },
    "safety": {
        "dry_run_default": True,
        "never_delete_emails": True,
        "redact_secrets_in_logs": True,
        "allow_sample_without_credentials": True,
        "allow_offline_llm_for_sample": True,
    },
    "progress": {
        "enabled": True,
        "show_timestamps": True,
    },
    "ui": {
        "banner_enabled": True,
        "display_name": "",
        "color_enabled": True,
    },
    "telemetry": {
        "detailed_log_enabled": True,
        "log_dir": "logs/metrics",
        # Run logs and request metrics older than this many days are deleted after each run; 0 keeps all.
        "log_retention_days": 30,
        "show_compact_summary": True,
    },
    "performance": {
        "run_timeout_seconds": 900,
        "parsing_max_workers": 3,
        "ranking_max_workers": 3,
        "ranking_batch_size": 10,
        "separate_translation": True,
        "ranking_abstract_max_chars": 2000,
        "email_text_max_chars": 12000,
        "email_max_chunk_items": 8,
        "email_max_split_depth": 4,
        "email_max_requests_per_email": 32,
        "email_budget_seconds": 240,
        "email_max_links": 50,
        "email_max_images": 20,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = Path(path) if path else Path("config.local.yaml")
    if not config_path.exists():
        return config

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on user env
        raise RuntimeError(
            "PyYAML is required to read YAML config files. Install dependencies with "
            "`python -m pip install -e .` or remove config.local.yaml to use defaults."
        ) from exc

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a mapping: {config_path}")
    config = deep_merge(config, loaded)
    config = _apply_llm_preset(config, loaded.get("llm"), yaml)
    return _load_external_llm_config(config, config_path.parent, yaml)


PRESET_DIR = Path(__file__).resolve().parent / "presets"
# Former template paths now served by the packaged presets, so old configs keep working.
_LEGACY_TEMPLATE_PRESETS = {
    "config/llm/deepseek.example.yaml": "deepseek",
    "config/llm/codex_cli.example.yaml": "codex_cli",
}


def available_presets() -> list[str]:
    return sorted(path.stem for path in PRESET_DIR.glob("*.yaml"))


def load_preset(name: str, yaml_module: Any | None = None) -> dict[str, Any]:
    if yaml_module is None:
        import yaml as yaml_module
    path = PRESET_DIR / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"Unknown llm.preset {name!r}; available: {', '.join(available_presets())}")
    loaded = yaml_module.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"LLM preset must contain a mapping: {path}")
    return loaded


def _apply_llm_preset(config: dict[str, Any], user_llm: Any, yaml_module: Any) -> dict[str, Any]:
    """defaults <- preset <- the user's own llm keys (so inline overrides win)."""
    if not isinstance(user_llm, dict) or not user_llm.get("preset"):
        return config
    preset = load_preset(str(user_llm["preset"]), yaml_module)
    merged = deep_merge(DEFAULT_CONFIG["llm"], preset)
    config["llm"] = deep_merge(merged, user_llm)
    return config


def _load_external_llm_config(config: dict[str, Any], base_dir: Path, yaml_module: Any) -> dict[str, Any]:
    config_path_value = config.get("llm", {}).get("config_path")
    if not config_path_value:
        return config

    llm_config_path = Path(config_path_value)
    if not llm_config_path.is_absolute():
        llm_config_path = base_dir / llm_config_path
    legacy = _LEGACY_TEMPLATE_PRESETS.get(Path(config_path_value).as_posix())
    if legacy and not llm_config_path.exists():
        llm_config_path = PRESET_DIR / f"{legacy}.yaml"
    if not llm_config_path.exists():
        raise FileNotFoundError(f"LLM config file not found: {llm_config_path}")

    loaded = yaml_module.safe_load(llm_config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"LLM config file must contain a mapping: {llm_config_path}")

    provider_config = loaded.get("llm", loaded)
    if not isinstance(provider_config, dict):
        raise ValueError(f"LLM config file must contain a mapping: {llm_config_path}")
    config["llm"] = deep_merge(config["llm"], provider_config)
    config["llm"]["config_path"] = str(config_path_value)
    return config


def resolve_path(value: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir or Path.cwd()) / path
