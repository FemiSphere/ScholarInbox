"""Inline stylesheet and script for the HTML digest.

Kept separate from ``digest.py`` so the page structure stays readable. Both are
plain strings (not f-strings); ``render_html`` inlines them so a digest remains a
single self-contained file that opens from ``file://`` without a server.
Reader state (read / starred) lives only in the browser's localStorage.
"""

DIGEST_CSS = r"""
/* ---------------------------------------------------------------- themes
   Three reading styles share one structure. html[data-theme] selects the tokens;
   a small set of theme rules below adjusts layout (list vs. cards, masthead). */
:root, html[data-theme="editorial"] {
  --bg: #f6f3ec; --surface: #fffdf8; --surface-soft: #f1ece1;
  --ink: #1f1c18; --ink-soft: #4b463f; --muted: #8b8478; --rule: #e2dacb; --rule-strong: #cfc4b0;
  --accent: #8a2f2a; --accent-soft: #f3e5df;
  --high: #8a2f2a; --medium: #8c6a2c; --low: #7b7468; --off_topic: #9b9385; --irrelevant: #b1aa9c;
  --star: #b8871f;
  --font-display: "Iowan Old Style", "Charter", "Songti SC", "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  --font-body: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --title-weight: 600; --radius: 0px; --card-pad: 26px 0 24px;
}
html[data-theme="swiss"] {
  --bg: #ffffff; --surface: #ffffff; --surface-soft: #f5f5f4;
  --ink: #111111; --ink-soft: #3d3d3d; --muted: #8c8c8c; --rule: #ebebeb; --rule-strong: #d6d6d6;
  --accent: #2650c7; --accent-soft: #eef2fc;
  --high: #2650c7; --medium: #4a4a4a; --low: #8c8c8c; --off_topic: #a6a6a6; --irrelevant: #bdbdbd;
  --star: #e0a100;
  --font-display: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  --title-weight: 650; --radius: 0px; --card-pad: 24px 0 22px;
}
html[data-theme="calm"] {
  --bg: #eff1ec; --surface: #fbfbf8; --surface-soft: #f3f5f0;
  --ink: #1d2420; --ink-soft: #46504a; --muted: #808a83; --rule: #e0e4dc; --rule-strong: #ccd3c8;
  --accent: #2f6a55; --accent-soft: #e2ede7;
  --high: #2f6a55; --medium: #5d7a3c; --low: #7f8a83; --off_topic: #98a19a; --irrelevant: #b2b9b3;
  --star: #c4932a;
  --font-display: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --title-weight: 600; --radius: 16px; --card-pad: 22px 24px 20px;
}

/* ---------------------------------------------------------------- base */
* { box-sizing: border-box; }
html { color-scheme: light; -webkit-text-size-adjust: 100%; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body);
  font-size: 15.5px; line-height: 1.7; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
a { color: inherit; text-decoration-color: var(--rule-strong); text-underline-offset: 3px; text-decoration-thickness: 1px; }
a:hover { color: var(--accent); text-decoration-color: currentColor; }
button { font: inherit; color: inherit; }
[hidden] { display: none !important; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
::selection { background: var(--accent-soft); }

.shell { width: min(1180px, calc(100vw - 40px)); margin: 0 auto; }
.progress { position: fixed; inset: 0 0 auto 0; height: 2px; z-index: 50; pointer-events: none;
  background: var(--accent); transform-origin: 0 50%; transform: scaleX(0); will-change: transform; }

/* ---------------------------------------------------------------- masthead */
.masthead { padding: 56px 0 30px; }
.masthead .shell { display: grid; gap: 14px; }
.kicker { margin: 0; display: flex; justify-content: space-between; gap: 16px; color: var(--muted);
  font-size: 12px; letter-spacing: .14em; text-transform: uppercase; }
h1 { margin: 0; font-family: var(--font-display); font-weight: var(--title-weight); font-size: 46px; line-height: 1.1;
  letter-spacing: -.01em; color: var(--ink); }
.subtitle { margin: 0; color: var(--ink-soft); font-size: 15px; }
.hero-summary { display: flex; flex-wrap: wrap; gap: 6px 28px; margin-top: 6px; padding-top: 16px; border-top: 1px solid var(--rule); }
.hero-summary a { text-decoration: none; display: inline-flex; align-items: baseline; gap: 7px; color: var(--ink-soft); }
.hero-summary strong { font-family: var(--font-display); font-size: 26px; font-weight: 500; color: var(--ink);
  font-variant-numeric: tabular-nums lining-nums; }
.hero-summary a:hover strong { color: var(--accent); }
.hero-summary span { font-size: 13px; }

html[data-theme="editorial"] .masthead { text-align: center; padding-top: 64px; }
html[data-theme="editorial"] .masthead .shell { justify-items: center; }
html[data-theme="editorial"] .kicker { width: 100%; padding-bottom: 12px; border-bottom: 1px solid var(--ink); }
html[data-theme="editorial"] h1 { font-size: 52px; }
html[data-theme="editorial"] .hero-summary { justify-content: center; width: 100%; border-top: 3px double var(--rule-strong); }
html[data-theme="swiss"] h1 { font-size: 60px; letter-spacing: -.035em; font-weight: 700; }
html[data-theme="swiss"] .hero-summary { gap: 0; border-top: 2px solid var(--ink); padding-top: 0; }
html[data-theme="swiss"] .hero-summary a { display: grid; gap: 2px; padding: 14px 32px 0 0; min-width: 110px; }
html[data-theme="swiss"] .hero-summary strong { font-family: var(--font-body); font-size: 34px; font-weight: 600; letter-spacing: -.02em; }
html[data-theme="calm"] .masthead { padding-bottom: 22px; }
html[data-theme="calm"] h1 { font-size: 38px; }
html[data-theme="calm"] .hero-summary { border-top: 0; padding-top: 4px; }
html[data-theme="calm"] .hero-summary a { padding: 8px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--rule); }
html[data-theme="calm"] .hero-summary strong { font-family: var(--font-body); font-size: 20px; font-weight: 600; }

/* ---------------------------------------------------------------- toolbar (solid: no backdrop blur) */
.toolbar { position: sticky; top: 0; z-index: 20; background: var(--bg); border-bottom: 1px solid var(--rule); padding: 10px 0; }
.toolbar .shell { display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: center; }
.search { flex: 1 1 240px; min-width: 0; }
.search input { width: 100%; height: 38px; padding: 0 2px; border: 0; border-bottom: 1px solid var(--rule-strong); border-radius: 0;
  background: transparent; color: var(--ink); font-size: 14.5px; outline: none; transition: border-color .2s; }
.search input::placeholder { color: var(--muted); }
.search input:focus { border-bottom-color: var(--ink); }
html[data-theme="calm"] .search input { border: 1px solid var(--rule); border-radius: 12px; padding: 0 14px; background: var(--surface); }
html[data-theme="calm"] .search input:focus { border-color: var(--accent); }
.chips, .tools { display: flex; flex-wrap: wrap; gap: 2px 16px; align-items: center; }
.chip, .tool { border: 0; background: none; padding: 6px 0; cursor: pointer; font-size: 13.5px; color: var(--muted);
  white-space: nowrap; border-bottom: 1.5px solid transparent; transition: color .15s, border-color .15s; }
.chip:hover, .tool:hover { color: var(--ink); }
.chip[aria-pressed="true"] { color: var(--ink); border-bottom-color: var(--accent); }
.tool[aria-pressed="true"] { color: var(--accent); }
.tools { margin-left: auto; }
html[data-theme="calm"] .chip { padding: 5px 11px; border-radius: 999px; border: 0; }
html[data-theme="calm"] .chip[aria-pressed="true"] { background: var(--accent); color: #fff; }

/* ---------------------------------------------------------------- layout */
.layout { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 48px; padding: 34px 0 72px; }
.layout > main { min-width: 0; }
.side { position: sticky; top: 76px; align-self: start; display: grid; gap: 26px; font-size: 13.5px; }
.side-title { margin: 0 0 8px; color: var(--muted); font-size: 11px; letter-spacing: .14em; text-transform: uppercase; }
.side-nav a { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; color: var(--ink-soft); text-decoration: none;
  border-left: 2px solid transparent; padding-left: 10px; margin-left: -12px; transition: color .15s, border-color .15s; }
.side-nav a:hover { color: var(--ink); }
.side-nav a.active { color: var(--ink); border-left-color: var(--accent); }
.side-nav .dot { display: none; }
.side-nav .nav-count { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
.meter { height: 2px; background: var(--rule); margin: 14px 0 6px; }
.meter i { display: block; height: 100%; width: 0; background: var(--accent); transition: width .4s ease; }
.meter-label { color: var(--muted); font-size: 12px; }
.facts { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; margin: 0; }
.facts div { display: contents; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-soft); }
html[data-theme="calm"] .side-card { background: var(--surface); border: 1px solid var(--rule); border-radius: 14px; padding: 16px; }
html[data-theme="calm"] .side-nav a { margin-left: 0; padding-left: 8px; border-radius: 8px; border-left: 0; }
html[data-theme="calm"] .side-nav a.active { background: var(--accent-soft); color: var(--accent); }

/* ---------------------------------------------------------------- intro panels */
.panel { margin: 0 0 26px; }
.panel h2 { margin: 0 0 6px; font-family: var(--font-display); font-weight: var(--title-weight); font-size: 17px; }
.panel p { margin: 0; color: var(--ink-soft); font-size: 14.5px; }
.interest-panel { padding-bottom: 24px; border-bottom: 1px solid var(--rule); }
.warning-panel { padding: 12px 16px; background: var(--surface-soft); border-left: 2px solid var(--star); }
.warning-panel ul { margin: 0; padding-left: 18px; font-size: 13.5px; color: var(--ink-soft); }
html[data-theme="calm"] .interest-panel { background: var(--surface); border: 1px solid var(--rule); border-radius: 16px; padding: 20px 22px; }
html[data-theme="calm"] .warning-panel { border-radius: 12px; border-left-width: 0; background: #f7f1e3; }
.topics { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 10px; font-size: 12.5px; color: var(--muted); }
.tag::before { content: "#"; opacity: .55; margin-right: 1px; }
html[data-theme="calm"] .tag { background: var(--accent-soft); color: var(--accent); border-radius: 6px; padding: 1px 8px; }
html[data-theme="calm"] .tag::before { content: none; }

/* ---------------------------------------------------------------- sections */
.list-intro { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 8px 0 6px; }
.list-intro h2 { margin: 0; font-family: var(--font-display); font-weight: var(--title-weight); font-size: 15px; color: var(--muted);
  letter-spacing: .12em; text-transform: uppercase; }
.result-count { color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
.paper-section { margin: 0 0 44px; scroll-margin-top: 72px; --level: var(--muted); }
.paper-section[data-section-level="high"], .paper-card[data-level="high"] { --level: var(--high); }
.paper-section[data-section-level="medium"], .paper-card[data-level="medium"] { --level: var(--medium); }
.paper-section[data-section-level="low"], .paper-card[data-level="low"] { --level: var(--low); }
.paper-section[data-section-level="off_topic"], .paper-card[data-level="off_topic"] { --level: var(--off_topic); }
.paper-section[data-section-level="irrelevant"], .paper-card[data-level="irrelevant"] { --level: var(--irrelevant); }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; padding: 10px 0 12px;
  border-bottom: 1px solid var(--ink); }
html[data-theme="calm"] .section-heading { border-bottom: 0; padding-bottom: 6px; }
.section-label { display: block; color: var(--level); font-size: 11px; letter-spacing: .16em; text-transform: uppercase; }
.section-heading h2, .section-heading-title { display: block; margin: 2px 0 0; font-family: var(--font-display);
  font-weight: var(--title-weight); font-size: 24px; line-height: 1.25; color: var(--ink); }
html[data-theme="swiss"] .section-heading h2, html[data-theme="swiss"] .section-heading-title { font-size: 22px; letter-spacing: -.01em; }
.section-heading p, .section-heading-note { display: block; margin: 4px 0 0; color: var(--muted); font-size: 13px; font-weight: 400; font-family: var(--font-body); }
.section-tools { display: flex; align-items: baseline; gap: 14px; flex: 0 0 auto; font-size: 12.5px; }
.count-pill { color: var(--muted); font-variant-numeric: tabular-nums; }
.text-btn { border: 0; background: none; padding: 0; color: var(--muted); cursor: pointer; font-size: 12.5px; }
.text-btn:hover { color: var(--accent); }
.folded-section > summary { list-style: none; cursor: pointer; }
.folded-section > summary::-webkit-details-marker { display: none; }
.folded-section > summary .section-heading-title::after { content: "＋"; display: inline-block; margin-left: 10px; font-size: .7em;
  color: var(--muted); transition: transform .25s ease; vertical-align: middle; }
.folded-section[open] > summary .section-heading-title::after { transform: rotate(45deg); }
.folded-section:not([open]) > summary.section-heading { border-bottom-color: var(--rule); }

/* ---------------------------------------------------------------- papers: list by default */
.paper-list { display: grid; grid-template-columns: minmax(0, 1fr); }
.paper-list > .paper-card { min-width: 0; }
.paper-card { position: relative; transition: opacity .2s ease; }
.paper-card.full { padding: var(--card-pad); border-bottom: 1px solid var(--rule); }
.card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 6px; }
.badge { font-size: 11.5px; letter-spacing: .08em; color: var(--level); font-variant-numeric: tabular-nums; white-space: nowrap; }
.card-tools { display: flex; gap: 14px; }
.icon-btn { border: 0; background: none; padding: 0; cursor: pointer; font-size: 12.5px; color: var(--muted); white-space: nowrap; transition: color .15s; }
.icon-btn:hover { color: var(--ink); }
.icon-btn.star[aria-pressed="true"] { color: var(--star); }
.icon-btn.read[aria-pressed="true"] { color: var(--accent); }
.paper-card h3 { margin: 0 0 6px; font-family: var(--font-display); font-weight: var(--title-weight); font-size: 21px; line-height: 1.45;
  color: var(--ink); overflow-wrap: anywhere; letter-spacing: .005em; }
html[data-theme="swiss"] .paper-card h3 { font-size: 19px; line-height: 1.4; letter-spacing: -.005em; }
html[data-theme="calm"] .paper-card h3 { font-size: 18.5px; }
.paper-card h3 .num { color: var(--level); font-weight: 400; margin-right: 10px; font-variant-numeric: tabular-nums; font-size: .82em; }
html[data-theme="editorial"] .paper-card h3 .num { font-style: italic; }
.meta { margin: 0 0 4px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.en-title { font-style: italic; color: var(--ink-soft); }
html[data-theme="swiss"] .en-title, html[data-theme="calm"] .en-title { font-style: normal; }
.en-title .k { display: none; }
.venue { display: block; margin: 2px 0 10px; color: var(--muted); font-size: 12.5px; letter-spacing: .02em; overflow-wrap: anywhere; }
.venue .k { display: none; }
.summary { margin: 10px 0 4px; color: var(--ink-soft); line-height: 1.9; overflow-wrap: anywhere; max-width: 46em; }
.card-details { margin-top: 8px; }
.card-details > summary { cursor: pointer; list-style: none; display: inline-block; color: var(--muted); font-size: 13px; }
.card-details > summary::-webkit-details-marker { display: none; }
.card-details > summary::after { content: " ↓"; transition: none; }
.card-details[open] > summary::after { content: " ↑"; }
.card-details > summary:hover { color: var(--accent); }
.details-body { overflow: hidden; }
.card-details .details-body { max-width: 46em; }
.card-details .details-body > :first-child { margin-top: 8px; }
.details-body p { margin: 6px 0; overflow-wrap: anywhere; color: var(--ink-soft); font-size: 14px; }
.actions { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 12px; font-size: 13px; }
.action { color: var(--accent); text-decoration: none; }
.action::after { content: " ↗"; }
.action:hover { text-decoration: underline; }

html[data-theme="calm"] .paper-list:not(.rows) { gap: 12px; }
html[data-theme="calm"] .paper-card.full { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
html[data-theme="calm"] .paper-card.full:hover { border-color: var(--rule-strong); }

/* rows (low / off-topic / irrelevant) */
.paper-card.row { border-bottom: 1px solid var(--rule); }
.row-details > summary { list-style: none; cursor: pointer; display: flex; align-items: baseline; gap: 16px; padding: 11px 0; }
.row-details > summary::-webkit-details-marker { display: none; }
.row-main { min-width: 0; flex: 1 1 auto; display: block; }
.row-main .title-zh { display: block; font-size: 15px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-en { display: block; color: var(--muted); font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-details[open] .row-main .title-zh, .row-details[open] .row-en { white-space: normal; }
.row-details > summary:hover .title-zh { color: var(--accent); }
.row-side { display: flex; align-items: baseline; gap: 14px; flex: 0 0 auto; }
.venue-chip { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 12px; }
.row-body { padding: 0 0 16px; max-width: 46em; }
html[data-theme="calm"] .paper-list.rows { background: var(--surface); border: 1px solid var(--rule); border-radius: 16px; padding: 0 20px; }
html[data-theme="calm"] .paper-list.rows > .paper-card.row:last-child { border-bottom: 0; }

.paper-card.is-read > * { opacity: .5; }
.paper-card.is-read:hover > * { opacity: .85; }
.paper-card.is-starred .title-zh::after { content: " ★"; color: var(--star); font-size: .8em; }

.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; margin-top: 14px; max-width: 46em; }
.image-grid img { width: 100%; max-height: 280px; object-fit: contain; background: #fff; border: 1px solid var(--rule); cursor: zoom-in;
  border-radius: calc(var(--radius) / 2); }
.image-grid:empty { display: none; }

/* filter changes fade in place: opacity only, no movement */
@media (prefers-reduced-motion: no-preference) { .paper-card.flash { animation: flash .3s ease; } }
@keyframes flash { from { opacity: 0; } }

.skipped-list { margin: 0; padding-left: 18px; font-size: 13px; color: var(--ink-soft); }
.skipped-list span, .skipped-list em { color: var(--muted); margin-left: 8px; }
.empty { padding: 40px 0; text-align: center; color: var(--muted); }
footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 12.5px;
  padding-top: 22px; margin-top: 30px; border-top: 1px solid var(--rule); }
.theme-switch { display: flex; gap: 12px; align-items: baseline; }
.theme-switch button { border: 0; background: none; padding: 0; cursor: pointer; color: var(--muted); font-size: 12.5px; }
.theme-switch button[aria-pressed="true"] { color: var(--ink); text-decoration: underline; text-underline-offset: 4px; }

.lightbox { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 24px; cursor: zoom-out;
  background: rgba(20, 18, 15, .82); opacity: 0; transition: opacity .2s ease; }
.lightbox.show { opacity: 1; }
.lightbox img { max-width: min(96vw, 1400px); max-height: 92vh; background: #fff; }
dialog { width: min(680px, calc(100vw - 32px)); border: 1px solid var(--rule-strong); border-radius: calc(var(--radius) + 4px); padding: 22px;
  background: var(--surface); color: var(--ink); }
dialog::backdrop { background: rgba(20, 18, 15, .4); }
dialog h2 { margin: 0 0 4px; font-family: var(--font-display); font-weight: var(--title-weight); font-size: 19px; }
dialog p { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
dialog textarea { width: 100%; height: 300px; padding: 12px; border: 1px solid var(--rule); background: var(--bg); color: var(--ink);
  font: 12.5px/1.6 ui-monospace, Menlo, monospace; resize: vertical; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 18px; margin-top: 12px; }
.to-top { position: fixed; right: 24px; bottom: 24px; z-index: 30; width: 38px; height: 38px; border: 1px solid var(--rule-strong);
  border-radius: 50%; background: var(--surface); color: var(--ink-soft); cursor: pointer; opacity: 0; pointer-events: none; transition: opacity .2s ease; }
.to-top.show { opacity: 1; pointer-events: auto; }

@media (max-width: 960px) {
  .layout { grid-template-columns: 1fr; gap: 20px; }
  .side { position: static; grid-template-columns: 1fr 1fr; gap: 20px; }
}
@media (max-width: 640px) {
  body { font-size: 15px; }
  .masthead { padding: 34px 0 20px; }
  h1, html[data-theme="editorial"] h1, html[data-theme="swiss"] h1 { font-size: 32px; }
  html[data-theme="swiss"] .hero-summary a { min-width: 0; padding-right: 18px; }
  .toolbar { position: static; }
  .chips, .tools { flex-wrap: nowrap; overflow-x: auto; max-width: 100%; }
  .tools { margin-left: 0; }
  .side { grid-template-columns: 1fr; }
  .venue-chip { display: none; }
  .section-heading p, .section-heading-note { display: none; }
  html[data-theme="calm"] .paper-card.full { padding: 16px; }
}
@media print {
  .toolbar, .side, .to-top, .progress, .icon-btn, .text-btn, .theme-switch { display: none !important; }
  .layout { grid-template-columns: 1fr; }
}
"""

