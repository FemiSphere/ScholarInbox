"""Inline stylesheet and script for the HTML digest.

Kept separate from ``digest.py`` so the page structure stays readable. Both are
plain strings (not f-strings); ``render_html`` inlines them so a digest remains a
single self-contained file that opens from ``file://`` without a server.
Reader state (read / starred) lives only in the browser's localStorage.
"""

DIGEST_CSS = r"""
/* =====================================================================
   Four bright reading styles on one structure (html[data-theme]).
   Static decoration only: no scroll-driven or looping animation, no
   backdrop blur, no hover movement - colour/shadow changes only.
   ===================================================================== */
:root, html[data-theme="pop"] {
  --bg: #fff5e1; --surface: #ffffff; --surface-soft: #fff0cf;
  --ink: #141414; --ink-soft: #2f2f2f; --muted: #6f6a60; --rule: #141414; --line: rgba(20, 20, 20, .14);
  --accent: #ff5d4a; --accent-2: #2f6bff; --accent-soft: #ffe1db;
  --high: #ff5d4a; --medium: #ffc83a; --low: #6fc8ff; --off_topic: #b9a7ff; --irrelevant: #d6d2c8;
  --star: #ff9f1a;
  --font-display: "Avenir Next", "Futura", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --radius: 14px;
}
html[data-theme="bauhaus"] {
  --bg: #ffffff; --surface: #ffffff; --surface-soft: #f3f3ef;
  --ink: #111111; --ink-soft: #333333; --muted: #7b7b7b; --rule: #111111; --line: #e6e6e6;
  --accent: #1f3fd6; --accent-2: #e8402f; --accent-soft: #e8ecff;
  --high: #e8402f; --medium: #1f3fd6; --low: #ffb81c; --off_topic: #9a9a9a; --irrelevant: #c4c4c4;
  --star: #ffb81c;
  --font-display: "Futura", "Avenir Next", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  --radius: 0px;
}
html[data-theme="riso"] {
  --bg: #f6f1e6; --surface: #fbf8f1; --surface-soft: #efe8da;
  --ink: #1d2253; --ink-soft: #3a3f6e; --muted: #7d7a8e; --rule: #1d2253; --line: rgba(255, 72, 163, .35);
  --accent: #ff48a3; --accent-2: #1f6fd6; --accent-soft: #ffe0ef;
  --high: #ff48a3; --medium: #1f6fd6; --low: #7a7fa8; --off_topic: #a9a6b8; --irrelevant: #c6c2cf;
  --star: #ff48a3;
  --font-display: "Avenir Next Condensed", "Avenir Next", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --radius: 0px;
}
html[data-theme="fresh"] {
  --bg: #f5f6fb; --surface: #ffffff; --surface-soft: #eef0f8;
  --ink: #1b1d2b; --ink-soft: #3f4256; --muted: #858aa3; --rule: #e3e6f0; --line: #eceef5;
  --accent: #6a5cff; --accent-2: #ff6b8b; --accent-soft: #ecebff;
  --high: #ff5f87; --medium: #ff9f2e; --low: #2bbf9a; --off_topic: #8c9ac0; --irrelevant: #b9c0d4;
  --star: #ffb020;
  --font-display: ui-rounded, "SF Pro Rounded", "Avenir Next", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-body: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --radius: 20px;
}

/* ------------------------------------------------------------- base */
* { box-sizing: border-box; }
html { color-scheme: light; -webkit-text-size-adjust: 100%; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: 15.5px; line-height: 1.7;
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
a { color: inherit; text-underline-offset: 3px; }
button { font: inherit; color: inherit; }
[hidden] { display: none !important; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; }
:focus-visible { outline: 3px solid var(--accent-2); outline-offset: 3px; }
::selection { background: var(--accent-soft); }
.shell { width: min(1180px, calc(100vw - 40px)); margin: 0 auto; position: relative; }
.progress { position: fixed; inset: 0 0 auto 0; height: 4px; z-index: 50; pointer-events: none;
  background: linear-gradient(90deg, var(--high), var(--medium), var(--low)); transform-origin: 0 50%; transform: scaleX(0); will-change: transform; }

/* masthead */
.masthead { position: relative; overflow: hidden; padding: 56px 0 40px; }
.masthead .shell { display: grid; gap: 14px; }
.deco { position: absolute; inset: 0; pointer-events: none; }
.deco i { position: absolute; display: block; }
.kicker { margin: 0; display: flex; gap: 12px; align-items: center; font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 0; font-family: var(--font-display); font-weight: 800; font-size: 64px; line-height: 1.05; letter-spacing: -.02em; }
.subtitle { margin: 0; font-size: 16px; color: var(--ink-soft); }
.hero-summary { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; }
.hero-summary a { text-decoration: none; display: grid; gap: 0; min-width: 104px; padding: 12px 16px; }
.hero-summary strong { font-family: var(--font-display); font-size: 36px; font-weight: 800; line-height: 1.05; font-variant-numeric: tabular-nums lining-nums; }
.hero-summary span { font-size: 13px; font-weight: 600; }

/* toolbar - solid background */
.toolbar { position: sticky; top: 0; z-index: 20; background: var(--bg); padding: 12px 0; }
.toolbar .shell { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
.search { flex: 1 1 200px; min-width: 0; }
.search input { width: 100%; height: 38px; padding: 0 16px; border: 2px solid var(--rule); background: var(--surface); color: var(--ink);
  font-size: 14.5px; outline: none; border-radius: var(--radius); }
.search input::placeholder { color: var(--muted); }
.chips, .tools { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.tools { margin-left: auto; }
.chip, .tool { height: 32px; padding: 0 11px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap;
  background: var(--surface); border: 2px solid var(--rule); border-radius: 999px; color: var(--ink); transition: background .15s, color .15s, box-shadow .15s; }
.chip[aria-pressed="true"] { background: var(--ink); color: var(--bg); }
.tool[aria-pressed="true"] { background: var(--accent-soft); }

/* layout */
.layout { display: grid; grid-template-columns: 210px minmax(0, 1fr); gap: 40px; padding: 30px 0 80px; }
.layout > main { min-width: 0; }
.side { position: sticky; top: 84px; align-self: start; display: grid; gap: 18px; font-size: 13.5px; }
.side-card { background: var(--surface); border: 2px solid var(--rule); border-radius: var(--radius); padding: 14px 16px; }
.side-title { margin: 0 0 8px; font-size: 11px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
.side-nav a { display: flex; align-items: center; gap: 10px; padding: 5px 8px; margin: 0 -8px; border-radius: 10px; text-decoration: none; font-weight: 600;
  transition: background .15s; }
.side-nav a:hover { background: var(--surface-soft); }
.side-nav a.active { background: var(--surface-soft); }
.side-nav .dot { width: 12px; height: 12px; border-radius: 50%; background: var(--level, var(--muted)); border: 2px solid var(--rule); flex: 0 0 12px; }
.side-nav .nav-count { margin-left: auto; font-variant-numeric: tabular-nums; color: var(--muted); }
.meter { height: 8px; border: 2px solid var(--rule); border-radius: 999px; overflow: hidden; margin: 12px 0 6px; background: var(--surface); }
.meter i { display: block; height: 100%; width: 0; background: var(--low); transition: width .4s ease; }
.meter-label { color: var(--muted); font-size: 12px; font-weight: 600; }
.facts { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; margin: 0; }
.facts div { display: contents; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }

/* panels */
.panel { margin: 0 0 22px; }
.panel h2 { margin: 0 0 6px; font-family: var(--font-display); font-weight: 800; font-size: 18px; }
.panel p { margin: 0; color: var(--ink-soft); font-size: 14.5px; }
.interest-panel { background: var(--surface); border: 2px solid var(--rule); border-radius: var(--radius); padding: 18px 20px; }
.warning-panel { background: var(--surface-soft); border: 2px solid var(--rule); border-radius: var(--radius); padding: 12px 18px; }
.warning-panel ul { margin: 0; padding-left: 18px; font-size: 13.5px; color: var(--ink-soft); }
.topics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.tag { font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px; background: var(--surface-soft); color: var(--ink-soft); }

/* sections */
.list-intro { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 10px 0; }
.list-intro h2 { margin: 0; font-family: var(--font-display); font-weight: 800; font-size: 14px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
.result-count { color: var(--muted); font-size: 12.5px; font-weight: 600; }
.paper-section { margin: 0 0 48px; scroll-margin-top: 76px; --level: var(--muted); }
.paper-section[data-section-level="high"], .paper-card[data-level="high"], .side-nav [data-nav="high"] { --level: var(--high); }
.paper-section[data-section-level="medium"], .paper-card[data-level="medium"], .side-nav [data-nav="medium"] { --level: var(--medium); }
.paper-section[data-section-level="low"], .paper-card[data-level="low"], .side-nav [data-nav="low"] { --level: var(--low); }
.paper-section[data-section-level="off_topic"], .paper-card[data-level="off_topic"], .side-nav [data-nav="off_topic"] { --level: var(--off_topic); }
.paper-section[data-section-level="irrelevant"], .paper-card[data-level="irrelevant"], .side-nav [data-nav="irrelevant"] { --level: var(--irrelevant); }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin: 0 0 16px; }
.section-label { display: inline-block; font-size: 11px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
.section-heading h2, .section-heading-title { display: block; margin: 4px 0 0; font-family: var(--font-display); font-weight: 800; font-size: 32px; line-height: 1.15; color: var(--ink); }
.section-heading p, .section-heading-note { display: block; margin: 4px 0 0; color: var(--muted); font-size: 13.5px; font-weight: 500; font-family: var(--font-body); }
.section-tools { display: flex; align-items: center; gap: 12px; flex: 0 0 auto; font-size: 12.5px; }
.count-pill { font-weight: 800; font-variant-numeric: tabular-nums; }
.text-btn { border: 0; background: none; padding: 0; cursor: pointer; font-size: 12.5px; font-weight: 600; color: var(--muted); }
.text-btn:hover { color: var(--ink); text-decoration: underline; }
.folded-section > summary { list-style: none; cursor: pointer; }
.folded-section > summary::-webkit-details-marker { display: none; }
.folded-section > summary .section-heading-title::after { content: "+"; display: inline-grid; place-items: center; width: 28px; height: 28px; margin-left: 12px;
  font-size: 20px; line-height: 1; vertical-align: middle; border: 2px solid var(--rule); border-radius: 50%; transition: transform .25s ease; }
.folded-section[open] > summary .section-heading-title::after { transform: rotate(45deg); }

/* papers */
.paper-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }
.paper-list > .paper-card { min-width: 0; }
.paper-card { position: relative; }
.paper-card.full { padding: 22px 24px 20px; background: var(--surface); border: 2px solid var(--rule); border-radius: var(--radius);
  transition: box-shadow .18s ease, opacity .2s ease; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 800;
  white-space: nowrap; background: var(--level); color: var(--ink); border: 2px solid var(--rule); font-variant-numeric: tabular-nums; }
.card-tools { display: flex; gap: 6px; }
.icon-btn { height: 30px; padding: 0 11px; cursor: pointer; font-size: 12px; font-weight: 700; white-space: nowrap; border-radius: 999px;
  background: var(--surface); border: 2px solid var(--rule); transition: background .15s; }
.icon-btn:hover { background: var(--surface-soft); }
.icon-btn.star[aria-pressed="true"] { background: var(--star); }
.icon-btn.read[aria-pressed="true"] { background: var(--low); }
.paper-card h3 { margin: 0 0 6px; font-family: var(--font-display); font-weight: 800; font-size: 22px; line-height: 1.4; overflow-wrap: anywhere; }
.paper-card h3 .num { margin-right: 10px; font-variant-numeric: tabular-nums; }
.meta { margin: 0 0 4px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.en-title .k, .venue .k { display: none; }
.en-title { color: var(--ink-soft); }
.venue { display: inline-block; margin: 4px 0 10px; font-size: 12.5px; font-weight: 700; color: var(--ink-soft); overflow-wrap: anywhere; }
.summary { margin: 10px 0 4px; color: var(--ink-soft); line-height: 1.9; overflow-wrap: anywhere; }
.card-details { margin-top: 8px; }
.card-details > summary { cursor: pointer; list-style: none; display: inline-block; font-size: 13px; font-weight: 700; }
.card-details > summary::-webkit-details-marker { display: none; }
.card-details > summary::after { content: " ↓"; }
.card-details[open] > summary::after { content: " ↑"; }
.details-body { overflow: hidden; }
.card-details .details-body > :first-child { margin-top: 8px; }
.details-body p { margin: 6px 0; overflow-wrap: anywhere; color: var(--ink-soft); font-size: 14px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.action { display: inline-flex; align-items: center; height: 34px; padding: 0 16px; border-radius: 999px; font-size: 13px; font-weight: 800; text-decoration: none;
  background: var(--ink); color: var(--bg); border: 2px solid var(--rule); transition: background .15s, color .15s; }
.action::after { content: "↗"; margin-left: 6px; }
.action:hover { background: var(--accent); color: var(--ink); }

/* rows */
.paper-list.rows { gap: 0; background: var(--surface); border: 2px solid var(--rule); border-radius: var(--radius); overflow: hidden; }
.paper-card.row { border-bottom: 1px solid var(--line); }
.paper-list.rows > .paper-card.row:last-child { border-bottom: 0; }
.row-details > summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 14px; padding: 12px 18px; transition: background .15s; }
.row-details > summary:hover { background: var(--surface-soft); }
.row-details > summary::-webkit-details-marker { display: none; }
.row-main { min-width: 0; flex: 1 1 auto; display: block; }
.row-main .title-zh { display: block; font-size: 15px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-en { display: block; color: var(--muted); font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-details[open] .row-main .title-zh, .row-details[open] .row-en { white-space: normal; }
.row-side { display: flex; align-items: center; gap: 12px; flex: 0 0 auto; }
.venue-chip { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 12px; font-weight: 600; }
.row-side .badge { padding: 1px 8px; font-size: 11px; }
.row-body { padding: 4px 18px 18px; }
.paper-card.is-read > * { opacity: .45; }
.paper-card.is-read:hover > * { opacity: .85; }
.paper-card.is-starred .title-zh::after { content: " ★"; color: var(--star); }

.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; margin-top: 14px; }
.image-grid img { width: 100%; max-height: 280px; object-fit: contain; background: #fff; border: 2px solid var(--rule); border-radius: calc(var(--radius) * .6); cursor: zoom-in; }
.image-grid:empty { display: none; }
@media (prefers-reduced-motion: no-preference) { .paper-card.flash { animation: flash .3s ease; } }
@keyframes flash { from { opacity: 0; } }

.skipped-list { margin: 0; padding-left: 18px; font-size: 13px; color: var(--ink-soft); }
.skipped-list span, .skipped-list em { color: var(--muted); margin-left: 8px; }
.empty { padding: 40px 0; text-align: center; color: var(--muted); font-weight: 600; }
footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 12.5px; padding-top: 22px; margin-top: 30px; border-top: 2px solid var(--rule); }
.theme-switch { display: flex; gap: 6px; align-items: center; font-weight: 700; }
.theme-switch button { cursor: pointer; padding: 3px 11px; border-radius: 999px; border: 2px solid var(--rule); background: var(--surface); font-size: 12px; font-weight: 700; }
.theme-switch button[aria-pressed="true"] { background: var(--ink); color: var(--bg); }

.lightbox { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 24px; cursor: zoom-out; background: rgba(15, 15, 20, .82); opacity: 0; transition: opacity .2s ease; }
.lightbox.show { opacity: 1; }
.lightbox img { max-width: min(96vw, 1400px); max-height: 92vh; background: #fff; border-radius: 8px; }
dialog { width: min(680px, calc(100vw - 32px)); border: 2px solid var(--rule); border-radius: var(--radius); padding: 22px; background: var(--surface); color: var(--ink); }
dialog::backdrop { background: rgba(15, 15, 20, .4); }
dialog h2 { margin: 0 0 4px; font-family: var(--font-display); font-weight: 800; font-size: 20px; }
dialog p { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
dialog textarea { width: 100%; height: 300px; padding: 12px; border: 2px solid var(--rule); border-radius: calc(var(--radius) * .6); background: var(--bg); color: var(--ink); font: 12.5px/1.6 ui-monospace, Menlo, monospace; resize: vertical; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.to-top { position: fixed; right: 24px; bottom: 24px; z-index: 30; width: 44px; height: 44px; border-radius: 50%; border: 2px solid var(--rule); background: var(--surface); font-size: 18px; font-weight: 800;
  cursor: pointer; opacity: 0; pointer-events: none; transition: opacity .2s ease; }
.to-top.show { opacity: 1; pointer-events: auto; }

/* ============================================================= POP (neo-brutalist) */
html[data-theme="pop"] .masthead { padding-bottom: 46px; border-bottom: 2.5px solid var(--rule); }
html[data-theme="pop"] .deco i:nth-child(1) { width: 190px; height: 190px; right: 6%; top: 38px; border-radius: 50%; background: var(--high); border: 2.5px solid var(--rule); box-shadow: 6px 6px 0 var(--rule); }
html[data-theme="pop"] .deco i:nth-child(2) { width: 110px; height: 110px; right: 20%; top: 150px; background: var(--low); border: 2.5px solid var(--rule); transform: rotate(14deg); box-shadow: 6px 6px 0 var(--rule); }
html[data-theme="pop"] .deco i:nth-child(3) { width: 150px; height: 48px; right: 3%; top: 240px; border-radius: 999px; background: var(--medium); border: 2.5px solid var(--rule); transform: rotate(-8deg); box-shadow: 6px 6px 0 var(--rule); }
html[data-theme="pop"] .kicker span:first-child { background: var(--ink); color: var(--bg); padding: 4px 10px; border-radius: 999px; }
html[data-theme="pop"] h1 { font-size: 76px; width: fit-content; background: linear-gradient(transparent 64%, var(--medium) 64%, var(--medium) 92%, transparent 92%); }
html[data-theme="pop"] .hero-summary a { background: var(--level, var(--surface)); border: 2.5px solid var(--rule); border-radius: 16px; box-shadow: 5px 5px 0 var(--rule); transition: box-shadow .15s; }
html[data-theme="pop"] .hero-summary a:hover { box-shadow: 8px 8px 0 var(--rule); }
html[data-theme="pop"] .hero-summary a[href="#sec-high"] { --level: var(--high); }
html[data-theme="pop"] .hero-summary a[href="#sec-medium"] { --level: var(--medium); }
html[data-theme="pop"] .hero-summary a[href="#sec-low"] { --level: var(--low); }
html[data-theme="pop"] .hero-summary a[href="#sec-off_topic"] { --level: var(--off_topic); }
html[data-theme="pop"] .hero-summary a[href="#sec-irrelevant"] { --level: var(--irrelevant); }
html[data-theme="pop"] .toolbar { border-bottom: 2.5px solid var(--rule); }
html[data-theme="pop"] .search input:focus { box-shadow: 4px 4px 0 var(--rule); }
html[data-theme="pop"] .chip:hover, html[data-theme="pop"] .tool:hover { box-shadow: 3px 3px 0 var(--rule); }
html[data-theme="pop"] .side-card, html[data-theme="pop"] .interest-panel, html[data-theme="pop"] .paper-list.rows { box-shadow: 5px 5px 0 var(--rule); }
html[data-theme="pop"] .warning-panel { background: var(--medium); }
html[data-theme="pop"] .section-label { background: var(--level); color: var(--ink); padding: 3px 10px; border: 2px solid var(--rule); border-radius: 999px; }
html[data-theme="pop"] .paper-card.full { box-shadow: 6px 6px 0 var(--rule); }
html[data-theme="pop"] .paper-card.full:hover { box-shadow: 9px 9px 0 var(--level); }
html[data-theme="pop"] .paper-card h3 .num { display: inline-grid; place-items: center; min-width: 34px; height: 34px; padding: 0 6px; border-radius: 10px; background: var(--level);
  border: 2px solid var(--rule); font-size: 16px; vertical-align: 3px; }
html[data-theme="pop"] .venue { background: var(--surface-soft); padding: 2px 10px; border-radius: 8px; border: 1.5px solid var(--rule); }
html[data-theme="pop"] .tag { border: 1.5px solid var(--rule); background: var(--surface); }
html[data-theme="pop"] .card-details > summary { color: var(--accent-2); }

/* ============================================================= BAUHAUS (colour-block poster) */
html[data-theme="bauhaus"] .masthead { background: var(--accent); color: #fff; padding: 64px 0 52px; }
html[data-theme="bauhaus"] .deco i:nth-child(1) { width: 420px; height: 420px; right: -110px; top: -120px; border-radius: 50%; background: var(--low); }
html[data-theme="bauhaus"] .deco i:nth-child(2) { width: 220px; height: 110px; right: 250px; bottom: 0; border-radius: 220px 220px 0 0; background: var(--high); }
html[data-theme="bauhaus"] .deco i:nth-child(3) { width: 64px; height: 64px; right: 120px; bottom: 60px; background: #fff; }
html[data-theme="bauhaus"] .kicker, html[data-theme="bauhaus"] .subtitle { color: rgba(255, 255, 255, .85); }
html[data-theme="bauhaus"] h1 { font-size: 84px; letter-spacing: -.03em; color: #fff; max-width: 9em; }
html[data-theme="bauhaus"] .hero-summary { gap: 0; margin-top: 18px; }
html[data-theme="bauhaus"] .hero-summary a { padding: 12px 34px 0 0; color: #fff; min-width: 120px; }
html[data-theme="bauhaus"] .hero-summary strong { font-size: 54px; font-weight: 700; }
html[data-theme="bauhaus"] .hero-summary span { color: rgba(255, 255, 255, .8); }
html[data-theme="bauhaus"] .toolbar { border-bottom: 3px solid var(--rule); }
html[data-theme="bauhaus"] .search input, html[data-theme="bauhaus"] .chip, html[data-theme="bauhaus"] .tool,
html[data-theme="bauhaus"] .side-card, html[data-theme="bauhaus"] .interest-panel, html[data-theme="bauhaus"] .warning-panel,
html[data-theme="bauhaus"] .icon-btn, html[data-theme="bauhaus"] .action, html[data-theme="bauhaus"] .theme-switch button, html[data-theme="bauhaus"] .badge { border-radius: 0; }
html[data-theme="bauhaus"] .chip, html[data-theme="bauhaus"] .tool { border-width: 0 0 3px; background: transparent; height: 34px; padding: 0 6px; border-bottom-color: transparent; }
html[data-theme="bauhaus"] .chip[aria-pressed="true"] { background: transparent; color: var(--ink); border-bottom-color: var(--low); }
html[data-theme="bauhaus"] .side-card, html[data-theme="bauhaus"] .interest-panel { border: 0; border-top: 6px solid var(--rule); padding-left: 0; padding-right: 0; }
html[data-theme="bauhaus"] .warning-panel { border: 0; background: var(--low); }
html[data-theme="bauhaus"] .side-nav .dot { border-radius: 0; border: 0; }
html[data-theme="bauhaus"] .section-heading { padding-top: 14px; border-top: 6px solid var(--level); }
html[data-theme="bauhaus"] .section-label { color: var(--level); }
html[data-theme="bauhaus"] .section-heading h2, html[data-theme="bauhaus"] .section-heading-title { font-size: 40px; letter-spacing: -.02em; }
html[data-theme="bauhaus"] .folded-section > summary .section-heading-title::after { border-radius: 0; }
html[data-theme="bauhaus"] .paper-list { gap: 0; }
html[data-theme="bauhaus"] .paper-card.full { border: 0; border-bottom: 2px solid var(--line); padding: 26px 0 24px 92px; }
html[data-theme="bauhaus"] .paper-card h3 .num { position: absolute; left: 0; top: 20px; font-family: var(--font-display); font-size: 56px; font-weight: 700; line-height: 1; color: var(--level); letter-spacing: -.04em; }
html[data-theme="bauhaus"] .badge { background: transparent; border: 0; padding: 0; color: var(--level); letter-spacing: .1em; }
html[data-theme="bauhaus"] .icon-btn { border-width: 2px; }
html[data-theme="bauhaus"] .icon-btn.read[aria-pressed="true"] { background: var(--low); }
html[data-theme="bauhaus"] .tag { border-radius: 0; background: var(--surface-soft); }
html[data-theme="bauhaus"] .action { background: var(--accent); color: #fff; border-color: var(--accent); }
html[data-theme="bauhaus"] .action:hover { background: var(--high); border-color: var(--high); color: #fff; }
html[data-theme="bauhaus"] .paper-list.rows { border: 0; border-top: 2px solid var(--rule); border-radius: 0; }
html[data-theme="bauhaus"] .row-details > summary { padding-left: 0; padding-right: 0; }
html[data-theme="bauhaus"] .row-body { padding-left: 0; }

/* ============================================================= RISO (duotone print) */
html[data-theme="riso"] .masthead { padding: 60px 0 46px; border-bottom: 3px solid var(--accent);
  background-image: radial-gradient(rgba(255, 72, 163, .28) 1.4px, transparent 1.6px); background-size: 12px 12px; background-position: right top; }
html[data-theme="riso"] .deco i:nth-child(1) { width: 260px; height: 260px; right: 7%; top: 30px; border-radius: 50%; background: var(--accent-2); mix-blend-mode: multiply; opacity: .85; }
html[data-theme="riso"] .deco i:nth-child(2) { width: 260px; height: 260px; right: calc(7% + 120px); top: 90px; border-radius: 50%; background: var(--accent); mix-blend-mode: multiply; opacity: .85; }
html[data-theme="riso"] .deco i:nth-child(3) { display: none; }
html[data-theme="riso"] .kicker { color: var(--accent); }
html[data-theme="riso"] h1 { font-size: 80px; color: var(--accent-2); text-shadow: 4px 3px 0 var(--accent); letter-spacing: -.01em; }
html[data-theme="riso"] .subtitle { color: var(--ink); font-weight: 600; }
html[data-theme="riso"] .hero-summary a { padding: 8px 26px 0 0; min-width: 100px; }
html[data-theme="riso"] .hero-summary strong { font-size: 48px; color: var(--accent); text-shadow: 3px 2px 0 var(--accent-2); }
html[data-theme="riso"] .toolbar { border-bottom: 2px dashed var(--accent); }
html[data-theme="riso"] .search input, html[data-theme="riso"] .side-card, html[data-theme="riso"] .interest-panel, html[data-theme="riso"] .paper-list.rows { border-color: var(--accent-2); }
html[data-theme="riso"] .chip, html[data-theme="riso"] .tool, html[data-theme="riso"] .icon-btn, html[data-theme="riso"] .theme-switch button { border-color: var(--accent-2); color: var(--accent-2); }
html[data-theme="riso"] .chip[aria-pressed="true"], html[data-theme="riso"] .theme-switch button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
html[data-theme="riso"] .warning-panel { border: 2px dashed var(--accent); background: var(--accent-soft); }
html[data-theme="riso"] .section-heading h2, html[data-theme="riso"] .section-heading-title { font-size: 38px; color: var(--ink);
  background: linear-gradient(transparent 58%, var(--accent-soft) 58%); width: fit-content; }
html[data-theme="riso"] .section-label { color: var(--level); }
html[data-theme="riso"] .paper-list { gap: 0; }
html[data-theme="riso"] .paper-card.full { border: 0; border-bottom: 2px dotted var(--accent); border-radius: 0; background: transparent; padding: 26px 0; }
html[data-theme="riso"] .paper-card h3 { color: var(--ink); }
html[data-theme="riso"] .paper-card h3 .num { color: var(--accent); text-shadow: 2px 1px 0 var(--accent-2); font-size: 1.25em; }
html[data-theme="riso"] .badge { background: transparent; color: var(--level); border-color: var(--level); }
html[data-theme="riso"] .tag { background: transparent; color: var(--accent-2); padding: 0; border-bottom: 1.5px dotted var(--accent-2); border-radius: 0; }
html[data-theme="riso"] .venue { color: var(--accent); }
html[data-theme="riso"] .action { background: var(--accent-2); border-color: var(--accent-2); color: #fff; }
html[data-theme="riso"] .action:hover { background: var(--accent); border-color: var(--accent); }
html[data-theme="riso"] footer { border-top: 2px dashed var(--accent); }

/* ============================================================= FRESH (bright product UI) */
html[data-theme="fresh"] .masthead { margin: 22px auto 0; width: min(1220px, calc(100vw - 24px)); border-radius: 32px; padding: 54px 0 44px;
  background: radial-gradient(60% 90% at 88% 10%, #ffd6e2 0, transparent 60%), radial-gradient(50% 80% at 70% 100%, #d9f6ec 0, transparent 60%),
              radial-gradient(45% 70% at 100% 60%, #e2deff 0, transparent 60%), #fff; border: 1px solid var(--rule); }
html[data-theme="fresh"] .deco i:nth-child(1) { width: 92px; height: 92px; right: 9%; top: 44px; border-radius: 28px; background: var(--accent); transform: rotate(12deg); }
html[data-theme="fresh"] .deco i:nth-child(2) { width: 58px; height: 58px; right: 19%; top: 128px; border-radius: 50%; background: var(--medium); }
html[data-theme="fresh"] .deco i:nth-child(3) { width: 120px; height: 36px; right: 5%; top: 172px; border-radius: 999px; background: var(--low); transform: rotate(-10deg); }
html[data-theme="fresh"] .kicker { color: var(--accent); }
html[data-theme="fresh"] h1 { font-size: 64px; font-weight: 800; }
html[data-theme="fresh"] .hero-summary a { border-radius: 18px; background: color-mix(in srgb, var(--level, var(--muted)) 16%, white); color: var(--ink); transition: background .15s; }
html[data-theme="fresh"] .hero-summary a:hover { background: color-mix(in srgb, var(--level, var(--muted)) 26%, white); }
html[data-theme="fresh"] .hero-summary strong { color: var(--level); }
html[data-theme="fresh"] .hero-summary a[href="#sec-high"] { --level: var(--high); }
html[data-theme="fresh"] .hero-summary a[href="#sec-medium"] { --level: var(--medium); }
html[data-theme="fresh"] .hero-summary a[href="#sec-low"] { --level: var(--low); }
html[data-theme="fresh"] .hero-summary a[href="#sec-off_topic"] { --level: var(--off_topic); }
html[data-theme="fresh"] .hero-summary a[href="#sec-irrelevant"] { --level: var(--irrelevant); }
html[data-theme="fresh"] .toolbar { margin-top: 12px; }
html[data-theme="fresh"] .search input, html[data-theme="fresh"] .chip, html[data-theme="fresh"] .tool, html[data-theme="fresh"] .side-card,
html[data-theme="fresh"] .interest-panel, html[data-theme="fresh"] .warning-panel, html[data-theme="fresh"] .paper-card.full, html[data-theme="fresh"] .paper-list.rows,
html[data-theme="fresh"] .icon-btn, html[data-theme="fresh"] .theme-switch button, html[data-theme="fresh"] .meter, html[data-theme="fresh"] .image-grid img,
html[data-theme="fresh"] .folded-section > summary .section-heading-title::after, html[data-theme="fresh"] dialog, html[data-theme="fresh"] .to-top { border-width: 1px; border-color: var(--rule); }
html[data-theme="fresh"] .search input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
html[data-theme="fresh"] .chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
html[data-theme="fresh"] .side-nav .dot { border: 0; }
html[data-theme="fresh"] .side-nav a.active { background: var(--accent-soft); color: var(--accent); }
html[data-theme="fresh"] .warning-panel { background: #fff6e6; border-color: #ffe2b0; }
html[data-theme="fresh"] .section-label { color: var(--level); background: color-mix(in srgb, var(--level) 14%, white); padding: 3px 10px; border-radius: 999px; }
html[data-theme="fresh"] .paper-card.full { box-shadow: 0 1px 2px rgba(27, 29, 43, .04), 0 8px 24px rgba(27, 29, 43, .05); }
html[data-theme="fresh"] .paper-card.full:hover { box-shadow: 0 2px 4px rgba(27, 29, 43, .05), 0 16px 40px rgba(27, 29, 43, .09); }
html[data-theme="fresh"] .paper-card.full::before { content: ""; position: absolute; left: 24px; right: 24px; top: 0; height: 4px; border-radius: 0 0 4px 4px; background: var(--level); }
html[data-theme="fresh"] .badge { border: 0; background: color-mix(in srgb, var(--level) 16%, white); color: var(--level); }
html[data-theme="fresh"] .paper-card h3 .num { color: var(--level); }
html[data-theme="fresh"] .tag { background: var(--accent-soft); color: var(--accent); }
html[data-theme="fresh"] .icon-btn.star[aria-pressed="true"] { background: #fff1d1; border-color: #ffd47a; }
html[data-theme="fresh"] .icon-btn.read[aria-pressed="true"] { background: #dcf5ee; border-color: #9fe0cc; }
html[data-theme="fresh"] .action { background: var(--accent); border-color: var(--accent); color: #fff; }
html[data-theme="fresh"] .action:hover { background: #5646f0; color: #fff; }
html[data-theme="fresh"] .card-details > summary { color: var(--accent); }
html[data-theme="fresh"] .row-side .badge { background: color-mix(in srgb, var(--level) 16%, white); }
html[data-theme="fresh"] footer { border-top-width: 1px; border-top-color: var(--rule); }
html[data-theme="fresh"] .theme-switch button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ------------------------------------------------------------- responsive / print */
@media (max-width: 960px) {
  .layout { grid-template-columns: 1fr; gap: 20px; }
  .side { position: static; grid-template-columns: 1fr 1fr; }
  .deco { opacity: .35; }
}
@media (max-width: 640px) {
  body { font-size: 15px; }
  .masthead, html[data-theme="bauhaus"] .masthead, html[data-theme="riso"] .masthead, html[data-theme="fresh"] .masthead { padding: 34px 0 26px; }
  h1, html[data-theme] h1 { font-size: 40px; }
  .hero-summary a, html[data-theme] .hero-summary a { min-width: 0; padding: 8px 12px; }
  .hero-summary strong, html[data-theme] .hero-summary strong { font-size: 26px; }
  .deco { display: none; }
  .toolbar { position: static; }
  .chips, .tools { flex-wrap: nowrap; overflow-x: auto; max-width: 100%; }
  .tools { margin-left: 0; }
  .side { grid-template-columns: 1fr; }
  .venue-chip { display: none; }
  .section-heading p, .section-heading-note { display: none; }
  .section-heading h2, .section-heading-title, html[data-theme] .section-heading h2, html[data-theme] .section-heading-title { font-size: 26px; }
  .paper-card.full { padding: 16px; }
  html[data-theme="bauhaus"] .paper-card.full { padding-left: 64px; }
  html[data-theme="bauhaus"] .paper-card h3 .num { font-size: 38px; }
}
@media print {
  .toolbar, .side, .to-top, .progress, .icon-btn, .text-btn, .theme-switch, .deco { display: none !important; }
  .layout { grid-template-columns: 1fr; }
  html[data-theme] .paper-card.full { box-shadow: none; }
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
