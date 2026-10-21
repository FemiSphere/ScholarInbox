"""Optional, bounded abstract enrichment; never persists fetched pages or run intermediates."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable

from .concurrency import cooperative_map
from .dedupe import normalize_doi, normalize_title, canonicalize_url
from .evidence_cache import EvidenceCache, CacheError
from .llm.base import llm_time_budget
from .models import EvidenceRecord, RankedPaper
from .ranking import rank_papers
from .web_evidence import WebEvidenceClient, acquire_evidence


class _OptionalTaskCancel(Event):
    """Observe the run cancellation without propagating an optional task failure."""
    def __init__(self, parent: Event):
        super().__init__()
        self.parent = parent

    def is_set(self):
        return self.parent.is_set() or super().is_set()


def evidence_key(entry) -> str:
    doi = normalize_doi(entry.doi)
    identity = 'doi:' + doi if doi else normalize_title(entry.title) + '|' + canonicalize_url(entry.url)
    return sha256(('evidence-v1|' + identity).encode()).hexdigest()


def _cached_evidence(record):
    if not isinstance(record, dict) or record.get('status') != 'verified':
        return None
    data = record.get('evidence')
    if not isinstance(data, dict):
        return None
    try:
        evidence = EvidenceRecord(**data)
        if (all(isinstance(value, str) for value in asdict(evidence).values())
                and evidence.source_kind in {'publisher_abstract', 'preprint_abstract', 'repository_abstract'}
                and 80 <= len(evidence.abstract) <= 12000
                and evidence.source_url.startswith(('https://', 'http://'))):
            return evidence
    except (TypeError, ValueError):
        pass
    return None


def enrich_ranked_papers(papers: list[RankedPaper], profile, llm, config: dict, *,
                         base_dir: Path, metrics=None, cancel_event: Event | None = None,
                         progress: Callable[[str, int, int], None] | None = None,
                         detail: Callable[[str], None] | None = None,
                         client=None) -> list[RankedPaper]:
    """Keep original results on optional failure; only verified abstracts reach reranking."""
    options = config.get('web_enrichment', {})
    targets = [paper for paper in papers if paper.relevance in {'high', 'medium'}]
    targets.sort(key=lambda paper: (paper.relevance != 'high', -paper.score))
    targets = targets[:max(0, int(options.get('max_papers', 30)))]
    if not targets:
        return papers
    started = monotonic()
    deadline = started + max(0.0, float(options.get('budget_seconds', 180)))
    cancel = cancel_event if cancel_event is not None else Event()
    def log(event, **fields):
        if metrics is not None:
            metrics.event(event, **fields)
        if detail:
            detail(event + ': ' + ', '.join(f'{key}={value}' for key, value in fields.items()))
    def check_cancel():
        if cancel.is_set():
            raise KeyboardInterrupt
    api = config.get('llm', {}).get('openai_compatible', {})
    client = client or WebEvidenceClient(
        base_url='https://api.deepseek.com', api_key_env=api.get('api_key_env', 'DEEPSEEK_API_KEY'),
        metrics=metrics, cancel_event=cancel,
        timeout_seconds=float(options.get('request_timeout_seconds', 12)),
        budget_seconds=min(float(options.get('retrieval_budget_seconds', 90)), max(0, deadline - monotonic())),
        max_requests=int(options.get('max_requests', 80)),
        search_count=3, min_interval_seconds=0.5,
    )
    cache = None
    if options.get('cache_enabled', True):
        path = Path(options.get('cache_path', 'data/cache/web_evidence.sqlite3'))
        if not path.is_absolute():
            path = base_dir / path
        try:
            cache = EvidenceCache(path,
                max_entries=int(options.get('cache_max_entries', 300)),
                max_bytes=int(options.get('cache_max_bytes', 8 * 1024 * 1024)),
                ttl_days=float(options.get('cache_ttl_days', 30)), negative_ttl_hours=6)
        except (CacheError, OSError, ValueError):
            log('web_cache_unavailable')
    log('web_enrichment_started', candidates=len(targets), budget_seconds=options.get('budget_seconds', 180))
    try:
        if progress:
            progress('补充论文摘要', 0, len(targets))
        def acquire(paper):
            check_cancel()
            key = evidence_key(paper.entry)
            if monotonic() >= deadline:
                return None
            if cache is not None:
                try:
                    record = cache.get(key)
                    evidence = _cached_evidence(record)
                    if evidence is not None:
                        log('web_cache_hit', paper=key[:12])
                        return evidence
                    if isinstance(record, dict) and record.get('status') == 'missing':
                        return None
                except (CacheError, OSError):
                    log('web_cache_read_failed')
            try:
                with llm_time_budget(max(0, deadline - monotonic())):
                    evidence = acquire_evidence(paper.entry, client, llm)
            except Exception as exc:
                # Optional errors never enter the core fallback/read-state signal.
                code = getattr(exc, 'code', type(exc).__name__)
                log('web_evidence_unavailable', paper=key[:12], reason=str(code)[:64])
                return None
            check_cancel()
            if evidence is not None and not isinstance(evidence, EvidenceRecord):
                log('web_evidence_invalid', paper=key[:12])
                return None
            if cache is not None:
                try:
                    cache.put(key, {'status': 'verified', 'evidence': asdict(evidence)} if evidence else
                              {'status': 'missing'}, negative=evidence is None)
                except (CacheError, OSError):
                    log('web_cache_write_failed')
            return evidence
        evidence_list = cooperative_map(acquire, targets,
            max_workers=max(1, min(3, int(options.get('max_workers', 3)))),
            thread_name_prefix='abstract-enrichment', cancel_event=cancel,
            progress=(lambda current, total: progress('补充论文摘要', current, total)) if progress else None)
        supported = [(paper, evidence) for paper, evidence in zip(targets, evidence_list) if evidence is not None]
        replacements = {}
        batch_size = max(1, min(10, int(config.get('performance', {}).get('ranking_batch_size', 10))))
        total_batches = (len(supported) + batch_size - 1) // batch_size
        if total_batches and progress:
            progress('复评论文相关性', 0, total_batches)
        for batch_index, offset in enumerate(range(0, len(supported), batch_size), 1):
            check_cancel()
            if monotonic() >= deadline:
                log('web_refinement_budget_exhausted')
                break
            batch = supported[offset:offset + batch_size]
            events = []
            try:
                with llm_time_budget(max(0, deadline - monotonic())):
                    refined = rank_papers([paper.entry for paper, _ in batch], profile, llm,
                        batch_size=batch_size, max_workers=1, analysis_only=True,
                        evidence_by_index={i: evidence for i, (_, evidence) in enumerate(batch)},
                        cancel_event=_OptionalTaskCancel(cancel), event_callback=events.append)
                if events or len(refined) != len(batch):
                    log('web_refinement_unavailable', batch=batch_index)
                else:
                    originals = {evidence_key(paper.entry): paper for paper, _ in batch}
                    for updated in refined:
                        key = evidence_key(updated.entry)
                        if key in originals:
                            replacements[key] = updated
                            log('web_refinement_completed', paper=key[:12],
                                initial=originals[key].relevance, final=updated.relevance)
            except Exception as exc:
                log('web_refinement_unavailable', batch=batch_index, reason=type(exc).__name__)
            if progress:
                progress('复评论文相关性', batch_index, total_batches)
        log('web_enrichment_finished', selected=len(targets), abstracts=len(supported),
            refined=len(replacements), elapsed_seconds=round(monotonic() - started, 2))
        return sorted([replacements.get(evidence_key(paper.entry), paper) for paper in papers],
                      key=lambda paper: paper.score, reverse=True)
    finally:
        if cache is not None:
            try:
                cache.close()
            except (CacheError, OSError):
                log('web_cache_close_failed')
