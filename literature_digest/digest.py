from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

from .models import DigestRun, RankedPaper


def write_digest(run: DigestRun, output_dir: str | Path) -> Path:
    """Backward-compatible Markdown-only writer."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{run.date_label}-digest.md"
    target.write_text(render_markdown(run), encoding="utf-8")
    return target


def write_digests(
    run: DigestRun,
    output_dir: str | Path,
    formats: list[str] | None = None,
    *,
    overwrite_existing: bool = True,
) -> list[Path]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    selected = [item.lower() for item in (formats or ["md", "html"])]
    extensions = _selected_extensions(selected)
    stem = _unique_output_stem(target_dir, f"{run.date_label}-digest", extensions, overwrite_existing)
    written: list[Path] = []

    if "md" in selected or "markdown" in selected:
        markdown_path = target_dir / f"{stem}.md"
        markdown_path.write_text(render_markdown(run), encoding="utf-8")
        written.append(markdown_path)

    if "html" in selected:
        html_path = target_dir / f"{stem}.html"
        # The BOM keeps the page readable in viewers that ignore the HTML meta tag
        # when a local file is opened directly. Browsers still treat it as UTF-8.
        html_path.write_text(render_html(run, target_dir), encoding="utf-8-sig")
        written.append(html_path)

    return written


def render_markdown(run: DigestRun) -> str:
    lines: list[str] = []
    lines.append(f"# 科研文献摘要 - {run.date_label}")
    lines.append("")
    if run.warnings:
        lines.append("## 运行提示")
        lines.extend(f"- {warning}" for warning in run.warnings)
        lines.append("")

    stats = run.stats
    lines.append("## 总体统计")
    lines.append(f"- 邮件读取数：{stats.emails_read}")
    lines.append(f"- 跳过无用邮件：{stats.skipped_emails}")
    lines.append(f"- 提取论文条目：{stats.paper_entries_extracted}")
    lines.append(f"- 去重移除：{stats.duplicates_removed}")
    lines.append(f"- 高相关论文：{stats.high_relevance}")
    lines.append(f"- 中相关论文：{stats.medium_relevance}")
    lines.append(f"- 低相关论文：{stats.low_relevance}")
    lines.append(f"- 不相关条目：{stats.irrelevant}")
    lines.append(f"- 样例模式：{'是' if stats.sample_mode else '否'}")
    lines.append("")

    lines.append("## 近期研究兴趣摘要")
    lines.append(run.interest_profile.summary_zh or "未生成研究兴趣摘要。")
    lines.append("")
    if run.interest_profile.high_priority_topics:
        lines.append("高优先级主题：" + "；".join(run.interest_profile.high_priority_topics))
        lines.append("")

    _append_markdown_section(lines, "高相关论文", [paper for paper in run.papers if paper.relevance == "high"])
    _append_markdown_section(lines, "中相关论文", [paper for paper in run.papers if paper.relevance == "medium"])
    _append_markdown_section(lines, "低相关论文", [paper for paper in run.papers if paper.relevance == "low"], short=True)
    _append_markdown_section(
        lines,
        "不相关",
        [paper for paper in run.papers if paper.relevance == "irrelevant"],
        short=True,
    )

    if run.skipped:
        lines.append("## 跳过的邮件")
        for skipped in run.skipped:
            lines.append(f"- {skipped.subject} | {skipped.sender} | {skipped.reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _selected_extensions(selected: list[str]) -> list[str]:
    extensions: list[str] = []
    if "md" in selected or "markdown" in selected:
        extensions.append(".md")
    if "html" in selected:
        extensions.append(".html")
    return extensions


def _unique_output_stem(
    output_dir: Path,
    base_stem: str,
    extensions: list[str],
    overwrite_existing: bool,
) -> str:
    if overwrite_existing or not extensions:
        return base_stem
    if not any((output_dir / f"{base_stem}{extension}").exists() for extension in extensions):
        return base_stem
    for index in range(2, 10000):
        candidate = f"{base_stem}-{index}"
        if not any((output_dir / f"{candidate}{extension}").exists() for extension in extensions):
            return candidate
    raise RuntimeError(f"Could not find an available output filename for {base_stem}")


def render_html(run: DigestRun, output_dir: str | Path | None = None) -> str:
    stats = run.stats
    levels = ("high", "medium", "low", "irrelevant")
    papers_by_level = {
        level: [paper for paper in run.papers if paper.relevance == level]
        for level in levels
    }
    displayed_counts = {level: len(papers_by_level[level]) for level in levels}
    warnings = "".join(f"<li>{escape(warning)}</li>" for warning in run.warnings)
    high_topics = run.interest_profile.high_priority_topics
    high_topic_html = "".join(f"<span>{escape(topic)}</span>" for topic in high_topics)
    paper_indices = {id(paper): index for index, paper in enumerate(run.papers, 1)}
    paper_sections = "\n".join(
        _render_paper_section(level, papers_by_level[level], paper_indices, output_dir)
        for level in levels
        if papers_by_level[level]
    )
    skipped_items = "".join(
        f"<li><strong>{escape(item.subject)}</strong><span>{escape(item.sender)}</span><em>{escape(item.reason)}</em></li>"
        for item in run.skipped
    )
    data = {
        **displayed_counts,
        "total": len(run.papers),
    }
    digest_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>科研文献摘要 - {escape(run.date_label)}</title>
  <style>
    :root {{
      --bg: #f3f5fa;
      --surface: #fafdff;
      --surface-strong: #ffffff;
      --text: #18243b;
      --muted: #63718a;
      --border: #dfe5ef;
      --accent: #365bd6;
      --accent-strong: #2946a6;
      --accent-soft: #edf1ff;
      --amber: #b7791f;
      --rose: #b04436;
      --slate: #607083;
      --high: #365bd6;
      --medium: #087b89;
      --low: #607083;
      --irrelevant: #777b82;
      --irrelevant-soft: #f0f1f2;
      --shadow: 0 12px 32px rgba(30, 50, 90, 0.09);
      --shadow-soft: 0 2px 8px rgba(30, 50, 90, 0.035);
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        linear-gradient(180deg, #eaf0fa 0%, transparent 600px),
        var(--bg);
      color: var(--text);
      line-height: 1.65;
    }}
    a {{ color: var(--accent-strong); text-decoration-thickness: 1px; text-underline-offset: 3px; }}
    header {{
      padding: 48px 0 38px;
      color: #f4f7ff;
      border-bottom: 1px solid #263859;
      background:
        radial-gradient(ellipse at 90% 0%, rgba(54, 91, 214, .32), transparent 55%),
        radial-gradient(ellipse at 10% 100%, rgba(8, 123, 137, .16), transparent 50%),
        #101b30;
    }}
    .shell {{ width: min(1180px, calc(100vw - 32px)); margin: 0 auto; }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      gap: 28px;
    }}
    h1 {{ margin: 0 0 10px; font-size: 38px; line-height: 1.15; font-weight: 760; letter-spacing: 0; }}
    .subtitle {{ margin: 0; color: #aabbd5; font-size: 14px; }}
    .hero-summary {{
      display: grid;
      grid-template-columns: repeat(3, minmax(76px, 1fr));
      gap: 8px;
      min-width: 290px;
    }}
    .hero-summary div {{
      border: 1px solid rgba(171, 195, 239, .18);
      background: rgba(255, 255, 255, .045);
      border-radius: 8px;
      padding: 10px 12px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04);
    }}
    .hero-summary strong {{ display: block; font-size: 28px; line-height: 1.1; font-weight: 550; font-variant-numeric: tabular-nums; }}
    .hero-summary span {{ display: block; margin-top: 7px; color: #aabbd5; font-size: 12px; }}
    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(243, 245, 250, 0.96);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
      padding: 14px 0;
    }}
    .toolbar-row {{ display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: center; }}
    input[type="search"] {{
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0 15px;
      background: var(--surface-strong);
      color: var(--text);
      font-size: 14px;
      outline: none;
    }}
    input[type="search"]:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12); }}
    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    button {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface-strong);
      color: var(--text);
      min-height: 40px;
      padding: 0 13px;
      font-size: 14px;
      cursor: pointer;
      transition: border-color 140ms ease, background 140ms ease, color 140ms ease, transform 140ms ease;
    }}
    button:hover {{ transform: translateY(-1px); border-color: rgba(19, 117, 109, 0.38); }}
    button[aria-pressed="true"] {{ background: var(--accent); border-color: var(--accent); color: white; }}
    .secondary-actions button {{
      color: var(--accent-strong);
      background: #f8fbfa;
    }}
    main {{ padding: 28px 0 56px; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(7, minmax(110px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .stat {{
      background: rgba(255, 255, 255, 0.86);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      min-height: 74px;
      box-shadow: var(--shadow-soft);
    }}
    .stat strong {{ display: block; font-size: 25px; line-height: 1.1; color: var(--accent-strong); }}
    .stat span {{ color: var(--muted); font-size: 13px; }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: var(--shadow-soft);
    }}
    .panel h2, .section-title {{ margin: 0 0 12px; font-size: 20px; line-height: 1.3; }}
    .topics {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .topics span, .tag {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 650;
    }}
    .paper-list {{ display: grid; gap: 18px; }}
    .paper-card {{
      background: var(--surface-strong);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px 20px 18px;
      box-shadow: var(--shadow-soft);
      transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
    }}
    .paper-card:hover {{ transform: translateY(-2px); box-shadow: var(--shadow); border-color: rgba(19, 117, 109, 0.24); }}
    .paper-card[data-level="irrelevant"] {{ background: #fafafa; }}
    .paper-top {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
    .paper-card h3 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.35; letter-spacing: 0; overflow-wrap: anywhere; }}
    .meta {{ margin: 0 0 10px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }}
    .venue {{
      display: inline-flex;
      width: fit-content;
      margin: 0 0 10px;
      padding: 4px 9px;
      border-radius: 8px;
      background: #eef6f3;
      color: var(--accent-strong);
      font-size: 13px;
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .score {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      flex: 0 0 auto;
      border-radius: 999px;
      border: 1px solid var(--border);
      padding: 6px 11px;
      color: var(--text);
      font-size: 13px;
      font-weight: 700;
      background: #faf8f2;
      white-space: nowrap;
    }}
    .score::before {{ content: ""; width: 5px; height: 5px; flex: 0 0 5px; border-radius: 50%; background: currentColor; }}
    .paper-card[data-level="high"] .score {{ color: var(--high); background: #edf1ff; border-color: #d8e0ff; }}
    .paper-card[data-level="medium"] .score {{ color: var(--medium); background: #eaf7f8; border-color: #cce9ec; }}
    .paper-card[data-level="low"] .score {{ color: var(--low); background: #f2f5f7; border-color: #d4dde4; }}
    .paper-card[data-level="irrelevant"] .score {{ color: var(--irrelevant); background: var(--irrelevant-soft); border-color: #d6d8db; }}
    .summary {{ margin: 10px 0; overflow-wrap: anywhere; }}
    details {{ margin-top: 10px; }}
    summary {{ cursor: pointer; color: var(--accent-strong); font-weight: 650; }}
    details[open] {{ border-top: 1px solid var(--border); padding-top: 10px; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }}
    .action {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 13px;
      border: 1px solid rgba(19, 117, 109, 0.26);
      border-radius: 8px;
      background: #f1faf7;
      text-decoration: none;
      font-size: 14px;
      font-weight: 650;
      transition: background 140ms ease, transform 140ms ease;
    }}
    .action:hover {{ background: #e4f4f0; transform: translateY(-1px); }}
    .image-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 14px; }}
    .image-grid img {{
      width: 100%;
      max-height: 320px;
      object-fit: contain;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: white;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
    }}
    .image-grid:empty {{ display: none; }}
    .skipped-list {{ margin: 0; padding-left: 18px; }}
    .skipped-list span, .skipped-list em {{ color: var(--muted); margin-left: 8px; font-size: 13px; }}
    .empty {{ display: none; padding: 24px; text-align: center; color: var(--muted); }}
    footer {{ color: var(--muted); font-size: 12px; padding: 28px 0; }}
    [hidden] {{ display: none !important; }}
    .hero-summary {{ grid-template-columns: repeat(4, minmax(76px, 1fr)); min-width: 390px; }}
    .kicker {{ margin: 0 0 12px; color: #80d6e3; font-size: 11px; font-weight: 650; letter-spacing: .22em; text-transform: uppercase; }}
    .context-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.55fr) minmax(250px, .65fr);
      gap: 16px;
      margin-bottom: 18px;
    }}
    .context-grid .panel {{ margin: 0; border-radius: 14px; }}
    .run-card {{
      background: rgba(255, 255, 255, .88);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      box-shadow: var(--shadow-soft);
    }}
    .run-card h2 {{ margin: 0 0 12px; font-size: 19px; }}
    .run-facts {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; gap: 10px; }}
    .run-facts div {{ padding: 10px 11px; border-radius: 10px; background: #f1f4fa; }}
    .run-facts dt {{ color: var(--muted); font-size: 11px; }}
    .run-facts dd {{ margin: 1px 0 0; color: var(--accent-strong); font-size: 19px; font-weight: 760; }}
    .warning-panel {{ margin-bottom: 18px; border-color: #e8ddc8; background: #fffcf5; box-shadow: none; font-size: 13px; }}
    .warning-panel ul {{ margin: 0; padding-left: 20px; }}
    .list-intro {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin: 28px 2px 13px; }}
    .list-intro h2 {{ margin: 0; font-size: 25px; line-height: 1.2; }}
    .result-count {{ color: var(--muted); font-size: 13px; }}
    .paper-section {{ margin: 0 0 22px; }}
    .section-heading {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 0 2px 11px; }}
    .section-heading h2 {{ margin: 1px 0 0; font-size: 19px; line-height: 1.3; }}
    .section-heading p {{ margin: 0; color: var(--muted); font-size: 13px; }}
    .section-heading-copy {{ display: block; }}
    .section-heading-title {{ display: block; margin-top: 1px; color: var(--text); font-size: 19px; line-height: 1.3; font-weight: 750; }}
    .section-heading-note {{ display: block; color: var(--muted); font-size: 13px; font-weight: 400; }}
    .section-label {{ font-size: 11px; font-weight: 800; letter-spacing: .11em; color: var(--muted); text-transform: uppercase; }}
    .count-pill {{ flex: 0 0 auto; border-radius: 999px; padding: 4px 9px; background: var(--accent-soft); color: var(--accent-strong); font-size: 12px; font-weight: 750; }}
    .paper-list {{ gap: 13px; }}
    .paper-card {{ border-radius: 12px; padding: 24px 25px 21px; }}
    .paper-card:hover {{ transform: none; border-color: #bbc9e7; }}
    .paper-card h3 {{ font-size: 19px; line-height: 1.55; font-weight: 650; }}
    .summary {{ color: #37455e; line-height: 1.85; }}
    .venue {{ background: #f1f4f9; color: #52617a; font-size: 12px; font-weight: 550; }}
    .topics span, .tag {{ border-radius: 5px; font-weight: 500; padding: 3px 8px; }}
    .action {{ background: #eef2ff; border-color: #d8e0f5; }}
    .action:hover {{ background: #e1e8ff; }}
    .action::after {{ content: " ↗"; margin-left: 8px; }}
    .secondary-actions button {{ background: transparent; color: #52617a; }}
    input[type="search"]:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(54, 91, 214, .12); }}
    button:focus-visible, summary:focus-visible, a:focus-visible {{ outline: 3px solid #8ca5f5; outline-offset: 3px; }}
    @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ transition: none !important; }} }}
    .paper-card.compact {{ padding-block: 14px; }}
    .paper-card.compact h3 {{ font-size: 17px; }}
    .irrelevant-section {{
      border: 1px solid var(--border);
      border-radius: 14px;
      background: rgba(255, 255, 255, .64);
      padding: 0 18px;
      box-shadow: var(--shadow-soft);
    }}
    .irrelevant-section > summary {{ list-style: none; cursor: pointer; padding: 17px 0; }}
    .irrelevant-section > summary::-webkit-details-marker {{ display: none; }}
    .irrelevant-section > summary.section-heading {{ margin: 0; }}
    .irrelevant-section > summary .section-heading-title::after {{ content: "  ＋"; color: var(--irrelevant); }}
    .irrelevant-section[open] > summary .section-heading-title::after {{ content: "  −"; }}
    .irrelevant-section[open] {{ border-top: 1px solid var(--border); padding-top: 0; }}
    .irrelevant-section > .paper-list {{ padding: 2px 0 18px; }}
    .skipped-panel {{ margin-top: 24px; }}
    @media (max-width: 860px) {{
      h1 {{ font-size: 27px; }}
      .hero {{ grid-template-columns: 1fr; align-items: start; }}
      .hero-summary {{ min-width: 0; width: 100%; grid-template-columns: repeat(4, minmax(0, 1fr)); }}
      .toolbar-row {{ grid-template-columns: 1fr; }}
      .context-grid {{ grid-template-columns: 1fr; }}
      .paper-top {{ display: block; }}
      .score {{ display: inline-flex; margin-bottom: 10px; }}
    }}
    @media (max-width: 540px) {{
      header {{ padding: 28px 0 22px; }}
      .shell {{ width: min(100% - 28px, 1180px); }}
      .hero {{ gap: 18px; }}
      .hero-summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .hero-summary div {{ padding: 9px 11px; }}
      .toolbar {{ position: static; }}
      .filters {{ flex-wrap: nowrap; overflow-x: auto; padding-bottom: 5px; scrollbar-width: thin; }}
      .filters button {{ flex: 0 0 auto; }}
      .secondary-actions {{ display: contents; }}
      main {{ padding-top: 18px; }}
      .panel, .run-card {{ padding: 16px; }}
      .list-intro {{ align-items: start; flex-direction: column; gap: 2px; }}
      .section-heading {{ align-items: flex-start; }}
      .section-heading p, .section-heading-note {{ display: none; }}
      .paper-card {{ padding: 15px 14px 13px; }}
      .irrelevant-section {{ padding-inline: 14px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="shell hero">
      <div>
        <p class="kicker">ScholarInbox</p>
        <h1>科研文献摘要</h1>
        <p class="subtitle">{escape(run.date_label)} · 浏览器阅读版 · 共 {len(run.papers)} 条结果</p>
      </div>
      <div class="hero-summary" aria-label="相关性概览">
        <div><strong>{displayed_counts['high']}</strong><span>高相关</span></div>
        <div><strong>{displayed_counts['medium']}</strong><span>中相关</span></div>
        <div><strong>{displayed_counts['low']}</strong><span>低相关</span></div>
        <div><strong>{displayed_counts['irrelevant']}</strong><span>不相关</span></div>
      </div>
    </div>
  </header>
  <nav class="toolbar" aria-label="阅读工具">
    <div class="shell toolbar-row">
      <input id="search" type="search" placeholder="搜索标题、摘要、主题、DOI 或来源邮件">
      <div class="filters" role="group" aria-label="相关性筛选">
        <button type="button" data-filter="all" aria-pressed="true">全部</button>
        <button type="button" data-filter="high" aria-pressed="false">高相关</button>
        <button type="button" data-filter="medium" aria-pressed="false">中相关</button>
        <button type="button" data-filter="low" aria-pressed="false">低相关</button>
        <button type="button" data-filter="irrelevant" aria-pressed="false">不相关</button>
        <span class="secondary-actions">
          <button type="button" id="expand-all">展开详情</button>
          <button type="button" id="collapse-all">收起详情</button>
        </span>
      </div>
    </div>
  </nav>
  <main class="shell">
    <div class="context-grid">
      <section class="panel">
        <h2>近期研究兴趣</h2>
        <p>{escape(run.interest_profile.summary_zh or '未生成研究兴趣摘要。')}</p>
        {'<div class="topics">' + high_topic_html + '</div>' if high_topic_html else ''}
      </section>
      <aside class="run-card" aria-label="本次处理概况">
        <h2>本次处理</h2>
        <dl class="run-facts">
          <div><dt>读取邮件</dt><dd>{stats.emails_read}</dd></div>
          <div><dt>提取条目</dt><dd>{stats.paper_entries_extracted}</dd></div>
          <div><dt>去重移除</dt><dd>{stats.duplicates_removed}</dd></div>
          <div><dt>跳过邮件</dt><dd>{stats.skipped_emails}</dd></div>
        </dl>
      </aside>
    </div>
    {'<section class="panel warning-panel"><h2>运行提示</h2><ul>' + warnings + '</ul></section>' if warnings else ''}
    <div class="list-intro">
      <h2>文献结果</h2>
      <span class="result-count" id="result-count" aria-live="polite">显示 {len(run.papers)} / {len(run.papers)} 条</span>
    </div>
    <div id="papers">
      {paper_sections or '<p class="panel">暂无论文条目。</p>'}
    </div>
    <p class="empty" id="empty">当前筛选条件下没有匹配论文。</p>
    {'<section class="panel skipped-panel"><h2>跳过的邮件</h2><ul class="skipped-list">' + skipped_items + '</ul></section>' if skipped_items else ''}
    <footer>由本地 ScholarInbox 工作流生成。Markdown 与 HTML 文件包含相同 digest 内容，HTML 额外提供搜索、筛选和图片浏览。</footer>
  </main>
  <script type="application/json" id="digest-data">{digest_data}</script>
  <script>
    const search = document.querySelector('#search');
    const buttons = Array.from(document.querySelectorAll('[data-filter]'));
    const cards = Array.from(document.querySelectorAll('.paper-card'));
    const expandAll = document.querySelector('#expand-all');
    const collapseAll = document.querySelector('#collapse-all');
    const empty = document.querySelector('#empty');
    const sections = Array.from(document.querySelectorAll('[data-section-level]'));
    const irrelevantSection = document.querySelector('.irrelevant-section');
    const resultCount = document.querySelector('#result-count');
    let activeFilter = 'all';

    function applyFilters(resetIrrelevant = false) {{
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      for (const card of cards) {{
        const matchesLevel = activeFilter === 'all' || card.dataset.level === activeFilter;
        const matchesSearch = !query || card.dataset.search.includes(query);
        const show = matchesLevel && matchesSearch;
        card.hidden = !show;
        if (show) visible += 1;
      }}
      for (const section of sections) {{
        const sectionCards = Array.from(section.querySelectorAll('.paper-card'));
        section.hidden = !sectionCards.some(card => !card.hidden);
      }}
      if (irrelevantSection && !irrelevantSection.hidden) {{
        if (activeFilter === 'irrelevant' || query) irrelevantSection.open = true;
        else if (resetIrrelevant) irrelevantSection.open = false;
      }}
      empty.style.display = visible ? 'none' : 'block';
      resultCount.textContent = `显示 ${{visible}} / ${{cards.length}} 条`;
    }}

    for (const button of buttons) {{
      button.addEventListener('click', () => {{
        activeFilter = button.dataset.filter;
        for (const item of buttons) item.setAttribute('aria-pressed', String(item === button));
        applyFilters(activeFilter === 'all');
      }});
    }}
    search.addEventListener('input', () => applyFilters(activeFilter === 'all' && !search.value.trim()));
    expandAll.addEventListener('click', () => {{
      if (irrelevantSection && !irrelevantSection.hidden) irrelevantSection.open = true;
      for (const item of document.querySelectorAll('.paper-card:not([hidden]) details')) item.open = true;
    }});
    collapseAll.addEventListener('click', () => {{
      for (const item of document.querySelectorAll('.paper-card details')) item.open = false;
      if (irrelevantSection) irrelevantSection.open = false;
    }});
    for (const img of document.querySelectorAll('.image-grid img')) {{
      img.addEventListener('error', () => img.remove());
      img.addEventListener('load', () => {{
        if (img.naturalWidth <= 4 || img.naturalHeight <= 4) img.remove();
      }});
    }}
    applyFilters(true);
  </script>
</body>
</html>
"""


