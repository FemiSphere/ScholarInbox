from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit

from .digest_assets import DIGEST_CSS, DIGEST_JS
from .models import RELEVANCE_LABELS, RELEVANCE_LEVELS, DigestRun, PaperEntry, RankedPaper


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


_DIGEST_FILENAME = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})-digest(?:-[0-9]+)?\.(?:md|html)")


def prune_old_digests(
    output_dir: Path, *, today: date, protected: list[Path],
) -> tuple[int, list[str]]:
    """Remove dated reports older than 60 days, excluding the current run's files."""
    cutoff = today - timedelta(days=60)
    current_outputs = set(protected)
    removed = 0
    failed = []
    for path in output_dir.iterdir():
        match = _DIGEST_FILENAME.fullmatch(path.name)
        if match is None or path in current_outputs or path.is_symlink() or not path.is_file():
            continue
        try:
            report_date = date.fromisoformat(match[1])
        except ValueError:
            continue
        if report_date >= cutoff:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            failed.append(path.name)
        else:
            removed += 1
    return removed, failed


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
    lines.append(f"- 领域外论文：{stats.off_topic}")
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
    _append_markdown_section(lines, "领域外论文", [paper for paper in run.papers if paper.relevance == "off_topic"], short=True)
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
    papers_by_level = {
        level: [paper for paper in run.papers if paper.relevance == level]
        for level in RELEVANCE_LEVELS
    }
    counts = {level: len(papers_by_level[level]) for level in RELEVANCE_LEVELS}
    warnings = "".join(f"<li>{escape(warning)}</li>" for warning in run.warnings)
    high_topic_html = "".join(f'<span class="tag">{escape(topic)}</span>' for topic in run.interest_profile.high_priority_topics)
    paper_indices = {id(paper): index for index, paper in enumerate(run.papers, 1)}
    paper_sections = "\n".join(
        _render_paper_section(level, papers_by_level[level], paper_indices, output_dir)
        for level in RELEVANCE_LEVELS
        if papers_by_level[level]
    )
    hero_tiles = "".join(
        f'<a href="#sec-{level}"><strong data-count="{counts[level]}">{counts[level]}</strong>'
        f"<span>{RELEVANCE_LABELS[level]}</span></a>"
        for level in RELEVANCE_LEVELS
    )
    nav_links = "".join(
        f'<a href="#sec-{level}" data-nav="{level}" style="--level: var(--{level})"><span class="dot"></span>'
        f'{RELEVANCE_LABELS[level]}<span class="nav-count">{counts[level]}</span></a>'
        for level in RELEVANCE_LEVELS
        if counts[level]
    )
    filter_chips = "".join(
        f'<button type="button" class="chip" data-filter="{level}" aria-pressed="false">{RELEVANCE_LABELS[level]}</button>'
        for level in RELEVANCE_LEVELS
    )
    skipped_items = "".join(
        f"<li><strong>{escape(item.subject)}</strong><span>{escape(item.sender)}</span><em>{escape(item.reason)}</em></li>"
        for item in run.skipped
    )
    data = {**counts, "total": len(run.papers), "date": run.date_label}
    digest_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    interest_summary = escape(run.interest_profile.summary_zh or "未生成研究兴趣摘要。")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>科研文献摘要 - {escape(run.date_label)}</title>
  <style>{DIGEST_CSS}</style>
