# Browser Indexing

**Date**: January 2026  
**Status**: ✅ Implemented

---

## Overview

Local-Agent can index your browser **bookmarks** and **history** so you can search across saved and visited links. When you search, results include both file chunks and relevant URLs.

---

## Quick Start

```bash
# Index browser bookmarks and history
python3 local-agent/cli.py index-browser

# Search (results include files + browser links)
python3 local-agent/cli.py find "machine learning tutorial"
```

---

## Supported Browsers

| Browser | Bookmarks | History |
|---------|-----------|---------|
| **Chrome** | ✅ | ✅ |
| **Chromium** | ✅ | ✅ |
| **Brave** | ✅ | ✅ |
| **Edge** | ✅ | ✅ |
| **Firefox** | ✅ | ✅ |

**Platform**: macOS (paths under `~/Library/Application Support/`).

---

## What Gets Indexed

- **Bookmarks**: URL + title from bookmark bars and folders
- **History**: URL + title, ordered by visit count and recency

Each entry is indexed as one chunk. Searchable text = title + URL. No page content is fetched (offline, fast).

---

## Configuration

In `config.yaml`:

```yaml
browser:
  enabled: true
  enabled_browsers: ["chrome", "firefox"]
  max_bookmarks: 10000
  max_history: 5000
```

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Master switch for browser indexing |
| `enabled_browsers` | `["chrome", "firefox"]` | Browsers to parse |
| `max_bookmarks` | `10000` | Max bookmark entries per browser |
| `max_history` | `5000` | Max history entries per browser |

---

## Robustness

- **Locked databases**: If the browser has the DB open, a temp copy is used
- **Missing files**: Skips gracefully if a browser profile is not found
- **Invalid URLs**: Skips `chrome://`, `about:`, `file://`, etc.
- **Re-indexing**: Full replace; previous browser entries are cleared first

---

## Search Results

Browser links appear with:

- **Path**: `browser:bookmark:https://...` or `browser:history:https://...`
- **Display**: CLI shows `🔗 https://... (bookmark)` for readability
- **Type**: `link`

---

## Privacy

- All data stays local
- No network requests for page content
- Browser data is read from standard profile paths

---

## Files

| File | Purpose |
|------|---------|
| `search/browser_indexer.py` | Parsing, embedding, upsert |
| `search/storage.py` | `delete_points_by_path_prefix`, `upsert_file(file_id=)` |
| `local-agent/cli.py` | `index-browser` command |
