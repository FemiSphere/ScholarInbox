"""Inline stylesheet and script for the HTML digest.

Kept separate from ``digest.py`` so the page structure stays readable. Both are
plain strings (not f-strings); ``render_html`` inlines them so a digest remains a
single self-contained file that opens from ``file://`` without a server.
Reader state (read / starred) lives only in the browser's localStorage.
"""

DIGEST_CSS = r"""
:root {
  --bg: #f4f6fa;
  --surface: #ffffff;
  --surface-soft: #f8f9fc;
  --text: #172033;
  --text-soft: #36425a;
  --muted: #66728a;
  --border: #e2e6ee;
  --border-strong: #cfd6e4;
  --accent: #3b5bdb;
  --accent-strong: #2f49b4;
  --accent-soft: #eef1fd;
  --high: #3b5bdb;
  --medium: #0f7f8c;
  --low: #6b778c;
  --off_topic: #a07a45;
  --irrelevant: #8a8f98;
  --star: #e0a100;
  --radius: 14px;
  --shadow-sm: 0 1px 2px rgba(23, 32, 51, .04), 0 2px 8px rgba(23, 32, 51, .04);
  --shadow-md: 0 6px 24px rgba(23, 32, 51, .08);
  --ease: cubic-bezier(.2, .7, .2, 1);
  color-scheme: light;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.65; -webkit-font-smoothing: antialiased; }
a { color: var(--accent-strong); text-underline-offset: 3px; text-decoration-thickness: 1px; }
button { font: inherit; }
[hidden] { display: none !important; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .92em; }

.progress { position: fixed; inset: 0 0 auto 0; height: 3px; z-index: 50; pointer-events: none;
  background: linear-gradient(90deg, var(--accent), #12a4b4); transform-origin: 0 50%; transform: scaleX(0); }

.hero { position: relative; overflow: hidden; color: #eef2ff; padding: 52px 0 44px; background: #0f1a30; }
.hero::before { content: ""; position: absolute; inset: -40%; opacity: .9;
  background: radial-gradient(40% 50% at 80% 10%, rgba(59, 91, 219, .45), transparent 70%),
              radial-gradient(35% 45% at 15% 90%, rgba(18, 164, 180, .28), transparent 70%); }
@media (prefers-reduced-motion: no-preference) { .hero::before { animation: drift 24s ease-in-out infinite alternate; } }
@keyframes drift { to { transform: translate3d(4%, 3%, 0) rotate(4deg); } }
.hero .shell { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 28px; align-items: end; }
.kicker { margin: 0 0 10px; color: #8fdbe6; font-size: 11px; font-weight: 700; letter-spacing: .24em; text-transform: uppercase; }
h1 { margin: 0 0 10px; font-size: 38px; line-height: 1.15; font-weight: 750; letter-spacing: .01em; }
.subtitle { margin: 0; color: #a9b8d4; font-size: 14px; }
.hero-summary { display: grid; grid-template-columns: repeat(5, minmax(72px, 1fr)); gap: 8px; }
.hero-summary a { display: block; padding: 11px 13px; border-radius: 12px; color: inherit; text-decoration: none;
  border: 1px solid rgba(180, 200, 245, .16); background: rgba(255, 255, 255, .05);
  transition: background .2s var(--ease), transform .2s var(--ease), border-color .2s var(--ease); }
.hero-summary a:hover { background: rgba(255, 255, 255, .1); border-color: rgba(180, 200, 245, .32); transform: translateY(-2px); }
.hero-summary strong { display: block; font-size: 27px; line-height: 1.1; font-weight: 600; font-variant-numeric: tabular-nums; }
.hero-summary span { display: block; margin-top: 6px; color: #a9b8d4; font-size: 12px; }

.shell { width: min(1240px, calc(100vw - 32px)); margin: 0 auto; }
.toolbar { position: sticky; top: 0; z-index: 20; padding: 12px 0; border-bottom: 1px solid var(--border);
  background: rgba(244, 246, 250, .86); backdrop-filter: saturate(1.4) blur(12px); -webkit-backdrop-filter: saturate(1.4) blur(12px); }
.toolbar .shell { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.search { flex: 1 1 280px; min-width: 0; position: relative; }
.search input { width: 100%; height: 42px; padding: 0 14px 0 38px; border: 1px solid var(--border); border-radius: 11px;
  background: var(--surface); color: var(--text); font-size: 14px; outline: none; transition: border-color .2s, box-shadow .2s; }
.search::before { content: ""; position: absolute; left: 14px; top: 50%; width: 11px; height: 11px; margin-top: -7px;
  border: 2px solid var(--muted); border-radius: 50%; }
.search::after { content: ""; position: absolute; left: 25px; top: 50%; width: 6px; height: 2px; margin-top: 4px;
  background: var(--muted); transform: rotate(45deg); border-radius: 2px; }
.search input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px rgba(59, 91, 219, .12); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip, .tool { height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface);
  color: var(--text-soft); font-size: 13px; cursor: pointer; white-space: nowrap;
  transition: background .18s var(--ease), color .18s var(--ease), border-color .18s var(--ease), transform .18s var(--ease); }
.chip:hover, .tool:hover { border-color: var(--border-strong); transform: translateY(-1px); }
.chip[aria-pressed="true"] { background: var(--text); border-color: var(--text); color: #fff; }
.tool[aria-pressed="true"] { background: var(--accent-soft); border-color: #c9d3fa; color: var(--accent-strong); }
.tools { display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }

.layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 28px; padding: 26px 0 64px; }
.side { position: sticky; top: 84px; align-self: start; display: grid; gap: 14px; }
.side-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; box-shadow: var(--shadow-sm); }
.side-title { margin: 0 0 8px; color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.side-nav a { display: flex; align-items: center; gap: 9px; padding: 7px 9px; margin: 0 -4px; border-radius: 9px;
  color: var(--text-soft); text-decoration: none; font-size: 14px; transition: background .18s, color .18s; }
.side-nav a:hover { background: var(--surface-soft); }
.side-nav a.active { background: var(--accent-soft); color: var(--accent-strong); font-weight: 650; }
.side-nav .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--level, var(--muted)); flex: 0 0 8px; }
.side-nav .nav-count { margin-left: auto; color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.meter { height: 6px; border-radius: 999px; background: #edf0f6; overflow: hidden; margin: 8px 0 6px; }
.meter i { display: block; height: 100%; width: 0; border-radius: inherit; background: linear-gradient(90deg, var(--accent), #12a4b4);
  transition: width .5s var(--ease); }
.meter-label { color: var(--muted); font-size: 12px; }
.facts { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 0; }
.facts div { padding: 8px 9px; border-radius: 10px; background: var(--surface-soft); }
.facts dt { color: var(--muted); font-size: 11px; }
.facts dd { margin: 0; font-size: 17px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }

.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 20px; margin-bottom: 16px; box-shadow: var(--shadow-sm); }
.panel h2 { margin: 0 0 8px; font-size: 17px; }
.panel p { margin: 0; color: var(--text-soft); font-size: 14px; }
.warning-panel { background: #fffbf2; border-color: #efe2c4; }
.warning-panel ul { margin: 0; padding-left: 18px; font-size: 13px; color: var(--text-soft); }
.topics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.tag { display: inline-flex; padding: 2px 8px; border-radius: 6px; background: var(--accent-soft); color: var(--accent-strong); font-size: 12px; }

.list-intro { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 22px 2px 10px; }
.list-intro h2 { margin: 0; font-size: 22px; }
.result-count { color: var(--muted); font-size: 13px; }
.paper-section { margin: 0 0 26px; scroll-margin-top: 84px; --level: var(--muted); }
.paper-section[data-section-level="high"], .paper-card[data-level="high"] { --level: var(--high); }
.paper-section[data-section-level="medium"], .paper-card[data-level="medium"] { --level: var(--medium); }
.paper-section[data-section-level="low"], .paper-card[data-level="low"] { --level: var(--low); }
.paper-section[data-section-level="off_topic"], .paper-card[data-level="off_topic"] { --level: var(--off_topic); }
.paper-section[data-section-level="irrelevant"], .paper-card[data-level="irrelevant"] { --level: var(--irrelevant); }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin: 0 2px 12px; }
.section-label { display: block; color: var(--level); font-size: 11px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
.section-heading h2, .section-heading-title { display: block; margin: 2px 0 0; font-size: 19px; line-height: 1.3; font-weight: 750; color: var(--text); }
.section-heading p, .section-heading-note { display: block; margin: 2px 0 0; color: var(--muted); font-size: 13px; font-weight: 400; }
.section-tools { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.count-pill { padding: 3px 9px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); color: var(--text-soft); font-size: 12px; font-weight: 650; font-variant-numeric: tabular-nums; }
.text-btn { border: 0; background: none; padding: 4px 6px; color: var(--muted); font-size: 12px; cursor: pointer; border-radius: 6px; }
.text-btn:hover { color: var(--accent-strong); background: var(--accent-soft); }

.folded-section { background: rgba(255, 255, 255, .6); border: 1px solid var(--border); border-radius: var(--radius); padding: 0 16px; }
.folded-section > summary { list-style: none; cursor: pointer; padding: 15px 0; margin: 0; }
.folded-section > summary::-webkit-details-marker { display: none; }
.folded-section > summary .section-heading-title::after { content: "＋"; display: inline-block; margin-left: 8px; color: var(--level);
  transition: transform .25s var(--ease); }
.folded-section[open] > summary .section-heading-title::after { transform: rotate(45deg); }
.folded-section > .details-body > .paper-list { padding-bottom: 16px; }

.paper-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.paper-list > .paper-card, .layout > main { min-width: 0; }
.paper-list.rows { gap: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow-sm); }
.paper-card { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-sm);
  transition: box-shadow .25s var(--ease), border-color .25s var(--ease), transform .25s var(--ease), opacity .3s var(--ease); }
.paper-card::before { content: ""; position: absolute; left: -1px; top: 18px; bottom: 18px; width: 3px; border-radius: 0 3px 3px 0; background: var(--level); }
.paper-card.full { padding: 22px 24px 18px; }
.paper-card.full:hover { box-shadow: var(--shadow-md); border-color: var(--border-strong); transform: translateY(-2px); }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap;
  color: var(--level); background: color-mix(in srgb, var(--level) 10%, white); border: 1px solid color-mix(in srgb, var(--level) 22%, white); }
.badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.card-tools { display: flex; gap: 6px; }
.icon-btn { height: 30px; padding: 0 10px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--muted);
  font-size: 12px; cursor: pointer; transition: all .18s var(--ease); white-space: nowrap; }
.icon-btn:hover { border-color: var(--border-strong); color: var(--text); }
.icon-btn.star[aria-pressed="true"] { color: var(--star); border-color: #f1d98a; background: #fffaeb; }
.icon-btn.read[aria-pressed="true"] { color: var(--medium); border-color: #bfe3e6; background: #effafa; }
@media (prefers-reduced-motion: no-preference) { .icon-btn.pop { animation: pop .35s var(--ease); } }
@keyframes pop { 40% { transform: scale(1.15); } }
.paper-card h3 { margin: 0 0 6px; font-size: 18.5px; line-height: 1.5; font-weight: 680; overflow-wrap: anywhere; }
.paper-card h3 .num { color: var(--muted); font-weight: 500; margin-right: 6px; font-variant-numeric: tabular-nums; }
.meta { margin: 0 0 8px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.venue { display: inline-block; margin: 0 0 8px; padding: 2px 9px; border-radius: 7px; background: var(--surface-soft); border: 1px solid var(--border);
  color: var(--text-soft); font-size: 12px; overflow-wrap: anywhere; }
.summary { margin: 10px 0 4px; color: var(--text-soft); line-height: 1.85; overflow-wrap: anywhere; }
.card-details { margin-top: 8px; }
.card-details > summary { cursor: pointer; color: var(--accent-strong); font-size: 14px; font-weight: 600; list-style: none; display: inline-flex; align-items: center; gap: 6px; }
.card-details > summary::-webkit-details-marker { display: none; }
.card-details > summary::before { content: "›"; display: inline-block; font-size: 18px; line-height: 1; transition: transform .25s var(--ease); }
.card-details[open] > summary::before { transform: rotate(90deg); }
.details-body { overflow: hidden; }
.card-details .details-body > :first-child { margin-top: 8px; }
.details-body p { margin: 6px 0; overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.action { display: inline-flex; align-items: center; height: 34px; padding: 0 13px; border-radius: 10px; font-size: 13px; font-weight: 650; text-decoration: none;
  color: var(--accent-strong); background: var(--accent-soft); border: 1px solid #d5ddfa; transition: background .18s, transform .18s var(--ease); }
.action:hover { background: #e2e8fd; transform: translateY(-1px); }
.action::after { content: "↗"; margin-left: 6px; }

.paper-card.row { border: 0; border-radius: 0; box-shadow: none; border-top: 1px solid var(--border); }
.paper-list.rows > .paper-card.row:first-child { border-top: 0; }
.paper-card.row::before { top: 14px; bottom: 14px; }
.paper-card.row:hover { background: var(--surface-soft); }
.row-details > summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 14px; padding: 11px 16px 11px 18px; }
.row-details > summary::-webkit-details-marker { display: none; }
.row-main { min-width: 0; flex: 1 1 auto; display: block; }
.row-main .title-zh { display: block; font-size: 14.5px; font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-en { display: block; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-details[open] .row-main .title-zh, .row-details[open] .row-en { white-space: normal; }
.row-side { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.venue-chip { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 12px; }
.row-details > .details-body { padding: 0 18px 0 18px; }
.row-details > .details-body > .row-body { padding: 2px 0 14px; border-top: 1px dashed var(--border); }
.paper-card.is-read > * { opacity: .55; transition: opacity .25s var(--ease); }
.paper-card.is-read:hover > * { opacity: .9; }
.paper-card.is-starred::after { content: "★"; position: absolute; top: 10px; right: 12px; color: var(--star); font-size: 13px; pointer-events: none; }
.paper-card.full.is-starred::after { display: none; }

.image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; margin-top: 12px; }
.image-grid img { width: 100%; max-height: 300px; object-fit: contain; border: 1px solid var(--border); border-radius: 10px; background: #fff; cursor: zoom-in;
  transition: transform .25s var(--ease), box-shadow .25s var(--ease); }
.image-grid img:hover { transform: scale(1.02); box-shadow: var(--shadow-md); }
.image-grid:empty { display: none; }

.js .paper-card.reveal { opacity: 0; transform: translateY(14px); }
.js .paper-card.reveal.in { opacity: 1; transform: none; transition: opacity .55s var(--ease), transform .55s var(--ease), box-shadow .25s, border-color .25s; }
@media (prefers-reduced-motion: no-preference) { .paper-card.flash { animation: flash .38s var(--ease); } }
@keyframes flash { from { opacity: 0; transform: translateY(8px); } }

.skipped-list { margin: 0; padding-left: 18px; font-size: 13px; }
.skipped-list span, .skipped-list em { color: var(--muted); margin-left: 8px; }
.empty { padding: 36px; text-align: center; color: var(--muted); }
footer { color: var(--muted); font-size: 12px; padding: 24px 0 0; }

.lightbox { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 24px; cursor: zoom-out;
  background: rgba(10, 16, 30, .78); opacity: 0; transition: opacity .25s var(--ease); }
.lightbox.show { opacity: 1; }
.lightbox img { max-width: min(96vw, 1400px); max-height: 92vh; border-radius: 10px; background: #fff; box-shadow: 0 20px 60px rgba(0, 0, 0, .4);
  transform: scale(.96); transition: transform .3s var(--ease); }
.lightbox.show img { transform: none; }

dialog { width: min(720px, calc(100vw - 32px)); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: var(--shadow-md); color: var(--text); }
dialog::backdrop { background: rgba(10, 16, 30, .45); }
dialog h2 { margin: 0 0 4px; font-size: 18px; }
dialog p { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
dialog textarea { width: 100%; height: 320px; padding: 12px; border: 1px solid var(--border); border-radius: 10px; font: 12.5px/1.6 ui-monospace, Menlo, monospace; resize: vertical; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }

.to-top { position: fixed; right: 22px; bottom: 22px; z-index: 30; width: 42px; height: 42px; border-radius: 50%; border: 1px solid var(--border);
  background: var(--surface); color: var(--text-soft); font-size: 18px; cursor: pointer; box-shadow: var(--shadow-md);
  opacity: 0; transform: translateY(12px); pointer-events: none; transition: opacity .25s var(--ease), transform .25s var(--ease); }
.to-top.show { opacity: 1; transform: none; pointer-events: auto; }

:focus-visible { outline: 3px solid #9db0f5; outline-offset: 2px; }

@media (max-width: 980px) {
  .layout { grid-template-columns: 1fr; gap: 16px; }
  .side { position: static; grid-template-columns: 1fr 1fr; }
  .hero .shell { grid-template-columns: 1fr; align-items: start; }
}
@media (max-width: 640px) {
  .hero { padding: 30px 0 24px; }
  h1 { font-size: 27px; }
  .hero-summary { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; }
  .hero-summary a { padding: 8px; }
  .hero-summary strong { font-size: 20px; }
  .toolbar { position: static; }
  .chips, .tools { flex-wrap: nowrap; overflow-x: auto; max-width: 100%; padding-bottom: 2px; }
  .tools { margin-left: 0; }
  .side { grid-template-columns: 1fr; }
  .paper-card.full { padding: 16px 15px 14px; }
  .card-head { flex-wrap: wrap; }
  .venue-chip { display: none; }
  .section-heading p, .section-heading-note { display: none; }
}
@media print {
  .toolbar, .side, .to-top, .progress, .icon-btn, .text-btn { display: none !important; }
  .layout { grid-template-columns: 1fr; }
  .js .paper-card.reveal { opacity: 1; transform: none; }
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

  // ---- scroll: progress bar, back-to-top, active section, reveal ----
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
    if (motionOK) {
      const reveal = new IntersectionObserver(entries => {
        for (const entry of entries) if (entry.isIntersecting) { entry.target.classList.add('in'); reveal.unobserve(entry.target); }
      }, { rootMargin: '0px 0px -5% 0px' });
      for (const card of cards) { card.classList.add('reveal'); reveal.observe(card); }
    }
  }

  // ---- count-up in the hero ----
  for (const element of $$('[data-count]')) {
    const target = Number(element.dataset.count) || 0;
    if (!motionOK || target === 0) continue;
    const started = performance.now();
    const step = now => {
      const progressRatio = Math.min(1, (now - started) / 900);
      element.textContent = String(Math.round(target * (1 - Math.pow(1 - progressRatio, 3))));
      if (progressRatio < 1) requestAnimationFrame(step);
    };
    element.textContent = '0';
    requestAnimationFrame(step);
  }

  applyFilters(true);
})();
"""