</head>
<body>
  <div class="progress" id="progress" aria-hidden="true"></div>
  <header class="hero">
    <div class="shell">
      <div>
        <p class="kicker">ScholarInbox</p>
        <h1>科研文献摘要</h1>
        <p class="subtitle">{escape(run.date_label)} · 共 {len(run.papers)} 条结果</p>
      </div>
      <nav class="hero-summary" aria-label="相关性概览">{hero_tiles}</nav>
    </div>
  </header>
  <nav class="toolbar" aria-label="阅读工具">
    <div class="shell">
      <label class="search"><input id="search" type="search" placeholder="搜索标题、摘要、主题、DOI 或来源邮件" aria-label="搜索"></label>
      <div class="chips" role="group" aria-label="相关性筛选">
        <button type="button" class="chip" data-filter="all" aria-pressed="true">全部</button>
        {filter_chips}
        <button type="button" class="chip" data-filter="starred" aria-pressed="false">★ 收藏 <span id="star-chip-count">0</span></button>
      </div>
      <div class="tools">
        <button type="button" class="tool" id="hide-read" aria-pressed="false">隐藏已读</button>
        <button type="button" class="tool" id="expand-all">展开详情</button>
        <button type="button" class="tool" id="collapse-all">收起详情</button>
        <button type="button" class="tool" id="export-starred">导出收藏 <span id="star-count">0</span></button>
      </div>
    </div>
  </nav>
  <div class="shell layout">
    <aside class="side" aria-label="目录与进度">
      <div class="side-card side-nav">
        <p class="side-title">目录</p>
        {nav_links or '<p class="meter-label">暂无论文</p>'}
        <div class="meter" aria-hidden="true"><i id="read-meter"></i></div>
        <span class="meter-label" id="read-label">已读 0 / {len(run.papers)}</span>
      </div>
      <div class="side-card">
        <p class="side-title">本次处理</p>
        <dl class="facts">
          <div><dt>读取邮件</dt><dd>{stats.emails_read}</dd></div>
          <div><dt>提取条目</dt><dd>{stats.paper_entries_extracted}</dd></div>
          <div><dt>去重移除</dt><dd>{stats.duplicates_removed}</dd></div>
          <div><dt>跳过邮件</dt><dd>{stats.skipped_emails}</dd></div>
        </dl>
      </div>
    </aside>
    <main>
      <section class="panel">
        <h2>近期研究兴趣</h2>
        <p>{interest_summary}</p>
        {'<div class="topics">' + high_topic_html + '</div>' if high_topic_html else ''}
      </section>
      {'<section class="panel warning-panel"><h2>运行提示</h2><ul>' + warnings + '</ul></section>' if warnings else ''}
      <div class="list-intro">
        <h2>文献结果</h2>
        <span class="result-count" id="result-count" aria-live="polite">显示 {len(run.papers)} / {len(run.papers)} 条</span>
      </div>
      <div id="papers">
        {paper_sections or '<p class="panel">暂无论文条目。</p>'}
      </div>
      <p class="empty" id="empty" hidden>当前筛选条件下没有匹配论文。</p>
      {'<section class="panel"><h2>跳过的邮件</h2><ul class="skipped-list">' + skipped_items + '</ul></section>' if skipped_items else ''}
      <footer>由本地 ScholarInbox 工作流生成。收藏与已读状态只保存在本机浏览器中，跨日报共享，保留 60 天；打开原文会自动标为已读。</footer>
    </main>
  </div>
  <div class="lightbox" id="lightbox" hidden><img alt="放大的 TOC 或邮件图片"></div>
  <dialog id="export-dialog" aria-labelledby="export-title">
    <h2 id="export-title">导出收藏</h2>
    <p>包含近 60 天在本机浏览器中收藏的论文（含往期日报）；更早的收藏与日报一样自动清除。</p>
    <textarea id="export-text" readonly></textarea>
    <div class="dialog-actions">
      <button type="button" class="tool" id="export-copy">复制</button>
      <button type="button" class="tool" id="export-download">下载 Markdown</button>
      <button type="button" class="tool" id="export-close">关闭</button>
    </div>
  </dialog>
  <button type="button" class="to-top" id="to-top" aria-label="回到顶部">↑</button>
  <script type="application/json" id="digest-data">{digest_data}</script>
  <script>{DIGEST_JS}</script>
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
        source_url = _evidence_source_url(paper)
        if source_url:
            lines.append(f"- 摘要来源：[原始摘要](<{source_url}>)")
        lines.append(f"- 来源邮件：{entry.source_subject} | {entry.source_sender}")
        lines.append("")


_SECTION_CONTENT = {
    "high": ("Priority", "与当前研究重点直接相连，建议优先阅读。"),
    "medium": ("Related", "方法、体系或性质与当前方向存在可用联系。"),
    "low": ("Peripheral", "同一大方向内的正常学术论文，但与具体课题联系较弱；点击展开详情。"),
    "off_topic": ("Off-topic", "学术论文，但不属于研究大方向；默认收起，仅显示标题。"),
    "irrelevant": ("Excluded", "非学术推广、活动信息或疑似错误提取；默认收起。"),
}
_FOLDED_LEVELS = {"off_topic", "irrelevant"}
_ROW_LEVELS = {"low", "off_topic", "irrelevant"}


def _render_paper_section(
    level: str,
    papers: list[RankedPaper],
    paper_indices: dict[int, int],
    output_dir: str | Path | None,
) -> str:
    eyebrow, description = _SECTION_CONTENT[level]
    title = RELEVANCE_LABELS[level]
    cards = "\n".join(
        _render_paper_card(paper, paper_indices[id(paper)], output_dir)
        for paper in papers
    )
    list_class = "paper-list rows" if level in _ROW_LEVELS else "paper-list"
    tools = (f'<span class="section-tools"><button type="button" class="text-btn" data-action="mark-section">本节标为已读</button>'
             f'<span class="count-pill">{len(papers)} 条</span></span>')
    if level in _FOLDED_LEVELS:
        return f"""
      <details class="paper-section folded-section" id="sec-{level}" data-section-level="{level}">
        <summary class="section-heading">
          <span class="section-heading-copy">
            <span class="section-label">{eyebrow}</span>
            <span class="section-heading-title" role="heading" aria-level="2">{title}</span>
            <small class="section-heading-note">{description}</small>
          </span>
          {tools}
        </summary>
        <div class="details-body"><div class="{list_class}">{cards}</div></div>
      </details>
"""
    return f"""
      <section class="paper-section" id="sec-{level}" data-section-level="{level}">
        <div class="section-heading">
          <div><span class="section-label">{eyebrow}</span><h2>{title}</h2><p>{description}</p></div>
          {tools}
        </div>
        <div class="{list_class}">{cards}</div>
      </section>
"""


