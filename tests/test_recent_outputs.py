import os

from literature_digest.recent_outputs import (
    load_recent_output_entries,
    parse_digest_markdown,
    select_recent_digest_files,
)


def test_parse_digest_markdown_extracts_paper_identities(tmp_path):
    digest = tmp_path / "2026-05-05-digest.md"
    digest.write_text(
        """# Digest

## High
### 1. Chinese title
- Original title: Thermal transport in pentagonal COF nanotubes | [Link](https://example.org/a?utm_source=x) | DOI: `10.1234/ABC`
- Source: alert

### 2. Another title
- Machine learning interatomic potentials for atomistic simulations | [Link](https://example.org/b)
""",
        encoding="utf-8",
    )

    entries = parse_digest_markdown(digest)

    assert len(entries) == 2
    assert entries[0].title == "Thermal transport in pentagonal COF nanotubes"
    assert entries[0].url == "https://example.org/a?utm_source=x"
    assert entries[0].doi == "10.1234/abc"
    assert entries[1].title == "Machine learning interatomic potentials for atomistic simulations"
    assert entries[1].url == "https://example.org/b"


def test_select_recent_digest_files_uses_day_and_file_lookback_union(tmp_path):
    files = [
        tmp_path / "2026-05-06-digest.md",
        tmp_path / "2026-05-03-digest.md",
        tmp_path / "2026-04-20-digest.md",
        tmp_path / "notes.md",
    ]
    for index, path in enumerate(files):
        path.write_text("x", encoding="utf-8")
        timestamp = 1_800_000_000 + index
        os.utime(path, (timestamp, timestamp))

    selected = select_recent_digest_files(
        tmp_path,
        date_label="2026-05-07",
        lookback_days=5,
        lookback_files=1,
    )

    assert {path.name for path in selected} == {
        "2026-05-06-digest.md",
        "2026-05-03-digest.md",
        "2026-04-20-digest.md",
    }


def test_load_recent_output_entries_returns_selected_files_and_entries(tmp_path):
    recent = tmp_path / "2026-05-06-digest.md"
    recent.write_text(
        """# Digest

### 1. Title
- Historical paper | [Link](https://example.org/history)
""",
        encoding="utf-8",
    )

    entries, files = load_recent_output_entries(
        tmp_path,
        date_label="2026-05-07",
        lookback_days=5,
        lookback_files=5,
    )

    assert files == [recent]
    assert [entry.title for entry in entries] == ["Historical paper"]
