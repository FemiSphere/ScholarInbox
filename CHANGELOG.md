# Changelog

## 0.3.0 — 2026-11-25

A large usability release: better papers, a better page, a calmer terminal and an easier setup.

### Reading
- **Seven reading styles** for the HTML digest — bright (Fresh, Pop, Bauhaus, Riso) and academic
  (Editorial, Swiss, Calm). Choose with `digest.theme` or switch from the page footer.
- **Off-topic level**: real papers outside your broad fields are folded away as 领域外; 不相关 is
  kept for non-academic items.
- Read / star marks (kept 60 days in your browser), hide-read, starred export to Markdown,
  image zoom, side navigation and reading progress. Scroll flicker removed.
- Chinese titles for every shown paper; low / off-topic rows get title-only translation.

### Better results
- **Abstracts from free scholarly metadata** (Crossref, OpenAlex) before paid web search; a check on
  48 high/medium papers found abstracts for 38 (previously roughly 25–50%).
- Google Scholar alerts are no longer mistaken for marketing; keywords match whole words.
- Translation only for papers that are shown; successful ratings and translations are reused if a
  run must be repeated; a translation-only hiccup no longer keeps mail unread.
- A looping translation of a single paper is retried with a short, different request.

### Setup and everyday use
- `scholar-inbox init` (guided setup) and `scholar-inbox doctor` (offline self-check).
- Built-in model presets: `llm.preset: deepseek | openai_compatible | codex_cli`.
- Reorganised, bilingual `config.example.yaml`; every key shows its real default.
- Terminal: static header, one line per finished step, single-line progress, end-of-run summary
  with remaining unread mail. Run logs older than 30 days are cleaned up.
- English README with screenshots and a live demo; Chinese README in `README.zh-CN.md`.
- Released under the MIT License.

### Upgrading from 0.2
- Existing `llm.config_path` setups keep working; `config/llm/*.example.yaml` paths map to presets.
- `research_interests.md` is no longer tracked in git (your local file is untouched);
  `research_interests.example.md` is the template. Adding a "大方向 / broad fields" section is recommended.
- Keys that were never read were removed from the template: `safety.never_delete_emails`,
  `safety.redact_secrets_in_logs`, `telemetry.show_compact_summary`, `digest.language`.