def _append_markdown_section(lines: list[str], title: str, papers: list[RankedPaper], *, short: bool = False) -> None:
    lines.append(f"## {title}")
    if not papers:
        lines.append("暂无。")
        lines.append("")
        return

    for index, paper in enumerate(papers, start=1):
        entry = paper.entry
        link = f" | [链接]({entry.url})" if entry.url else ""
        doi = f" | DOI: `{entry.doi}`" if entry.doi else ""
        title_zh = _display_title_zh(paper)
        lines.append(f"### {index}. {title_zh}")
        lines.append(f"- 英文原题：{entry.title}{link}{doi}")
        lines.append(f"- 期刊/来源：{entry.venue or '未识别'}")
        lines.append(f"- 相关性：{paper.relevance} / {paper.score:.2f}")
        if paper.matched_topics:
            lines.append(f"- 匹配主题：{'；'.join(paper.matched_topics)}")
        if short:
            lines.append(f"- 简注：{paper.reason_zh}")
        else:
            lines.append(f"- 中文摘要：{paper.summary_zh}")
            lines.append(f"- 推荐理由：{paper.reason_zh}")
        if entry.image_paths:
            lines.append("- TOC/邮件图片：")
            for image_path in entry.image_paths:
                lines.append(f"  - ![]({image_path})")
        lines.append(f"- 来源邮件：{entry.source_subject} | {entry.source_sender}")
        lines.append("")


