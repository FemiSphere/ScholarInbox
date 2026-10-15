from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from threading import Event, Lock
from typing import Any

from .concurrency import cooperative_map
from .interests import profile_to_json
from .llm import LLMClient, LLMError
from .llm.base import redact_secrets
from .models import InterestProfile, PaperEntry, RankedPaper, RelevanceLevel
from .telemetry import llm_operation


def rank_papers(
    entries: list[PaperEntry],
    profile: InterestProfile,
    llm: LLMClient,
    *,
    batch_size: int = 20,
    max_workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
    event_callback: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
    separate_translation: bool = False,
    abstract_max_chars: int = 2000,
) -> list[RankedPaper]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if abstract_max_chars < 1:
        raise ValueError("abstract_max_chars must be at least 1")
    batches = [
        (batch_number, offset, entries[offset : offset + batch_size])
        for batch_number, offset in enumerate(range(0, len(entries), batch_size), start=1)
    ]
    total_batches = (len(entries) + batch_size - 1) // batch_size
    worker_count = min(max(1, max_workers), total_batches or 1)
    callback_lock = Lock()

    def emit(message: str) -> None:
        if event_callback:
            with callback_lock:
                event_callback(message)

    def rank_one(item: tuple[int, int, list[PaperEntry]]) -> list[RankedPaper]:
        batch_number, offset, batch = item
        def on_error(error: LLMError) -> None:
            stage = "论文翻译" if str(error).startswith("论文翻译失败：") else "论文排序"
            emit(f"{stage} {batch_number}/{total_batches}：LLM 失败（{type(error).__name__}），回退本地规则")
        return _rank_batch(
            batch, profile, llm, offset, on_error=on_error,
            separate_translation=separate_translation, abstract_max_chars=abstract_max_chars,
        )

    ranked_batches = cooperative_map(
        rank_one, batches, max_workers=worker_count, thread_name_prefix="paper-ranker",
        cancel_event=cancel_event, progress=progress,
    )
    ranked = [paper for batch in ranked_batches for paper in batch]
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def _rank_batch(
    entries: list[PaperEntry],
    profile: InterestProfile,
    llm: LLMClient,
    offset: int,
    on_error: Callable[[LLMError], None] | None = None,
    *,
    separate_translation: bool = False,
    abstract_max_chars: int = 2000,
) -> list[RankedPaper]:
    papers_json = [
        {
            "index": offset + index,
            "title": entry.title,
            "doi": entry.doi,
            "url": entry.url,
            "authors": entry.authors,
            "venue": entry.venue,
            "abstract": entry.abstract[:abstract_max_chars],
            "source_status": "email_excerpt" if entry.abstract.strip() else "title_only",
            "abstract_truncated": len(entry.abstract) > abstract_max_chars,
            "abstract_original_chars": len(entry.abstract),
            "source_subject": entry.source_subject,
        }
        for index, entry in enumerate(entries)
    ]
    translation_schema = (
        '"title_zh": "中文标题", "summary_zh": "中文摘要式概述",'
        if not separate_translation else ""
    )
    translation_rules = (
        "- Translate every English paper title into natural Chinese in title_zh; never copy the English title unchanged.\n"
        "- Produce a faithful Chinese summary from supplied metadata in summary_zh.\n"
        if not separate_translation else
        "- Return analysis fields only; do not translate titles or write summaries in this call.\n"
    )
    prompt = f"""
RANK_PAPERS_JSON

You are ranking paper entries for a Chinese literature digest.

Return exactly one valid JSON object. Do not wrap it in Markdown or add explanations.
The first character must be `{{` and the last character must be `}}`.

Schema:
{{
  "papers": [
    {{
      "index": 0,
      "relevance": "high",
      "score": 0.92,
      {translation_schema}
      "reason_zh": "中文推荐理由",
      "matched_topics": ["pentagonal materials", "COF/MOF"]
    }}
  ]
}}

Rules:
- `index` must match the corresponding entry in `PAPERS_JSON`.
{translation_rules}
- Never use placeholders such as "...", "N/A", or empty strings.
- Keep formulas, chemical names, material abbreviations, model names, and Greek letters as needed.
- `relevance` must be one of: "high", "medium", "low", "irrelevant".
- `score` must be a number from 0 to 1.
- Use "low" for a genuine academic paper that is weakly related to the research interest profile.
- Use "irrelevant" only when the entry is clearly not an academic paper, such as advertising,
  sales or subscription promotion, product marketing, recruitment, event registration, or a
  malformed extraction. A valid academic paper outside the user's field must remain "low".
- For "irrelevant", use a score close to 0, keep the note short, and explain the non-academic signal.
- Judge relevance only from the research interest profile and paper metadata.
- `abstract` may be an incomplete email snippet, especially for Google Scholar alerts.
- Do not invent details that are not present in the title, venue, snippet, DOI, or URL.
- For high/medium relevance, write a cautious Chinese note based on available metadata.
- For low relevance, keep the note short and focus on why it is weakly related.
- Treat abstract as an email excerpt, never as a verified full abstract. source_status, abstract_truncated,
  and abstract_original_chars describe the available evidence, not the original publication abstract.
- Assess the actual scientific connection through material system/structural motif, method,
  property and research question; explain the strongest supported connection to the profile.
- Shared keywords alone do not require medium/high relevance. Distinguish a real scientific
  connection or transferable method from incidental vocabulary and unrelated uses of an acronym.
- High means a direct connection to a priority research question/system/property or a clearly
  transferable method; medium means a useful adjacent connection; low means a weak connection.
- Separate topical relevance from evidence confidence. A title-only paper can be high if directly
  on topic, but explicitly state in reason_zh that evidence is limited to the title/metadata.
- For truncated or incomplete excerpts mention uncertainty where it affects the conclusion.
- Never infer a specific method, mechanism, result, or performance value without source evidence.
- reason_zh must be a short visible Chinese recommendation rationale and evidence limitation,
  not private chain-of-thought or a step-by-step reasoning transcript.
- Return one item for every input paper, using the original `index` exactly once.

Research interest profile:
{profile_to_json(profile)}

PAPERS_JSON:
{json.dumps(papers_json, ensure_ascii=False)}
""".strip()
    expected = set(range(offset, offset + len(entries)))
    try:
        with llm_operation("paper_ranking", len(entries)):
            payload = llm.complete_json(prompt)
        by_index = _payload_by_index(payload, expected)
        if separate_translation:
            for item in by_index.values():
                _validate_analysis(item)
                # Ignore any unsolicited translation produced by the reasoning call.
                item.pop("title_zh", None)
                item.pop("summary_zh", None)
    except LLMError as exc:
        if on_error:
            on_error(exc)
        fallback = _fallback_ranked_batch(entries, profile, exc)
        by_index = {
            offset + i: {
                "relevance": paper.relevance, "score": paper.score,
                "reason_zh": paper.reason_zh, "matched_topics": paper.matched_topics,
                "title_zh": paper.title_zh, "summary_zh": paper.summary_zh,
            }
            for i, paper in enumerate(fallback)
        }
        if not separate_translation:
            return fallback

    if separate_translation:
        translation_input = [
            {**item, "relevance": by_index[item["index"]]["relevance"]}
            for item in papers_json
        ]
        translation_prompt = f"""
TRANSLATE_PAPERS_JSON
Translate source paper titles and summarize supplied source metadata into natural Chinese.
Return only a valid JSON object with this schema:
{{"papers": [{{"index": 0, "title_zh": "中文标题", "summary_zh": "中文概述"}}]}}
- Return each input index exactly once. Return no relevance, score, reason or matched_topics fields.
- Preserve formulas, chemical abbreviations and proper model names; do not leave English titles unchanged.
- Use only title and the supplied email excerpt. Do not invent methods, mechanisms or results.
- If source_status is title_only, state that only title/metadata are available; do not fabricate an abstract.
- An email excerpt is not a verified complete abstract. Preserve uncertainty and truncation boundaries.
- relevance is supplied only to control summary length: high/medium concise explanation, low/irrelevant brief note.
PAPERS_JSON:
{json.dumps(translation_input, ensure_ascii=False)}
""".strip()
        try:
            with llm_operation("paper_translation", len(entries)):
                translation_payload = llm.complete_json(translation_prompt)
            translations = _payload_by_index(translation_payload, expected)
            for i, entry in enumerate(entries):
                translated = translations[offset + i]
                if not _valid_generated_text(translated.get("title_zh"), original=entry.title):
                    raise LLMError("Translation response has missing or unchanged title_zh")
                if not _valid_generated_text(translated.get("summary_zh")):
                    raise LLMError("Translation response has missing summary_zh")
            for index, translated in translations.items():
                # Never allow a translation response to overwrite scientific ranking.
                by_index[index].update({key: translated[key] for key in ("title_zh", "summary_zh")})
        except LLMError as exc:
            if on_error:
                on_error(LLMError(f"论文翻译失败：{exc}"))

    result = []
    for local_index, entry in enumerate(entries):
        item = by_index[offset + local_index]
        if separate_translation and not entry.abstract.strip():
            reason = str(item.get("reason_zh", ""))
            item["reason_zh"] = reason + "（仅有标题及元数据，证据有限。）"
        result.append(_ranked_from_payload(entry, item))
    return result


