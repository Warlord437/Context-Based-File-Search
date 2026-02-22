# Local-Agent Web UI

Browser-based interface for the hybrid document search engine.

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI (Python) |
| **Frontend** | Vanilla HTML, CSS, JavaScript |
| **Server** | Uvicorn (ASGI) |

**Note:** This is a web app, not a desktop app. We do **not** use Tauri, Electron, or any desktop wrapper. The UI runs in your browser and talks to a local Python server.

## Quick Start

```bash
# From project root
pip install -r requirements.txt

# Start Qdrant (required for search)
docker-compose up -d

# Start the web server
uvicorn web.server:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

## Folder Structure

```
web/
├── README.md           # This file
├── server.py           # FastAPI backend + API routes
└── static/
    ├── index.html      # Main search page
    ├── css/
    │   └── style.css   # Styles (dark theme)
    └── js/
        └── app.js      # Search & index logic
```

## Features

- **Search** – Hybrid semantic + keyword search across indexed documents
- **Filters** – Filter by file type (pdf, docx) or path
- **Status** – View indexed file and vector counts in the header
- **Index** – Index a folder or browser bookmarks/history from the UI

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | System status (files, vectors, Qdrant connection) |
| POST | `/api/search` | Perform search with optional filters |
| POST | `/api/index` | Index a directory (path, max_items) |
| POST | `/api/index-browser` | Index browser bookmarks & history |

## Development

No build step. Edit files in `web/static/` and refresh the browser. The server reloads on code changes when run with `--reload`.

## Future: Desktop App with Tauri?

To package this as a native desktop app, you could:
1. Use **Tauri** – Rust backend, small binary, uses system webview
2. Use **Electron** – Node.js backend, larger binary, bundles Chromium

The current web UI is designed to work with any of these approaches.