def _render_paper_section(
    level: str,
    papers: list[RankedPaper],
    paper_indices: dict[int, int],
    output_dir: str | Path | None,
) -> str:
    section_content = {
        "high": ("Priority", "高相关", "与当前研究重点直接相连，建议优先阅读。"),
        "medium": ("Related", "中相关", "方法、体系或性质与当前方向存在可用联系。"),
        "low": ("Peripheral", "低相关", "属于正常学术论文，但与当前研究方向联系较弱。"),
        "irrelevant": ("Excluded", "不相关", "非学术推广、活动信息或疑似错误提取；默认收起。"),
    }
    eyebrow, title, description = section_content[level]
    cards = "\n".join(
        _render_paper_card(paper, paper_indices[id(paper)], output_dir)
        for paper in papers
    )
    heading = f"""
        <div>
          <span class="section-label">{eyebrow}</span>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <span class="count-pill">{len(papers)} 条</span>
"""
    if level == "irrelevant":
        return f"""
      <details class="paper-section irrelevant-section" data-section-level="irrelevant">
        <summary class="section-heading">
          <span class="section-heading-copy">
            <span class="section-label">{eyebrow}</span>
            <span class="section-heading-title" role="heading" aria-level="2">{title}</span>
            <small class="section-heading-note">{description}</small>
          </span>
          <span class="count-pill">{len(papers)} 条</span>
        </summary>
        <div class="paper-list">{cards}</div>
      </details>
"""
    return f"""
      <section class="paper-section" data-section-level="{level}">
        <div class="section-heading">{heading}</div>
        <div class="paper-list">{cards}</div>
      </section>
"""


