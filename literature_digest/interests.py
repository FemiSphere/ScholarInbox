from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .llm import LLMClient, LLMError
from .models import InterestProfile
from .telemetry import llm_operation


INTEREST_CACHE_VERSION = 2  # v2 adds broad_fields for the off_topic tier


def read_research_interests(path: str | Path) -> str:
    interests_path = Path(path)
    if not interests_path.exists():
        raise FileNotFoundError(
            f"Research interests file not found: {interests_path}. "
            "Run `scholar-inbox init`, or copy research_interests.example.md to research_interests.md and edit it."
        )
    return interests_path.read_text(encoding="utf-8").strip()


def analyze_research_interests(text: str, llm: LLMClient) -> InterestProfile:
    try:
        payload = _request_interest_profile(text, llm)
    except LLMError:
        return fallback_interest_profile(text)
    return profile_from_payload(payload)


def load_or_analyze_research_interests(
    text: str,
    llm: LLMClient,
    *,
    cache_path: str | Path,
    model_fingerprint: str,
    refresh: bool = False,
) -> tuple[InterestProfile, bool]:
    """Return a cached interest profile when both source text and model settings match."""

    path = Path(cache_path)
    cache_key = _interest_cache_key(text, model_fingerprint)
    if not refresh:
        cached = _read_interest_cache(path, cache_key)
        if cached is not None:
            return cached, True

    try:
        payload = _request_interest_profile(text, llm)
    except LLMError:
        return fallback_interest_profile(text), False
    profile = profile_from_payload(payload)
    _write_interest_cache(path, cache_key, payload)
    return profile, False


def _request_interest_profile(text: str, llm: LLMClient) -> dict[str, Any]:
    prompt = f"""
INTEREST_PROFILE_JSON

Read the research-interest note below and return STRICT JSON only.

Schema:
{{
  "current_projects": ["..."],
  "material_systems": ["..."],
  "methods": ["..."],
  "properties": ["..."],
  "high_priority_topics": ["..."],
  "medium_priority_topics": ["..."],
  "deprioritized_topics": ["..."],
  "broad_fields": ["..."],
  "summary_zh": "..."
}}

Rules:
- Return only a single JSON object. No markdown fences, no commentary.
- Keep values concise and specific.
- `summary_zh` should be a short Chinese summary of the research interests.
- Put the strongest matching topics into `high_priority_topics`.
- Put related but weaker topics into `medium_priority_topics`.
- Put clearly out-of-scope topics into `deprioritized_topics`.
- `broad_fields`: 2-5 broad disciplines that bound the research as a whole (for example
  "computational materials science", "condensed matter physics"). Use an explicit
  "大方向"/"broad field" section when the note has one; otherwise infer them. A paper
  outside every broad field is treated as off-topic, so keep them broad, not project-specific.
- If the note is brief or ambiguous, infer a compact profile that is still useful for ranking.

Research-interest note:
{text}
""".strip()
    with llm_operation("interest_profile", 1):
        payload = llm.complete_json(prompt)
    return payload


def fallback_interest_profile(text: str) -> InterestProfile:
    """Create a lightweight profile without calling an LLM."""

    summary = re.sub(r"\s+", " ", text).strip()
    if len(summary) > 220:
        summary = summary[:220].rstrip() + "..."
    topics = _extract_topic_phrases(text)
    payload = {
        "current_projects": [summary] if summary else [],
        "material_systems": _terms_present(
            text,
            [
                "COF",
                "MOF",
                "HOF",
                "pentagonal",
                "pentagon",
                "framework",
                "porous",
            ],
        ),
        "methods": _terms_present(text, ["machine learning", "MLIP", "neural network", "phonon"]),
        "properties": _terms_present(text, ["thermal conductivity", "phonon", "heat transport", "diffusivity"]),
        "high_priority_topics": topics,
        "medium_priority_topics": [],
        "deprioritized_topics": [],
        "broad_fields": [],
        "summary_zh": summary or "研究兴趣摘要为空，使用默认回退配置。",
    }
    return profile_from_payload(payload)


def profile_from_payload(payload: dict[str, Any]) -> InterestProfile:
    return InterestProfile(
        current_projects=_string_list(payload.get("current_projects")),
        material_systems=_string_list(payload.get("material_systems")),
        methods=_string_list(payload.get("methods")),
        properties=_string_list(payload.get("properties")),
        high_priority_topics=_string_list(payload.get("high_priority_topics")),
        medium_priority_topics=_string_list(payload.get("medium_priority_topics")),
        deprioritized_topics=_string_list(payload.get("deprioritized_topics")),
        broad_fields=_string_list(payload.get("broad_fields")),
        summary_zh=str(payload.get("summary_zh", "")).strip(),
        raw=payload,
    )


def profile_to_json(profile: InterestProfile) -> str:
    return json.dumps(
        profile.raw
        or {
            "current_projects": profile.current_projects,
            "material_systems": profile.material_systems,
            "methods": profile.methods,
            "properties": profile.properties,
            "high_priority_topics": profile.high_priority_topics,
            "medium_priority_topics": profile.medium_priority_topics,
            "deprioritized_topics": profile.deprioritized_topics,
            "broad_fields": profile.broad_fields,
            "summary_zh": profile.summary_zh,
        },
        ensure_ascii=False,
        indent=2,
    )


def _interest_cache_key(text: str, model_fingerprint: str) -> str:
    material = json.dumps(
        {
            "version": INTEREST_CACHE_VERSION,
            "text": text,
            "model": model_fingerprint,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _read_interest_cache(path: Path, expected_key: str) -> InterestProfile | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_key") != expected_key:
        return None
    profile_payload = payload.get("profile")
    if not isinstance(profile_payload, dict):
        return None
    return profile_from_payload(profile_payload)


def _write_interest_cache(path: Path, cache_key: str, profile_payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "version": INTEREST_CACHE_VERSION,
                    "cache_key": cache_key,
                    "profile": profile_payload,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        # A cache failure must not prevent digest generation.
        return


def _extract_topic_phrases(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text)
    parts = re.split(r"[;,\n/\\]+", normalized)
    topics = [part.strip(" .:") for part in parts if 4 <= len(part.strip()) <= 60]
    return topics[:8]


def _terms_present(text: str, terms: list[str]) -> list[str]:
    lower_text = text.lower()
    result: list[str] = []
    for term in terms:
        if term.lower() in lower_text:
            result.append(term)
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
