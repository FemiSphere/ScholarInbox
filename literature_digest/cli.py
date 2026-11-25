from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from threading import RLock, Timer
from collections import Counter
from dataclasses import replace
import re

from .config import load_config, resolve_path as _resolve_path
from .dedupe import deduplicate_entries
from .digest import prune_old_digests, write_digests
from .email_filter import classify_email
from .env import load_dotenv_file
from .gmail_client import GmailConnectionError, GmailClient
from .interests import (
    analyze_research_interests,
    fallback_interest_profile,
    load_or_analyze_research_interests,
    profile_to_json,
    read_research_interests,
)
from .llm import build_llm_client
from .housekeeping import prune_old_logs
from .result_cache import ResultCache, ResultCacheError, analysis_key, translation_key
from .models import RELEVANCE_LABELS, RELEVANCE_LEVELS, DigestRun, RunStats, SkippedEmail
from .parsers import parse_emails
from .paper_registry import (
    PaperRegistry,
    PaperRegistryError,
    bootstrap_registry_from_markdown,
)
from .ranking import count_relevance, rank_papers, ranked_from_analysis, translate_ranked_papers
from .enrichment import enrich_ranked_papers
from urllib.parse import urlsplit
from .sample_data import sample_emails
from .telemetry import RunMetrics
from .ui import ProgressReporter


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"init", "doctor"}:
        from .setup_wizard import run_doctor, run_init
        try:
            return (run_init if arguments[0] == "init" else run_doctor)(arguments[1:])
        except (KeyboardInterrupt, EOFError):
            print("\n已取消。", file=sys.stderr)
            return 130
    metrics = RunMetrics()
    resources: dict[str, Any] = {}
    outcome = "failed"
    try:
        result = _main(argv, metrics, resources)
        outcome = "completed" if result == 0 else "failed"
        return result
    except KeyboardInterrupt:
        timed_out = resources.get("deadline_reached", False)
        outcome = "timed_out" if timed_out else "cancelled"
        metrics.cancel_event.set()
        message = ("运行已达到总等待预算" if timed_out else "已中断") + "：已保留解析缓存和请求日志。"
        if "progress" in resources:
            resources["progress"].error(message)
        else:
            print(message, file=sys.stderr)
        return 124 if timed_out else 130
    finally:
        if outcome != "completed":
            metrics.cancel_event.set()
        if "deadline_timer" in resources:
            resources["deadline_timer"].cancel()
        metrics.event("run_finished", status=outcome)
        if outcome != "completed" and "config" in resources:
            target = _write_detailed_metrics_log(metrics, base_dir=Path.cwd(),
                config=resources["config"].get("telemetry", {}))
            if target:
                if "progress" in resources:
                    resources["progress"].detail(f"Partial request metrics: {target}")
                else:
                    print(f"请求指标：{target}", file=sys.stderr)
        if "progress" in resources:
            reporter = resources["progress"]
            if outcome != "completed" and reporter.run_log_path is not None:
                reporter.output(f"日志：{reporter.run_log_path}", style="dim")
            reporter.close()