def _payload_by_index(
    payload: dict[str, Any], expected: set[int] | None = None,
) -> dict[int, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("papers"), list):
        raise LLMError("Ranking/translation response must contain a papers list")
    result: dict[int, dict[str, Any]] = {}
    for item in payload["papers"]:
        if not isinstance(item, dict) or type(item.get("index")) is not int:
            raise LLMError("Ranking/translation item must have an integer index")
        index = item["index"]
        if index in result:
            raise LLMError("Ranking/translation response contains duplicate indexes")
        result[index] = item
    if expected is not None and set(result) != expected:
        raise LLMError("Ranking/translation response has missing or unexpected indexes")
    return result


def _validate_analysis(item: dict[str, Any]) -> None:
    if item.get("relevance") not in {"high", "medium", "low", "irrelevant"}:
        raise LLMError("Ranking response has invalid relevance")
    score = item.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        raise LLMError("Ranking response has invalid score")
    if not _valid_generated_text(item.get("reason_zh")):
        raise LLMError("Ranking response has missing reason_zh")
    if not isinstance(item.get("matched_topics"), list):
        raise LLMError("Ranking response has invalid matched_topics")


def _ranked_from_payload(entry: PaperEntry, payload: dict[str, Any]) -> RankedPaper:
    relevance = str(payload.get("relevance", "low")).lower()
    if relevance not in {"high", "medium", "low", "irrelevant"}:
        relevance = "low"
    try:
        score = float(payload.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0

    academic_guard_applied = False
    if _looks_clearly_nonacademic(entry):
        relevance = "irrelevant"
        score = 0.0
    elif relevance == "irrelevant" and _has_strong_academic_identity(entry):
        relevance = "low"
        score = min(score, 0.24)
        academic_guard_applied = True

    title_zh = _valid_generated_text(payload.get("title_zh"), original=entry.title)
    if not title_zh:
        title_zh = _fallback_title_translation(entry.title)
    summary_zh = _valid_generated_text(payload.get("summary_zh"))
    reason_zh = _valid_generated_text(payload.get("reason_zh"))
    if academic_guard_applied:
        reason_zh = "该条目具有 DOI 或 arXiv 等明确论文身份，因此保守保留为低相关学术论文。"
    if relevance == "irrelevant" and not reason_zh:
        reason_zh = "该条目包含明显的推广、活动或其他非学术信号，不属于论文推荐范围。"
    return RankedPaper(
        entry=entry,
        relevance=relevance,  # type: ignore[arg-type]
        score=max(0.0, min(score, 1.0)),
        title_zh=title_zh,
        summary_zh=summary_zh or "未生成中文摘要，已使用默认占位说明。",
        reason_zh=reason_zh or "未生成中文推荐理由，已使用默认占位说明。",
        matched_topics=_string_list(payload.get("matched_topics")),
    )


def _fallback_ranked_batch(
    entries: list[PaperEntry],
    profile: InterestProfile,
    error: Exception,
) -> list[RankedPaper]:
    reason = redact_secrets(str(error).strip())
    if len(reason) > 240:
        reason = reason[:240] + "..."
    return [
        _fallback_ranked_paper(entry, profile, reason)
        for entry in entries
    ]


def _fallback_ranked_paper(entry: PaperEntry, profile: InterestProfile, error_reason: str) -> RankedPaper:
    score, matched_topics = _heuristic_score(entry, profile)
    clearly_nonacademic = _looks_clearly_nonacademic(entry)
    relevance: RelevanceLevel = (
        "irrelevant"
        if clearly_nonacademic
        else "high"
        if score >= 0.7
        else "medium"
        if score >= 0.28
        else "low"
    )
    if clearly_nonacademic:
        score = 0.0
        matched_topics = []
        reason = "LLM JSON 解析失败；本地规则检测到明显的推广、订阅或其他非学术信号。"
        summary = "该条目看起来不是学术论文，已归入“不相关”供审计。"
    else:
        topic_note = "、".join(matched_topics[:6]) if matched_topics else "未命中明显高优先级主题"
        reason = f"LLM JSON 解析失败，已用本地规则按标题、期刊/来源和片段保守判断；命中：{topic_note}。"
        summary = "LLM 未返回可解析的结构化结果；此处为本地规则生成的占位摘要，请优先查看英文原题、期刊/来源和原文链接。"
    if error_reason:
        reason += f" 错误摘要：{error_reason}"
    return RankedPaper(
        entry=entry,
        relevance=relevance,
        score=score,
        title_zh=_fallback_title_translation(entry.title),
        summary_zh=summary,
        reason_zh=reason,
        matched_topics=matched_topics,
    )


def _heuristic_score(entry: PaperEntry, profile: InterestProfile) -> tuple[float, list[str]]:
    text = _normalize_text(
        " ".join(
            [
                entry.title,
                entry.abstract,
                entry.venue,
                entry.raw_text[:700],
                entry.source_subject,
            ]
        )
    )
    score = 0.0
    matched: list[str] = []

    weighted_patterns: list[tuple[str, float, tuple[str, ...]]] = [
        ("thermal conductivity", 0.30, ("thermal conductivity", "heat conductivity", "热导率")),
        ("thermal transport", 0.25, ("thermal transport", "heat transport", "热输运", "热传输")),
        ("phonons", 0.18, ("phonon", "phonons", "声子")),
        ("machine-learning potentials", 0.28, ("machine learning potential", "machine-learning potential", "interatomic potential", "neural network potential", "mlip", "nep", "势函数")),
        ("COF", 0.26, ("cof", "covalent organic framework", "covalent organic frameworks", "共价有机框架")),
        ("MOF", 0.22, ("mof", "metal-organic framework", "metal organic framework", "metal-organic frameworks", "金属有机框架")),
        ("pentagonal materials", 0.30, ("pentagonal", "penta-", "penta ", "五边形", "五边")),
        ("nanotubes", 0.20, ("nanotube", "nanotubes", "纳米管")),
        ("framework materials", 0.10, ("framework", "porous", "多孔", "框架材料")),
        ("computational materials", 0.10, ("molecular dynamics", "first-principles", "density functional", "dft", "simulation", "计算材料")),
        ("AI for materials", 0.10, ("machine learning", "deep learning", "neural network", "artificial intelligence", "materials informatics")),
    ]
    for label, weight, patterns in weighted_patterns:
        if any(_normalize_text(pattern) in text for pattern in patterns):
            score += weight
            matched.append(label)

    for topic in _profile_terms(profile):
        topic_tokens = _important_tokens(topic)
        if not topic_tokens:
            continue
        hits = [token for token in topic_tokens if token in text]
        if not hits:
            continue
        score += min(0.18, 0.05 * len(hits))
        matched.append(topic)

    deprioritized_hits = [
        topic
        for topic in _profile_terms(profile, deprioritized=True)
        if _normalize_text(topic) and _normalize_text(topic) in text
    ]
    if deprioritized_hits:
        score -= 0.25
        matched.extend([f"降权：{topic}" for topic in deprioritized_hits[:2]])

    score = max(0.0, min(score, 1.0))
    return round(score, 2), _dedupe_preserve_order(matched)


_CLEARLY_NONACADEMIC_PATTERNS = (
    "limited time offer",
    "special offer",
    "exclusive offer",
    "subscription offer",
    "renew your subscription",
    "buy now",
    "shop now",
    "save up to",
    "free trial",
    "request a demo",
    "product demo",
    "register now",
    "registration is open",
    "reserve your seat",
    "sponsored message",
    "sponsored content",
    "advertisement",
    "career opportunity",
    "job alert",
    "now hiring",
    "unsubscribe preferences",
    "editorial board announcement and subscription information",
    "限时优惠",
    "特价促销",
    "立即购买",
    "订阅优惠",
    "续订优惠",
    "免费试用",
    "预约演示",
    "立即注册",
    "职位推荐",
    "招聘信息",
    "推广内容",
)


def _looks_clearly_nonacademic(entry: PaperEntry) -> bool:
    """Conservatively catch obvious non-paper entries when the LLM misses them."""

    text = _normalize_text(
        " ".join(
            [
                entry.title,
                entry.venue,
                entry.source_subject,
            ]
        )
    )
    return any(pattern in text for pattern in _CLEARLY_NONACADEMIC_PATTERNS)


def _has_strong_academic_identity(entry: PaperEntry) -> bool:
    if entry.doi.strip():
        return True
    text = _normalize_text(" ".join([entry.title, entry.venue, entry.url]))
    return bool(re.search(r"(?:arxiv(?:\.org)?[:/\s]|\b\d{4}\.\d{4,5}\b)", text))


def _profile_terms(profile: InterestProfile, *, deprioritized: bool = False) -> list[str]:
    if deprioritized:
        return profile.deprioritized_topics
    return (
        profile.high_priority_topics
        + profile.material_systems
        + profile.methods
        + profile.properties
        + profile.current_projects
        + profile.medium_priority_topics
    )


def _important_tokens(topic: str) -> list[str]:
    normalized = _normalize_text(topic)
    tokens = re.findall(r"[a-z0-9][a-z0-9+\-.]{1,}|[\u4e00-\u9fff]{2,}", normalized)
    stopwords = {"and", "for", "with", "the", "from", "based", "materials", "science", "research", "current"}
    return [token for token in tokens if token not in stopwords]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def count_relevance(papers: list[RankedPaper], level: RelevanceLevel) -> int:
    return sum(1 for paper in papers if paper.relevance == level)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _valid_generated_text(value: Any, *, original: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    placeholders = {"...", "n/a", "none", "null"}
    if text.lower() in placeholders:
        return ""
    if original and text.casefold() == original.strip().casefold():
        return ""
    return text


def _fallback_title_translation(title: str) -> str:
    normalized = " ".join(title.split())
    exact = {
        "Metal-modulated phonon transport in porphyrin-based MOFs": "卟啉基 MOFs 中金属调控的声子输运",
        "Al-Doping Effects on beta-Ga2O3 Thermal Transport: Neural Network Potential-Based NEMD": "Al 掺杂对 beta-Ga2O3 热输运的影响：基于神经网络势的 NEMD",
    }
    if normalized in exact:
        return exact[normalized]

    replacements = [
        ("machine-learning interatomic potentials", "机器学习原子间势"),
        ("machine learning interatomic potentials", "机器学习原子间势"),
        ("neural network potential-based", "基于神经网络势的"),
        ("neural network potential", "神经网络势"),
        ("molecular dynamics", "分子动力学"),
        ("thermal conductivity", "热导率"),
        ("thermal transport", "热输运"),
        ("phonon transport", "声子输运"),
        ("phonons", "声子"),
        ("porphyrin-based MOFs", "卟啉基 MOFs"),
        ("pentagonal COF nanotubes", "五边形 COF 纳米管"),
        ("COF nanotubes", "COF 纳米管"),
        ("nanotubes", "纳米管"),
        ("metal-modulated", "金属调制"),
        ("doping effects", "掺杂效应"),
        ("effects on", "对……的影响"),
        ("anisotropic", "各向异性"),
        ("enhancement", "增强"),
        ("aligned", "取向排列的"),
        ("two-dimensional", "二维"),
        ("electronic properties", "电子性质"),
        ("structural defects", "结构缺陷"),
        ("band degeneracy", "能带简并"),
        ("orbital engineering", "轨道工程"),
        ("in ", "在"),
        ("of ", "的"),
    ]
    translated = normalized
    for source, target in replacements:
        translated = _replace_case_insensitive(translated, source, target)
    if any("\u4e00" <= char <= "\u9fff" for char in translated):
        return translated
    return f"待翻译：{title}"


def _replace_case_insensitive(text: str, source: str, target: str) -> str:
    return re.sub(re.escape(source), target, text, flags=re.IGNORECASE)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()