def _render_paper_card(paper: RankedPaper, index: int, output_dir: str | Path | None) -> str:
    entry = paper.entry
    title_zh = _display_title_zh(paper)
    search_blob = " ".join(
        [entry.title, title_zh, paper.summary_zh, paper.reason_zh, entry.doi, entry.source_subject, entry.venue,
         " ".join(paper.matched_topics)]
    ).lower()
    topic_html = "".join(f'<span class="tag">{escape(topic)}</span>' for topic in paper.matched_topics)
    topics = f'<div class="topics">{topic_html}</div>' if topic_html else ""
    image_html = _render_images(entry.image_paths, output_dir)
    original_link = (
        f'<a class="action" data-action="open" href="{escape(entry.url)}" target="_blank" rel="noreferrer">打开原文</a>'
        if entry.url else ""
    )
    venue = entry.venue or "未识别"
    doi_html = f'<p class="meta">DOI: <code>{escape(entry.doi)}</code></p>' if entry.doi else ""
    source_url = _evidence_source_url(paper)
    abstract_source_html = (f'<p class="meta">摘要来源：<a href="{escape(source_url, quote=True)}" '
        'target="_blank" rel="noreferrer">原始摘要</a></p>' if source_url else "")
    badge = f'<span class="badge">{escape(_level_label(paper.relevance))} · {paper.score:.2f}</span>'
    star_button = '<button type="button" class="icon-btn star" data-action="star" aria-pressed="false">☆ 收藏</button>'
    read_button = '<button type="button" class="icon-btn read" data-action="read" aria-pressed="false">标为已读</button>'
    source_html = f'<p class="meta">来源邮件：{escape(entry.source_subject)} | {escape(entry.source_sender)}</p>'
    attributes = (
        f'data-level="{escape(paper.relevance)}" data-id="{_paper_key(entry)}" data-search="{escape(search_blob)}" '
        f'data-title="{escape(entry.title)}" data-venue="{escape(entry.venue)}" data-doi="{escape(entry.doi)}" '
        f'data-url="{escape(entry.url)}"'
    )

    if paper.relevance in _ROW_LEVELS:
        summary_html = (f'<p class="summary">{escape(paper.summary_zh)}</p>'
                        if paper.summary_zh and paper.relevance != "irrelevant" else "")
        return f"""
      <article class="paper-card row" id="p-{index}" {attributes}>
        <details class="row-details">
          <summary>
            <span class="row-main"><span class="title-zh">{index}. {escape(title_zh)}</span><span class="row-en">英文原题：{escape(entry.title)}</span></span>
            <span class="row-side"><span class="venue-chip">{escape(venue)}</span>{badge}</span>
          </summary>
          <div class="details-body"><div class="row-body">
            {topics}
            {summary_html}
            <p>{escape(paper.reason_zh)}</p>
            <p class="venue">期刊/来源：{escape(venue)}</p>
            {source_html}
            {doi_html}
            {abstract_source_html}
            {image_html}
            <div class="actions">{original_link}{star_button}{read_button}</div>
          </div></div>
        </details>
      </article>
"""
    return f"""
      <article class="paper-card full" id="p-{index}" {attributes}>
        <div class="card-head">{badge}<span class="card-tools">{star_button}{read_button}</span></div>
        <h3><span class="num">{index}.</span><span class="title-zh">{escape(title_zh)}</span></h3>
        <p class="meta">英文原题：{escape(entry.title)}</p>
        <p class="venue">期刊/来源：{escape(venue)}</p>
        {topics}
        <p class="summary">{escape(paper.summary_zh)}</p>
        <details class="card-details">
          <summary>查看判断理由与来源</summary>
          <div class="details-body">
            <p>{escape(paper.reason_zh)}</p>
            {source_html}
            {doi_html}
            {abstract_source_html}
          </div>
        </details>
        {image_html}
        <div class="actions">{original_link}</div>
      </article>
"""


def _paper_key(entry: PaperEntry) -> str:
    """Stable per-paper id for browser read/star state across digests."""
    identity = (entry.doi or entry.url or entry.title).strip().lower()
    return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def _evidence_source_url(paper: RankedPaper) -> str:
    if paper.evidence is None:
        return ""
    url = paper.evidence.source_url
    if not isinstance(url, str) or any(ord(char) < 32 for char in url):
        return ""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
    except ValueError:
        return ""
    return quote(url, safe=":/?&=%#@+;,~!$'()*[]")

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
    return RELEVANCE_LABELS.get(level, level)