def _main(argv: list[str] | None, metrics: RunMetrics, resources: dict[str, Any]) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    base_dir = Path.cwd()
    load_dotenv_file(base_dir / ".env")
    config = load_config(args.config)
    resources["config"] = config
    telemetry_config = config.get("telemetry", {})
    if telemetry_config.get("detailed_log_enabled", True):
        journal_dir = _resolve_path(telemetry_config.get("log_dir", "logs/metrics"), base_dir)
        metrics.configure_journal(journal_dir / f"requests-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.jsonl")
    ui_config = config.get("ui", {})
    progress = ProgressReporter(
        enabled=bool(config.get("progress", {}).get("enabled", True)) and not args.quiet,
        show_timestamps=bool(config.get("progress", {}).get("show_timestamps", True)),
        color_enabled=bool(ui_config.get("color_enabled", True)) and not args.no_color,
        run_log_path=os.environ.get("LITERATURE_DIGEST_RUN_LOG") or
            base_dir / "logs" / f"digest-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.log",
    )

    resources["progress"] = progress
    output_lock = RLock()
    # Core fallbacks (extraction / ranking) keep mail unread; translation-only fallbacks do not,
    # because ratings are intact and the paper is still shown with its original title.
    fallback_count = 0
    translation_fallback_count = 0
    fallback_reasons: Counter[str] = Counter()
    def report_detail(message: str) -> None:
        nonlocal fallback_count, translation_fallback_count
        with output_lock:
            progress.detail(message)
            if "回退本地规则" in message:
                if message.startswith("论文翻译"):
                    translation_fallback_count += 1
                    return
                fallback_count += 1
                match = re.search(r"code=([a-z0-9_]+)", message)
                fallback_reasons[match.group(1) if match else "llm_error"] += 1

    def report_items(current: int, total: int, message: str) -> None:
        if not metrics.cancel_event.is_set():
            progress.item(current, total, message)
    def report_request_event(name: str, fields: dict[str, Any]) -> None:
        if metrics.cancel_event.is_set():
            return
        if name in {"llm_request_started", "llm_retry_wait", "llm_json_repair", "llm_budget_exhausted"}:
            report_detail("API " + name.removeprefix("llm_") + "：" +
                "，".join(f"{key}={value}" for key, value in fields.items()))
        elif name == "llm_request_finished" and fields.get("status") != "ok":
            report_detail(f"API 请求失败：{fields.get('operation')}，{fields.get('status')}，耗时 {fields.get('elapsed_seconds', 0):.1f}s")
    metrics.event_callback = report_request_event
    run_timeout = float(config.get("performance", {}).get("run_timeout_seconds", 600))
    if run_timeout > 0:
        def expire_run() -> None:
            resources["deadline_reached"] = True
            metrics.event("run_budget_exhausted", seconds=run_timeout)
            metrics.cancel_event.set()
        timer = Timer(run_timeout, expire_run)
        timer.daemon = True
        resources["deadline_timer"] = timer
        timer.start()
    dry_run = _resolve_dry_run(args, config)
    if args.max_emails is not None:
        config["gmail"]["max_emails_per_run"] = args.max_emails

    if args.reauth_gmail:
        progress.banner(
            provider="Gmail OAuth",
            mode="重新授权",
            show_banner=bool(ui_config.get("banner_enabled", True)),
        display_name=str(ui_config.get("display_name") or ""),
        )
        progress.step("开始重新授权 Gmail OAuth")
        gmail = GmailClient(config, base_dir=base_dir, metrics=metrics)
        try:
            token_path = gmail.reauthorize()
        except GmailConnectionError as exc:
            progress.error(f"Error: {exc}")
            progress.close()
            return 2
        progress.done(f"Gmail OAuth 重新授权完成：{token_path}")
        progress.close()
        return 0

    sample_mode, warnings = _should_use_sample(args, config, dry_run, base_dir)
    progress.banner(
        provider=_ui_provider_label(config, sample_mode=sample_mode),
        mode=_ui_run_mode(sample_mode=sample_mode, dry_run=dry_run),
        show_banner=bool(ui_config.get("banner_enabled", True)),
        display_name=str(ui_config.get("display_name") or ""),
    )
    progress.detail("初始化完成")

    if sample_mode:
        progress.step("读取内置样例邮件")
        emails = sample_emails()
        unread_estimate = None
    else:
        progress.step("读取 Gmail 未读邮件")
        progress.detail(
            f"搜索 Gmail 未读邮件，query={config['gmail'].get('query', 'is:unread')!r}，"
            f"max={config['gmail']['max_emails_per_run']}"
        )
        gmail = GmailClient(config, base_dir=base_dir, metrics=metrics)
        try:
            emails = gmail.fetch_unread_emails(max_results=config["gmail"]["max_emails_per_run"])
        except GmailConnectionError as exc:
            progress.error(f"Error: {exc}")
            progress.close()
            return 2
        unread_estimate = gmail.last_result_size_estimate
    if unread_estimate is None:
        progress.detail(f"邮件读取完成：{len(emails)} 封")
    else:
        progress.detail(
            f"邮箱中符合当前查询条件的未读邮件约 {unread_estimate} 封；"
            f"本次读取 {len(emails)} 封"
        )

    if not emails:
        progress.done("需要提取的邮件为 0，无需进行后续处理")
        progress.close()
        return 0

    llm = build_llm_client(config, sample_mode=sample_mode, metrics=metrics)

    skipped: list[SkippedEmail] = []
    accepted = []
    progress.item(0, len(emails), "筛选学术邮件")
    for index, email in enumerate(emails, start=1):
        progress.detail(f"过滤邮件 {index}/{len(emails)}：{_shorten(email.subject, 58)}")
        progress.item(index, len(emails), "筛选学术邮件")
        decision = classify_email(email, config)
        if decision.skip:
            skipped.append(
                SkippedEmail(
                    email_id=email.id,
                    subject=email.subject,
                    sender=email.sender,
                    reason=decision.reason,
                )
            )
        else:
            accepted.append(email)
    progress.detail(f"邮件过滤完成：保留 {len(accepted)} 封，跳过 {len(skipped)} 封")

    progress.item(0, len(accepted), "解析论文条目")
    entries = parse_emails(
        accepted,
        llm=llm,
        progress=lambda current, total: report_items(current, total, "解析论文条目"),
        event_callback=report_detail,
        cancel_event=metrics.cancel_event,
        cache_dir=None if sample_mode or not config["parsing"].get("cache_enabled", True) else
            _resolve_path(config["parsing"].get("cache_dir", "data/cache/email_parsing"), base_dir),
        cache_namespace=_llm_cache_fingerprint(config),
        llm_structure_non_scholar=bool(config["parsing"].get("llm_structure_non_scholar", True)),
        max_workers=int(config["performance"].get("parsing_max_workers", 3)),
        llm_text_max_chars=int(config["performance"].get("email_text_max_chars", 12000)),
        llm_max_links=int(config["performance"].get("email_max_links", 50)),
        llm_max_images=int(config["performance"].get("email_max_images", 20)),
        llm_max_chunk_items=int(config["performance"].get("email_max_chunk_items", 8)),
        llm_max_split_depth=int(config["performance"].get("email_max_split_depth", 4)),
        llm_max_requests_per_email=int(config["performance"].get("email_max_requests_per_email", 32)),
        llm_email_budget_seconds=float(config["performance"].get("email_budget_seconds", 240)),
    )
    progress.detail(f"解析完成：{len(entries)} 个候选条目")

    progress.step("合并重复论文")
    fuzzy_title_threshold = int(config["parsing"].get("fuzzy_title_threshold", 92))
    deduped = deduplicate_entries(
        entries,
        fuzzy_title_threshold=fuzzy_title_threshold,
    )
    progress.detail(
        f"去重完成：保留 {len(deduped.unique_entries)} 个条目，移除 {deduped.duplicates_removed} 个重复项"
    )

    date_label = args.date or datetime.now().strftime("%Y-%m-%d")
    registry_date = _registry_reference_date(date_label)
    candidate_entries = deduped.unique_entries
    registry: PaperRegistry | None = None
    registry_duplicates_removed = 0
    dedupe_config = config.get("deduplication", {})
    if not sample_mode and bool(dedupe_config.get("registry_enabled", True)):
        try:
            registry = PaperRegistry.load(
                _resolve_path(dedupe_config.get("registry_path", "data/paper_registry.json"), base_dir),
                reference_date=registry_date,
                retention_days=int(dedupe_config.get("retention_days", 30)),
                fuzzy_title_threshold=float(dedupe_config.get("fuzzy_title_threshold", 94)),
            )
        except PaperRegistryError as exc:
            progress.error(f"Error: {exc}")
            progress.close()
            return 2
        if not registry.loaded_from_disk and bool(dedupe_config.get("bootstrap_from_outputs", True)):
            history_files, history_entries = bootstrap_registry_from_markdown(
                registry,
                _resolve_path(config["digest"]["output_dir"], base_dir),
                reference_date=registry_date,
            )
            if history_files:
                progress.detail(
                    f"JSON 去重索引首次回填：读取近 {registry.retention_days} 天 "
                    f"{history_files} 个 Markdown，"
                    f"识别 {history_entries} 条历史记录"
                )
        registry_filtered = registry.filter_new(candidate_entries)
        candidate_entries = registry_filtered.unique_entries
        registry_duplicates_removed = registry_filtered.duplicates_removed
        if registry_duplicates_removed:
            reason_text = _format_duplicate_reasons(registry_filtered.reasons)
            warnings.append(
                f"近 {registry.retention_days} 天 JSON 身份索引移除 "
                f"{registry_duplicates_removed} 篇重复论文（{reason_text}）。"
            )
            progress.detail(
                f"跨日期去重完成：移除 {registry_duplicates_removed} 篇（{reason_text}）"
            )

    separate_translation = bool(config["performance"].get("separate_translation", True))
    interests_path = _resolve_path(config["research_interests"]["path"], base_dir)
    example_interests = Path(__file__).resolve().parent.parent / "research_interests.example.md"
    if sample_mode and not interests_path.exists() and example_interests.exists():
        interests_path = example_interests  # the offline demo works on a fresh clone
    try:
        interest_text = read_research_interests(interests_path)
    except FileNotFoundError as exc:
        progress.error(f"Error: {exc}")
        progress.close()
        return 2
    if candidate_entries:
        progress.step("准备研究兴趣画像")
        interest_config = config["research_interests"]
        if sample_mode:
            interest_profile = analyze_research_interests(interest_text, llm)
            cache_hit = False
        else:
            interest_profile, cache_hit = load_or_analyze_research_interests(
                interest_text,
                llm,
                cache_path=_resolve_path(
                    interest_config.get("cache_path", "data/cache/research_interests.json"),
                    base_dir,
                ),
                model_fingerprint=_llm_cache_fingerprint(config),
                refresh=bool(interest_config.get("refresh_each_run", False)),
            )
        if sample_mode:
            progress.detail("样例模式使用离线研究兴趣画像，不读写生产缓存")
        elif cache_hit:
            progress.detail("近期研究兴趣画像命中本地缓存")
        else:
            progress.detail("近期研究兴趣画像已更新")
        api_config = config.get("llm", {}).get("openai_compatible", {})
        enrichment_enabled = (
            not sample_mode and config.get("web_enrichment", {}).get("enabled", True)
            and config["llm"].get("provider") == "openai_compatible"
            and urlsplit(api_config.get("base_url", "")).hostname == "api.deepseek.com"
        )
        result_cache = None if sample_mode else _open_result_cache(config, base_dir, progress)
        resources["result_cache"] = result_cache
        model_fingerprint = _llm_cache_fingerprint(config)
        profile_fingerprint = hashlib.sha256(profile_to_json(interest_profile).encode("utf-8")).hexdigest()
        cached_ranked, to_rank = [], []
        for entry in candidate_entries:
            hit = result_cache.get_analysis(analysis_key(entry, profile_fingerprint, model_fingerprint)) if result_cache else None
            if hit is None:
                to_rank.append(entry)
            else:
                cached_ranked.append(ranked_from_analysis(entry, hit))
        if cached_ranked:
            progress.detail(f"评级结果缓存命中 {len(cached_ranked)} 篇，仅需分析 {len(to_rank)} 篇")
        progress.detail(f"调用 LLM 分批评级：{len(to_rank)} 篇论文")
        batch_size = int(config["performance"].get("ranking_batch_size", 10))
        progress.item(0, (len(to_rank) + batch_size - 1) // batch_size, "论文相关性评级")
        ranked = rank_papers(
            to_rank,
            interest_profile,
            llm,
            batch_size=batch_size,
            analysis_only=enrichment_enabled or separate_translation,
            separate_translation=separate_translation,
            abstract_max_chars=int(config["performance"].get("ranking_abstract_max_chars", 2000)),
            max_workers=int(config["performance"].get("ranking_max_workers", 3)),
            progress=lambda current, total: report_items(current, total, "论文相关性评级"),
            event_callback=report_detail,
            cancel_event=metrics.cancel_event,
        ) if to_rank else []
        if result_cache is not None:
            result_cache.put_analyses([(analysis_key(paper.entry, profile_fingerprint, model_fingerprint), paper)
                                       for paper in ranked])
        ranked = sorted(cached_ranked + ranked, key=lambda paper: paper.score, reverse=True)
        if enrichment_enabled:
            if not fallback_count:
                try:
                    ranked = enrich_ranked_papers(
                        ranked, interest_profile, llm, config, base_dir=base_dir,
                        metrics=metrics, cancel_event=metrics.cancel_event,
                        progress=lambda label, current, total: report_items(current, total, label),
                        detail=progress.detail,
                    )
                except Exception as exc:
                    # Optional source enrichment must not invalidate core processing.
                    metrics.event("web_enrichment_unavailable", reason=type(exc).__name__)
                    progress.detail(f"联网摘要补充未完成，保留初筛结果：{type(exc).__name__}")
            else:
                progress.detail("核心提取或初筛出现回退，本次跳过可选联网补充")
        progress.detail("LLM 评级完成")
    else:
        if deduped.unique_entries and registry_duplicates_removed:
            retention_days = registry.retention_days if registry is not None else 30
            warnings.append(
                f"本次候选论文均已在近 {retention_days} 天 JSON 身份索引中出现，因此生成空 digest。"
            )
        else:
            warnings.append("没有找到可处理的未读论文条目，本次生成空 digest。")
        interest_profile = fallback_interest_profile(interest_text)
        ranked = []

    if not config["digest"].get("include_low_relevance", True):
        ranked = [paper for paper in ranked if paper.relevance != "low"]
    if not config["digest"].get("include_off_topic", True):
        ranked = [paper for paper in ranked if paper.relevance != "off_topic"]
    if not config["digest"].get("include_irrelevant", True):
        ranked = [paper for paper in ranked if paper.relevance != "irrelevant"]

    stats = RunStats(
        emails_read=len(emails),
        skipped_emails=len(skipped),
        paper_entries_extracted=len(entries),
        duplicates_removed=deduped.duplicates_removed + registry_duplicates_removed,
        high_relevance=count_relevance(ranked, "high"),
        medium_relevance=count_relevance(ranked, "medium"),
        low_relevance=count_relevance(ranked, "low"),
        off_topic=count_relevance(ranked, "off_topic"),
        irrelevant=count_relevance(ranked, "irrelevant"),
        sample_mode=sample_mode,
    )
    if fallback_count:
        warnings.append(f"本次 {fallback_count} 项 LLM 任务失败，部分条目或推荐使用本地规则回退；请根据日志中的具体原因修复后重跑；邮件提取回退可能遗漏条目。")
    displayed = _apply_digest_limits(ranked, config)
    omitted_note = _omitted_by_limits_note(ranked, displayed)
    if omitted_note:
        warnings.append(omitted_note)
    if separate_translation and displayed:
        # Translate only what the digest shows; papers hidden by digest.max_* are not paid for.
        displayed = _translate_displayed(
            displayed, llm, config, resources.get("result_cache"), progress,
            progress_callback=lambda current, total: report_items(current, total, "生成中文阅读摘要"),
            event_callback=report_detail, cancel_event=metrics.cancel_event,
        )
        progress.detail("中文标题与概述完成")
    if translation_fallback_count:
        warnings.append(f"本次 {translation_fallback_count} 批中文翻译未完整完成，相关论文显示原英文标题或占位概述；"
                        "评级不受影响，邮件按正常流程处理。")
    run = DigestRun(
        date_label=date_label,
        stats=stats,
        interest_profile=interest_profile,
        papers=displayed,
        skipped=skipped if config["filtering"].get("audit_skipped_emails", True) else [],
        warnings=warnings,
    )
    if metrics.cancel_event.is_set():
        raise KeyboardInterrupt
    progress.step("保存文献日报")
    output_dir = _resolve_path(config["digest"]["output_dir"], base_dir)
    output_paths = write_digests(
        run,
        output_dir,
        formats=list(config["digest"]["output_formats"]),
        overwrite_existing=bool(config["digest"].get("overwrite_existing", True)),
        theme=str(config["digest"].get("theme", "pop")),
    )

    if registry is not None and not dry_run and not fallback_count:
        progress.detail(f"更新近 {registry.retention_days} 天 JSON 论文身份索引")
        registry.record_entries(entries, seen_on=registry_date)
        try:
            registry.save(reference_date=registry_date)
        except PaperRegistryError as exc:
            progress.error(f"Error: {exc}")
            progress.close()
            return 2

    marked_read = 0
    if not dry_run and not sample_mode and not fallback_count and config["gmail"].get("mark_as_read", False):
        read_ids = [email.id for email in accepted]
        if config["filtering"].get("mark_skipped_as_read", False):
            # Skipped mail is listed in the digest for audit; without this it stays
            # unread forever and occupies max_emails_per_run on every later run.
            read_ids += [item.email_id for item in skipped]
        progress.step(f"标记已处理邮件为已读：{len(read_ids)} 封")
        gmail = GmailClient(config, base_dir=base_dir, metrics=metrics)
        try:
            gmail.mark_as_read(read_ids)
        except GmailConnectionError as exc:
            progress.error(f"Error: {exc}")
            progress.close()
            return 2
        marked_read = len(read_ids)

    cache = resources.get("result_cache")
    if cache is not None:
        if not dry_run and not fallback_count:
            cache.clear()  # these papers are now in the registry and will not come back
        cache.close()

    if (output_paths and config["digest"].get("cleanup_old_outputs", False)
            and not dry_run and not sample_mode and not fallback_count
            and not metrics.cancel_event.is_set()):
        try:
            removed, failed = prune_old_digests(output_dir, today=date.today(), protected=output_paths)
        except OSError as exc:
            progress.detail(f"无法扫描日报输出目录：{type(exc).__name__}")
        else:
            progress.detail(f"已清理超过 60 天的日报：{removed} 个")
            for name in failed:
                progress.detail(f"无法清理旧日报：{name}")

    progress.done("文献日报已生成")
    verified = sum(1 for paper in ranked if paper.evidence is not None)
    facts = [f"邮件 {stats.emails_read} 封", f"新论文 {len(candidate_entries)} 篇"]
    if verified:
        facts.append(f"核验摘要 {verified} 篇")
    progress.summary(
        [("高相关", stats.high_relevance), ("中相关", stats.medium_relevance), ("低相关", stats.low_relevance),
         ("领域外", stats.off_topic), ("不相关", stats.irrelevant)],
        facts,
    )
    progress.detail(
        f"Stats: emails={stats.emails_read}, entries={stats.paper_entries_extracted}, "
        f"duplicates={stats.duplicates_removed}, high={stats.high_relevance}, "
        f"medium={stats.medium_relevance}, low={stats.low_relevance}, "
        f"off_topic={stats.off_topic}, irrelevant={stats.irrelevant}, skipped={stats.skipped_emails}"
    )
    if fallback_count:
        progress.output(f"提示：{fallback_count} 项任务未完整处理，输出包含本地规则回退。", style="yellow")
        labels = {"output_length": "输出超长", "invalid_json": "JSON 格式异常", "invalid_schema": "输出结构不完整", "invalid_response": "响应结构异常",
                  "timeout": "请求超时", "network_error": "网络异常", "budget_exhausted": "处理预算耗尽",
                  "request_limit": "拆分请求达到上限", "llm_error": "提取或生成异常"}
        progress.output("原因：" + "；".join(f"{labels.get(code, code)} {count} 项" for code, count in fallback_reasons.items()), style="yellow")
        if not dry_run and not sample_mode:
            progress.output("邮件保持未读，未更新去重索引；可在问题修复后重跑（已成功的评级与翻译会复用缓存）。", style="yellow")
    elif translation_fallback_count:
        progress.output(f"提示：{translation_fallback_count} 批中文翻译未完整完成，评级正常，邮件已按正常流程处理。", style="yellow")
    for output_path in output_paths:
        progress.output_file(output_path)
    for line in metrics.summary_lines(include_request_details=False):
        progress.detail(line)
    metrics_log_path = _write_detailed_metrics_log(metrics, base_dir=base_dir, config=telemetry_config)
    if metrics_log_path is not None:
        progress.detail(f"Detailed request metrics: {metrics_log_path}")
    if not sample_mode:
        _prune_logs(config, base_dir, progress)
    if dry_run:
        progress.output("预览模式 · 未修改邮件状态", style="dim")
    remaining = _remaining_unread_note(unread_estimate, marked_read)
    if remaining:
        progress.output(remaining, style="cyan")
    if progress.run_log_path is not None:
        progress.output(f"日志：{_display_path(progress.run_log_path)}", style="dim")
    progress.close()
    return 0


def _display_path(path: Path | str) -> str:
    """Project-relative path for terminal display; absolute when outside the working directory."""
    target = Path(path).resolve()
    try:
        return str(target.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(target)


def _remaining_unread_note(unread_estimate: int | None, marked_read: int) -> str:
    """Tell the user how much unread mail is left after this run (Gmail's count is approximate)."""
    if unread_estimate is None:
        return ""
    remaining = max(0, int(unread_estimate) - marked_read)
    if remaining == 0:
        return "邮箱中已无符合条件的未读邮件。"
    return f"邮箱中仍有约 {remaining} 封未读邮件，可再次运行继续处理。"


def _prune_logs(config: dict[str, Any], base_dir: Path, progress: ProgressReporter) -> None:
    telemetry_config = config.get("telemetry", {})
    retention = int(telemetry_config.get("log_retention_days", 30) or 0)
    directories = [base_dir / "logs", _resolve_path(telemetry_config.get("log_dir", "logs/metrics"), base_dir)]
    removed, failed = prune_old_logs(directories, today=date.today(), retention_days=retention)
    if removed:
        progress.detail(f"已清理超过 {retention} 天的日志：{removed} 个")
    for name in failed:
        progress.detail(f"无法清理旧日志：{name}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a daily academic literature digest.",
        epilog="Setup commands: `scholar-inbox init` (guided setup), `scholar-inbox doctor` (offline self-check).",
    )
    parser.add_argument("--config", help="Path to config YAML. Defaults to config.local.yaml if present.")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify Gmail state.")
    parser.add_argument("--no-dry-run", action="store_true", help="Allow configured non-dry-run actions.")
    parser.add_argument("--max-emails", type=int, help="Override gmail.max_emails_per_run.")
    parser.add_argument("--sample", action="store_true", help="Use built-in sample emails.")
    parser.add_argument("--date", help="Override output date label, e.g. 2026-04-28.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages.")
    parser.add_argument("--no-color", action="store_true", help="Disable colors and animations.")
    parser.add_argument("--reauth-gmail", action="store_true", help="Force Gmail OAuth reauthorization.")
    return parser


def _resolve_dry_run(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    if args.no_dry_run:
        return False
    if args.dry_run:
        return True
    return bool(config["safety"].get("dry_run_default", True))


def _should_use_sample(
    args: argparse.Namespace,
    config: dict[str, Any],
    dry_run: bool,
    base_dir: Path,
) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    if args.sample:
        warnings.append("使用内置样例邮件进行 dry-run；未读取真实 Gmail。")
        return True, warnings
    credentials_path = _resolve_path(config["gmail"].get("credentials_path", "credentials.json"), base_dir)
    if (
        dry_run
        and config["safety"].get("allow_sample_without_credentials", True)
        and not credentials_path.exists()
    ):
        warnings.append(
            f"未找到 Gmail OAuth 凭据 {credentials_path}，本次 dry-run 使用内置样例邮件。"
        )
        return True, warnings
    return False, warnings


# Per-level display limit keys and their defaults (None = unlimited).
_DIGEST_LIMITS = {
    "high": ("max_high_relevance", 20),
    "medium": ("max_medium_relevance", 30),
    "low": ("max_low_relevance", None),
    "off_topic": ("max_off_topic", None),
    "irrelevant": ("max_irrelevant", None),
}


def _apply_digest_limits(ranked, config: dict[str, Any]):
    limits = {}
    for level, (key, default) in _DIGEST_LIMITS.items():
        raw = config["digest"].get(key, default)
        limits[level] = None if raw is None else int(raw)
    counts = dict.fromkeys(limits, 0)
    result = []
    for paper in ranked:
        limit = limits.get(paper.relevance)
        if limit is not None and counts[paper.relevance] >= limit:
            continue
        counts[paper.relevance] = counts.get(paper.relevance, 0) + 1
        result.append(paper)
    return result


def _open_result_cache(config: dict[str, Any], base_dir: Path, progress: ProgressReporter) -> ResultCache | None:
    settings = config.get("result_cache", {})
    if not settings.get("enabled", True):
        return None
    try:
        return ResultCache(_resolve_path(settings.get("path", "data/cache/results.sqlite3"), base_dir),
                           ttl_days=float(settings.get("ttl_days", 7)),
                           max_entries=int(settings.get("max_entries", 5000)))
    except (ResultCacheError, ValueError) as exc:
        progress.detail(f"评级/翻译结果缓存不可用，本次不使用：{exc}")
        return None


# Levels shown as compact rows only get a Chinese title (cheap); high/medium get title + summary.
_TITLE_ONLY_LEVELS = {"low", "off_topic", "irrelevant"}
_TITLE_ONLY_BATCH_SIZE = 30


def _translate_displayed(displayed, llm, config: dict[str, Any], cache: ResultCache | None,
                         progress: ProgressReporter, *, progress_callback, event_callback, cancel_event):
    model_fingerprint = _llm_cache_fingerprint(config)
    finished: dict[int, Any] = {}
    groups = {False: [], True: []}
    keys: dict[int, str] = {}
    for paper in displayed:
        title_only = paper.relevance in _TITLE_ONLY_LEVELS
        keys[id(paper)] = translation_key(paper, model_fingerprint, title_only=title_only)
        hit = cache.get_translation(keys[id(paper)], title_only=title_only) if cache is not None else None
        if hit is None:
            groups[title_only].append(paper)
        else:
            finished[id(paper)] = replace(paper, title_zh=hit["title_zh"], summary_zh=hit["summary_zh"], translated=True)
    pending_count = len(groups[False]) + len(groups[True])
    if finished:
        progress.detail(f"翻译结果缓存命中 {len(finished)} 篇，仅需翻译 {pending_count} 篇")
    if pending_count:
        full_batch = int(config["performance"].get("ranking_batch_size", 10))
        total = sum((len(groups[mode]) + size - 1) // size
                    for mode, size in ((False, full_batch), (True, _TITLE_ONLY_BATCH_SIZE)) if groups[mode])
        done = 0

        def report(current: int, _total: int) -> None:
            progress_callback(done + current, total)

        progress.item(0, total, "生成中文阅读摘要")
        for title_only, size in ((False, full_batch), (True, _TITLE_ONLY_BATCH_SIZE)):
            pending = groups[title_only]
            if not pending:
                continue
            translated = translate_ranked_papers(
                pending, llm, batch_size=size, title_only=title_only,
                max_workers=int(config["performance"].get("ranking_max_workers", 3)),
                progress=report, event_callback=event_callback, cancel_event=cancel_event,
            )
            done += (len(pending) + size - 1) // size
            for original, result in zip(pending, translated):
                finished[id(original)] = result
            if cache is not None:
                cache.put_translations([(keys[id(original)], result) for original, result in zip(pending, translated)])
    return [finished[id(paper)] for paper in displayed]


def _omitted_by_limits_note(ranked, displayed) -> str:
    """Say how many ranked papers the digest.max_* limits hid; empty when none."""
    parts = []
    for level in RELEVANCE_LEVELS:
        hidden = count_relevance(ranked, level) - count_relevance(displayed, level)
        if hidden > 0:
            parts.append(f"{RELEVANCE_LABELS[level]} {hidden} 篇")
    if not parts:
        return ""
    return ("受显示数量上限（digest.max_*）限制，以下论文已评级但未在本日报展示：" + "、".join(parts)
            + "。它们仍计入去重索引，之后不会再次出现；如需全部查看，可调大或删除对应上限。")


def _shorten(value: str, max_length: int) -> str:
    text = " ".join((value or "(no subject)").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _llm_cache_fingerprint(config: dict[str, Any]) -> str:
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "")
    provider_config = llm_config.get(provider, {})
    if provider == "openai_compatible":
        provider_config = llm_config.get("openai_compatible", {})
    elif provider == "codex_cli":
        provider_config = llm_config.get("codex_cli", {})
    safe_provider_config = {
        key: value
        for key, value in provider_config.items()
        if key not in {"api_key", "api_key_env"}
    }
    return json.dumps(
        {
            "provider": provider,
            "model": safe_provider_config.get("model") or llm_config.get("model", ""),
            "reasoning_effort": safe_provider_config.get("reasoning_effort")
            or llm_config.get("reasoning_effort", ""),
            "response_format_json": safe_provider_config.get("response_format_json", True),
            "extra_body": safe_provider_config.get("extra_body", {}),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _registry_reference_date(date_label: str) -> date:
    try:
        return date.fromisoformat(date_label)
    except ValueError:
        return date.today()


def _format_duplicate_reasons(reasons: dict[str, int]) -> str:
    labels = {
        "doi": "DOI",
        "arxiv": "arXiv",
        "url": "URL",
        "exact_title": "完全标题",
        "fuzzy_title": "模糊标题",
    }
    return "，".join(f"{labels.get(reason, reason)} {count}" for reason, count in reasons.items())


def _ui_provider_label(config: dict[str, Any], *, sample_mode: bool) -> str:
    if sample_mode:
        return "本地离线模型"
    llm_config = config.get("llm", {})
    provider = str(llm_config.get("provider") or "LLM")
    provider_config = llm_config.get(provider, {})
    if not isinstance(provider_config, dict):
        provider_config = {}
    model = str(provider_config.get("model") or llm_config.get("model") or "").strip()
    labels = {
        "codex_cli": "Codex CLI",
        "openai_compatible": "自定义 API",
    }
    label = labels.get(provider, provider)
    if provider == "openai_compatible":
        base_url = str(provider_config.get("base_url") or "").lower()
        if "deepseek.com" in base_url:
            label = "DeepSeek API"
    return f"{label} · {model}" if model else label


def _ui_run_mode(*, sample_mode: bool, dry_run: bool) -> str:
    if sample_mode:
        return "样例 dry-run"
    return "dry-run" if dry_run else "正式运行"


def _write_detailed_metrics_log(
    metrics: RunMetrics,
    *,
    base_dir: Path,
    config: dict[str, Any],
) -> Path | None:
    if not bool(config.get("detailed_log_enabled", True)):
        return None
    lines = metrics.summary_lines(include_request_details=True)
    if not lines:
        return None
    log_dir = _resolve_path(config.get("log_dir", "logs/metrics"), base_dir)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = log_dir / f"metrics-{timestamp}.log"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not write detailed metrics log: {exc}", file=sys.stderr)
        return None
    return target
