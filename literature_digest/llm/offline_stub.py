from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .base import extract_json_object


@dataclass(slots=True)
class OfflineStubClient:
    """Deterministic fallback for tests and no-credential sample dry-runs only."""

    def complete(self, prompt: str) -> str:
        if "INTEREST_PROFILE_JSON" in prompt:
            return json.dumps(
                {
                    "current_projects": [
                        "computational materials science",
                        "AI for materials",
                    ],
                    "material_systems": ["COF", "MOF", "pentagonal materials"],
                    "methods": ["machine-learning interatomic potentials", "phonons", "thermal transport"],
                    "properties": ["thermal conductivity", "phonon transport"],
                    "high_priority_topics": [
                        "pentagonal materials",
                        "COF/MOF",
                        "machine-learning interatomic potentials",
                        "thermal transport",
                    ],
                    "medium_priority_topics": ["AI for materials", "materials informatics"],
                    "deprioritized_topics": ["unrelated organic synthesis"],
                    "summary_zh": "当前研究聚焦于计算材料科学、AI for materials、COF/MOF、五边形材料、机器学习原子间势以及热输运。",
                },
                ensure_ascii=False,
            )
        if "EMAIL_PAPER_EXTRACTION_JSON" in prompt:
            # Offline fixtures use the same structural envelope as the live extractor.
            encoded = prompt.split("CANDIDATE_LINKS_JSON:\n", 1)[1].split("\n\nCANDIDATE_IMAGES_JSON:", 1)[0]
            links = json.loads(encoded)
            return json.dumps({"papers": [
                {"title": item["text"], "url": item["url"], "snippet": "", "image_index": None}
                for item in links if len(item.get("text", "")) >= 15
            ]}, ensure_ascii=False)
        if "TRANSLATE_PAPERS_JSON" in prompt:
            return json.dumps({"papers": [
                {"index": item["index"], "title_zh": f"论文：{item.get('title', '')}",
                 "summary_zh": "这是本地离线 stub 生成的中文摘要，用于测试和 dry-run。"}
                for item in _extract_papers(prompt)
            ]}, ensure_ascii=False)
        if "RANK_PAPERS_JSON" in prompt:
            papers = _extract_papers(prompt)
            ranked = []
            for item in papers:
                text = f"{item.get('title', '')} {item.get('abstract', '')}".lower()
                title = str(item.get("title", "")).lower()
                score = 0.25
                if any(term in text for term in ["pentagonal", "penta", "cof", "mof"]):
                    score += 0.35
                if any(term in text for term in ["thermal", "phonon", "conductivity"]):
                    score += 0.25
                if any(term in text for term in ["machine learning", "interatomic potential", "nep"]):
                    score += 0.2
                nonacademic = any(
                    phrase in title
                    for phrase in (
                        "limited time offer",
                        "buy now",
                        "subscription offer",
                        "register now",
                        "product demo",
                    )
                )
                relevance = (
                    "irrelevant"
                    if nonacademic
                    else "high"
                    if score >= 0.75
                    else "medium"
                    if score >= 0.45
                    else "low"
                )
                if nonacademic:
                    score = 0.0
                ranked.append(
                    {
                        "index": item["index"],
                        "relevance": relevance,
                        "score": round(min(score, 1.0), 2),
                        "title_zh": f"论文：{item.get('title', '')}",
                        "summary_zh": "这是本地离线 stub 生成的中文摘要，用于测试和 dry-run。",
                        "reason_zh": "这是本地离线 stub 生成的中文推荐理由，用于测试和 dry-run。",
                        "matched_topics": (
                            ["pentagonal materials", "COF/MOF"]
                            if relevance in {"high", "medium"}
                            else []
                        ),
                    }
                )
            return json.dumps({"papers": ranked}, ensure_ascii=False)
        return "{}"

    def complete_json(self, prompt: str) -> dict[str, Any]:
        return extract_json_object(self.complete(prompt))


def _extract_papers(prompt: str) -> list[dict[str, Any]]:
    marker = "PAPERS_JSON:"
    start = prompt.find(marker)
    if start == -1:
        return []
    raw = prompt[start + len(marker) :].strip()
    match = re.search(r"(\[.*\])", raw, flags=re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