def _render_paper_card(paper: RankedPaper, index: int, output_dir: str | Path | None) -> str:
    entry = paper.entry
    title_zh = _display_title_zh(paper)
    search_blob = " ".join(
        [
            entry.title,
            title_zh,
            paper.summary_zh,
            paper.reason_zh,
            entry.doi,
            entry.source_subject,
            " ".join(paper.matched_topics),
        ]
    ).lower()
    topic_html = "".join(f'<span class="tag">{escape(topic)}</span>' for topic in paper.matched_topics)
    image_html = _render_images(entry.image_paths, output_dir)
    original_link = (
        f'<a class="action" href="{escape(entry.url)}" target="_blank" rel="noreferrer">打开原文</a>'
        if entry.url
        else ""
    )
    venue_html = escape(entry.venue or "未识别")
    doi_html = f'<span>DOI: <code>{escape(entry.doi)}</code></span>' if entry.doi else ""
    compact = paper.relevance in {"low", "irrelevant"}
    summary_html = "" if compact else f'<p class="summary">{escape(paper.summary_zh)}</p>'
    details_summary = "查看摘要、判断理由与来源" if compact else "查看判断理由与来源"
    compact_summary = f'<p class="summary">{escape(paper.summary_zh)}</p>' if compact else ""
    return f"""
      <article class="paper-card{' compact' if compact else ''}" data-level="{escape(paper.relevance)}" data-search="{escape(search_blob)}">
        <div class="paper-top">
          <div>
            <h3>{index}. {escape(title_zh)}</h3>
            <p class="meta">英文原题：{escape(entry.title)}</p>
            <p class="venue">期刊/来源：{venue_html}</p>
          </div>
          <div class="score">{escape(_level_label(paper.relevance))} · {paper.score:.2f}</div>
        </div>
        {'<div class="topics">' + topic_html + '</div>' if topic_html else ''}
        {summary_html}
        <details>
          <summary>{details_summary}</summary>
          {compact_summary}
          <p>{escape(paper.reason_zh)}</p>
          <p class="meta">来源邮件：{escape(entry.source_subject)} | {escape(entry.source_sender)}</p>
          {doi_html}
        </details>
        {image_html}
        <div class="actions">{original_link}</div>
      </article>
"""


