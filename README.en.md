# ScholarInbox

**Turn academic alert emails into a personalized, skimmable literature digest.**

[中文说明](README.md) · [Docs (Chinese)](docs/README.md)

ScholarInbox reads unread Google Scholar alerts and journal table-of-contents emails from Gmail,
extracts the papers, removes duplicates (within a run and across the last 30 days), ranks them
against a plain-language description of your research interests, optionally fetches the original
abstract for the most relevant ones, and writes a single-file HTML digest. The interface and
generated summaries are in Chinese.

Papers are sorted into five levels:

| Level | Meaning | In the digest |
| --- | --- | --- |
| High / Medium | Directly related / usefully related to your work | Full cards |
| Low | Same broad field, weak connection | One-line rows, expandable |
| Off-topic | A real paper outside your broad fields | Folded, titles only |
| Irrelevant | Promotions, events, extraction errors | Folded |

The HTML reader offers search and filters, read/starred marks stored in your browser (shared
across digests), "hide read", starred export to Markdown, an image lightbox, and smooth motion
that respects the system's reduced-motion setting.

## Quick start

Python 3.12+ (3.13 recommended).

```bash
git clone https://github.com/FemiSphere/ScholarInbox.git
cd ScholarInbox
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

scholar-inbox init                       # guided setup: model, API key, config, interests file
scholar-inbox doctor                     # offline self-check (no Gmail or paid API calls)
scholar-inbox --sample --dry-run         # offline demo
scholar-inbox --dry-run --max-emails 5   # small real trial (calls the model API)
scholar-inbox --no-dry-run               # real run
```

You need:

- **Gmail OAuth client** — enable the Gmail API in Google Cloud, create an OAuth client of type
  *Desktop app*, and save the JSON as `credentials.json` in the project root. The first real run
  opens a browser to authorize and writes `token.json`.
- **A model backend** — `llm.preset: deepseek` (recommended; put `DEEPSEEK_API_KEY=...` in `.env`),
  `openai_compatible` (set `base_url`, `model`, `api_key_env`), or `codex_cli` (uses a logged-in
  local `codex` command). Online abstract enrichment is only enabled for the official DeepSeek host.
- **Your research interests** — edit `research_interests.md` (copied from
  [the template](research_interests.example.md)). The *broad fields* section decides which papers
  are folded as off-topic.

## Safety

Dry runs never change Gmail state. Mail is marked as read only on a real run with
`gmail.mark_as_read: true` and no core-step fallback; emails are never deleted. Secrets live in
`.env`, `credentials.json` and `token.json`, all git-ignored.

## Development

```bash
python -B -m pytest -q
```

See [AGENTS.md](AGENTS.md) for maintenance rules and [docs/code-map.md](docs/code-map.md) for where things live.