DIGEST_JS = r"""
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const motionOK = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const digest = JSON.parse(document.querySelector('#digest-data').textContent);
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  const search = $('#search');
  const buttons = $$('[data-filter]');
  const cards = $$('.paper-card');
  const sections = $$('[data-section-level]');
  const folded = $$('.folded-section');
  const resultCount = $('#result-count');
  const empty = $('#empty');
  const hideReadButton = $('#hide-read');
  let activeFilter = 'all';
  let hideRead = false;

  // ---- reader state (per browser; shared by every digest opened from this machine) ----
  const KEY = 'scholarinbox:v1';
  const RETENTION_MS = 60 * 24 * 3600 * 1000;
  const state = { read: {}, starred: {} };
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
    state.read = saved.read || {};
    state.starred = saved.starred || {};
  } catch (error) { /* storage unavailable: state lives for this page only */ }
  function save() {
    // Read and starred marks expire after 60 days, matching digest.cleanup_old_outputs.
    const expiry = Date.now() - RETENTION_MS;
    for (const id of Object.keys(state.read)) if (state.read[id] < expiry) delete state.read[id];
    for (const id of Object.keys(state.starred)) if (!(state.starred[id].t >= expiry)) delete state.starred[id];
    const ids = Object.keys(state.read);
    if (ids.length > 6000) {
      ids.sort((a, b) => state.read[a] - state.read[b]).slice(0, ids.length - 6000).forEach(id => delete state.read[id]);
    }
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (error) { /* ignore */ }
  }
  function meta(card) {
    const title = card.querySelector('.title-zh');
    return {
      t: Date.now(), date: digest.date, title_zh: title ? title.textContent.trim() : '',
      title: card.dataset.title || '', venue: card.dataset.venue || '', doi: card.dataset.doi || '', url: card.dataset.url || '',
    };
  }
  function paint(card) {
    const id = card.dataset.id;
    const read = Boolean(state.read[id]);
    const starred = Boolean(state.starred[id]);
    card.classList.toggle('is-read', read);
    card.classList.toggle('is-starred', starred);
    for (const button of $$('[data-action="read"]', card)) {
      button.setAttribute('aria-pressed', String(read));
      button.textContent = read ? '已读 ✓' : '标为已读';
    }
    for (const button of $$('[data-action="star"]', card)) {
      button.setAttribute('aria-pressed', String(starred));
      button.textContent = starred ? '★ 已收藏' : '☆ 收藏';
    }
  }
  function setRead(card, value) {
    if (value) state.read[card.dataset.id] = Date.now(); else delete state.read[card.dataset.id];
    paint(card);
  }
  function refreshMeter() {
    const read = cards.filter(card => state.read[card.dataset.id]).length;
    const starredHere = cards.filter(card => state.starred[card.dataset.id]).length;
    $('#read-meter').style.width = cards.length ? `${(read / cards.length) * 100}%` : '0';
    $('#read-label').textContent = `已读 ${read} / ${cards.length}`;
    $('#star-count').textContent = String(Object.keys(state.starred).length);
    $('#star-chip-count').textContent = String(starredHere);
  }
  save();
  cards.forEach(paint);

  // ---- filtering ----
  function applyFilters(resetFolded = false) {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const card of cards) {
      const level = activeFilter === 'all' || card.dataset.level === activeFilter
        || (activeFilter === 'starred' && card.classList.contains('is-starred'));
      const show = level && (!query || card.dataset.search.includes(query)) && (!hideRead || !card.classList.contains('is-read'));
      if (show && card.hidden && motionOK) { card.classList.remove('flash'); void card.offsetWidth; card.classList.add('flash'); }
      card.hidden = !show;
      if (show) visible += 1;
    }
    for (const section of sections) {
      const count = $$('.paper-card:not([hidden])', section).length;
      section.hidden = count === 0;
      const pill = $('.count-pill', section);
      if (pill) pill.textContent = `${count} 条`;
      const nav = $(`.side-nav [data-nav="${section.dataset.sectionLevel}"] .nav-count`);
      if (nav) nav.textContent = String(count);
    }
    for (const section of folded) {
      if (section.hidden) continue;
      if (activeFilter === section.dataset.sectionLevel || activeFilter === 'starred' || query) section.open = true;
      else if (resetFolded) section.open = false;
    }
    empty.hidden = visible > 0;
    resultCount.textContent = `显示 ${visible} / ${cards.length} 条`;
    refreshMeter();
  }
  for (const button of buttons) {
    button.addEventListener('click', () => {
      activeFilter = button.dataset.filter;
      for (const item of buttons) item.setAttribute('aria-pressed', String(item === button));
      applyFilters(activeFilter === 'all');
    });
  }
  search.addEventListener('input', () => applyFilters(activeFilter === 'all' && !search.value.trim()));
  hideReadButton.addEventListener('click', () => {
    hideRead = !hideRead;
    hideReadButton.setAttribute('aria-pressed', String(hideRead));
    applyFilters();
  });

  // ---- smooth <details> open/close ----
  function toggleDetails(details, open) {
    const body = details.querySelector(':scope > .details-body');
    if (!body || !motionOK || !body.animate) { details.open = open; return; }
    if (details._animation) details._animation.cancel();
    details._closing = !open;
    if (open) details.open = true;
    const height = body.scrollHeight;
    const frames = [{ height: '0px', opacity: 0 }, { height: `${height}px`, opacity: 1 }];
    const animation = body.animate(open ? frames : frames.reverse(), {
      duration: open ? Math.min(420, 220 + height / 8) : 200, easing: open ? 'cubic-bezier(.2,.7,.2,1)' : 'ease-in',
    });
    details._animation = animation;
    animation.onfinish = () => { details._animation = null; details._closing = false; if (!open) details.open = false; };
    animation.oncancel = () => { details._animation = null; details._closing = false; };
  }
  document.addEventListener('click', event => {
    const summary = event.target.closest('summary');
    if (!summary || event.target.closest('a, button')) return;
    const details = summary.parentElement;
    if (!(details instanceof HTMLDetailsElement)) return;
    event.preventDefault();
    toggleDetails(details, details._closing ? true : !details.open);
  });
  $('#expand-all').addEventListener('click', () => {
    for (const section of folded) if (!section.hidden) section.open = true;
    for (const item of $$('.paper-card:not([hidden]) details')) item.open = true;
  });
  $('#collapse-all').addEventListener('click', () => {
    for (const item of $$('.paper-card details')) item.open = false;
    for (const section of folded) section.open = false;
  });

  // ---- card actions ----
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    const card = target.closest('.paper-card');
    const action = target.dataset.action;
    if (action === 'open' && card) { setRead(card, true); save(); refreshMeter(); return; }
    if (action === 'read' && card) setRead(card, !state.read[card.dataset.id]);
    if (action === 'star' && card) {
      if (state.starred[card.dataset.id]) delete state.starred[card.dataset.id]; else state.starred[card.dataset.id] = meta(card);
      paint(card);
    }
    if (action === 'mark-section') {
      const section = target.closest('[data-section-level]');
      const pending = $$('.paper-card:not([hidden])', section);
      const allRead = pending.every(item => state.read[item.dataset.id]);
      pending.forEach(item => setRead(item, !allRead));
    }
    if (motionOK && target.classList.contains('icon-btn')) { target.classList.remove('pop'); void target.offsetWidth; target.classList.add('pop'); }
    save();
    if (hideRead && action !== 'star') applyFilters(); else refreshMeter();
  });

  // ---- export starred ----
  const dialog = $('#export-dialog');
  function exportText() {
    const items = Object.values(state.starred).sort((a, b) => a.t - b.t);
    const lines = [`# ScholarInbox 收藏（${items.length} 篇，导出于 ${new Date().toLocaleDateString('zh-CN')}）`, ''];
    for (const item of items) {
      lines.push(`- **${item.title_zh || item.title}**`);
      const parts = [item.title, item.venue, item.doi ? `DOI: ${item.doi}` : '', item.url ? `[链接](${item.url})` : '', item.date ? `日报 ${item.date}` : '']
        .filter(Boolean);
      lines.push(`  ${parts.join(' · ')}`);
    }
    return lines.join('\n') + '\n';
  }
  $('#export-starred').addEventListener('click', () => {
    $('#export-text').value = exportText();
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
  });
  $('#export-copy').addEventListener('click', async event => {
    const area = $('#export-text');
    try { await navigator.clipboard.writeText(area.value); }
    catch (error) { area.select(); document.execCommand('copy'); }
    event.target.textContent = '已复制 ✓';
    setTimeout(() => { event.target.textContent = '复制'; }, 1600);
  });
  $('#export-download').addEventListener('click', () => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([$('#export-text').value], { type: 'text/markdown;charset=utf-8' }));
    link.download = `scholarinbox-starred-${digest.date}.md`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });
  $('#export-close').addEventListener('click', () => dialog.close ? dialog.close() : dialog.removeAttribute('open'));

  // ---- images & lightbox ----
  const lightbox = $('#lightbox');
  for (const img of $$('.image-grid img')) {
    img.addEventListener('error', () => img.remove());
    img.addEventListener('load', () => { if (img.naturalWidth <= 4 || img.naturalHeight <= 4) img.remove(); });
    img.addEventListener('click', () => {
      $('img', lightbox).src = img.currentSrc || img.src;
      lightbox.hidden = false;
      requestAnimationFrame(() => lightbox.classList.add('show'));
    });
  }
  function closeLightbox() {
    if (lightbox.hidden) return;
    lightbox.classList.remove('show');
    setTimeout(() => { lightbox.hidden = true; }, motionOK ? 250 : 0);
  }
  lightbox.addEventListener('click', closeLightbox);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeLightbox(); });

  // ---- scroll: progress bar, back-to-top, active section ----
  const progress = $('#progress');
  const toTop = $('#to-top');
  let ticking = false;
  function onScroll() {
    ticking = false;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    progress.style.transform = `scaleX(${max > 0 ? Math.min(1, window.scrollY / max) : 0})`;
    toTop.classList.toggle('show', window.scrollY > 700);
  }
  window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  toTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: motionOK ? 'smooth' : 'auto' }));
  onScroll();

  for (const link of $$('.side-nav a, .hero-summary a')) {
    link.addEventListener('click', () => {
      const section = document.getElementById(link.getAttribute('href').slice(1));
      if (section instanceof HTMLDetailsElement) section.open = true;
    });
  }
  if ('IntersectionObserver' in window) {
    const navLinks = new Map($$('.side-nav a').map(link => [link.dataset.nav, link]));
    const spy = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        navLinks.forEach(link => link.classList.remove('active'));
        const link = navLinks.get(entry.target.dataset.sectionLevel);
        if (link) link.classList.add('active');
      }
    }, { rootMargin: '-25% 0px -65% 0px' });
    sections.forEach(section => spy.observe(section));
  }

  // ---- reading style switcher (per browser) ----
  for (const button of $$('[data-theme-choice]')) {
    button.setAttribute('aria-pressed', String(button.dataset.themeChoice === root.dataset.theme));
    button.addEventListener('click', () => {
      root.dataset.theme = button.dataset.themeChoice;
      try { localStorage.setItem('scholarinbox:theme', root.dataset.theme); } catch (error) { /* ignore */ }
      for (const other of $$('[data-theme-choice]')) other.setAttribute('aria-pressed', String(other === button));
    });
  }

  applyFilters(true);
})();
"""