def _render_images(paths: list[Path | str], output_dir: str | Path | None) -> str:
    if not paths:
        return ""
    items = []
    for path in paths:
        src = _image_src(path, output_dir)
        items.append(f'<img src="{escape(src)}" alt="TOC 或邮件图片" loading="lazy">')
    return '<div class="image-grid">' + "".join(items) + "</div>"


def _display_title_zh(paper: RankedPaper) -> str:
    title = (paper.title_zh or "").strip()
    original = paper.entry.title.strip()
    if title and title != original and _contains_cjk(title):
        return title
    return "中文标题暂未生成"


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _image_src(path: Path | str, output_dir: str | Path | None) -> str:
    raw = str(path)
    if raw.startswith(("http://", "https://", "data:", "file:")):
        return raw
    image_path = Path(raw)
    if image_path.is_absolute():
        return image_path.as_uri()
    if output_dir is not None:
        base = Path(output_dir).resolve()
        absolute = image_path.resolve()
        try:
            return os.path.relpath(absolute, base).replace("\\", "/")
        except ValueError:
            return absolute.as_uri()
    return image_path.as_posix()


def _level_label(level: str) -> str:
    return {
        "high": "高相关",
        "medium": "中相关",
        "low": "低相关",
        "irrelevant": "不相关",
    }.get(level, level)
