"""
Browser indexer: parse bookmarks and history from Chrome, Firefox, Safari.
Indexes URLs + titles for semantic search over saved/visited links.
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

from .config import get_config
from .ids import chunk_id
from .model_loader import get_embedding_model
from .storage import create_storage
from .types import Chunk, IndexStats

logger = logging.getLogger(__name__)

# URL schemes to skip (internal, file, etc.)
SKIP_SCHEMES = {"chrome", "about", "file", "javascript", "data", "blob", ""}

# Max history entries per source (avoid huge indexes)
DEFAULT_MAX_HISTORY = 5000
DEFAULT_MAX_BOOKMARKS = 10000


def _browser_file_id(url: str, source: str) -> str:
    """Stable file_id for browser entries."""
    content = f"browser|{source}|{url}"
    return hashlib.sha1(content.encode()).hexdigest()


def _browser_path(url: str, source: str) -> str:
    """Canonical path for browser entries (used in catalog and search)."""
    return f"browser:{source}:{url}"


def _is_valid_url(url: str) -> bool:
    """Check if URL is indexable."""
    if not url or not isinstance(url, str) or len(url) > 2048:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() in SKIP_SCHEMES:
            return False
        if not parsed.netloc and parsed.scheme not in ("http", "https"):
            return False
        return True
    except Exception:
        return False


def _webkit_time_to_unix(webkit_us: int) -> int:
    """Convert WebKit timestamp (microseconds since 1601-01-01) to Unix."""
    if webkit_us <= 0:
        return 0
    # WebKit epoch is 1601-01-01; Unix is 1970-01-01
    # Delta in microseconds: 11644473600 seconds
    return int(webkit_us / 1_000_000 - 11644473600)


def _read_sqlite_safe(db_path: Path, max_rows: int = 50000) -> Optional[sqlite3.Connection]:
    """
    Read SQLite DB robustly. Copies to temp if locked (browser may have it open).
    Caller must close the connection; temp file is deleted on close.
    """
    if not db_path.exists():
        return None
    try:
        # Try direct read first (read-only)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
                tmp.close()
                shutil.copy2(db_path, tmp.name)
                conn = sqlite3.connect(tmp.name)
                conn.row_factory = sqlite3.Row
                return conn
            except Exception as copy_err:
                logger.warning(f"Could not copy locked DB {db_path}: {copy_err}")
                return None
        raise


def _parse_chrome_bookmarks(profile_path: Path, max_items: int) -> Iterator[Dict[str, Any]]:
    """Parse Chrome/Chromium Bookmarks JSON."""
    bookmarks_path = profile_path / "Bookmarks"
    if not bookmarks_path.exists():
        return

    try:
        with open(bookmarks_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to parse Chrome bookmarks at {bookmarks_path}: {e}")
        return

    count = 0

    def _recurse(node: dict, folder: str = ""):
        nonlocal count
        if count >= max_items:
            return
        if node.get("type") == "url":
            url = node.get("url", "")
            title = node.get("name", "") or url
            if _is_valid_url(url):
                count += 1
                yield {
                    "url": url,
                    "title": title,
                    "source": "bookmark",
                    "visit_count": 0,
                    "last_visit": 0,
                    "folder": folder,
                }
        elif node.get("type") == "folder":
            children = node.get("children", [])
            folder_name = node.get("name", "")
            next_folder = f"{folder}/{folder_name}" if folder_name else folder
            for child in children:
                yield from _recurse(child, next_folder)

    roots = data.get("roots", {})
    for root_name, root_node in roots.items():
        if isinstance(root_node, dict):
            yield from _recurse(root_node, root_name)


def _parse_chrome_history(profile_path: Path, max_items: int) -> Iterator[Dict[str, Any]]:
    """Parse Chrome/Chromium History SQLite. Uses temp copy if locked."""
    history_path = profile_path / "History"
    if not history_path.exists():
        return

    conn = _read_sqlite_safe(history_path, max_rows=max_items * 2)
    if not conn:
        return

    tmp_path = None

    def _do_query(c):
        return c.execute(
            """
            SELECT url, title, visit_count,
                   (SELECT max(visit_time) FROM visits WHERE visits.url = urls.id) as last_visit
            FROM urls
            WHERE url IS NOT NULL AND url != ''
            ORDER BY visit_count DESC, last_visit DESC
            LIMIT ?
            """,
            (max_items,),
        )

    try:
        cursor = _do_query(conn)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            conn.close()
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".db")
                os.close(fd)
                shutil.copy2(history_path, tmp_path)
                conn = sqlite3.connect(tmp_path)
                conn.row_factory = sqlite3.Row
                cursor = _do_query(conn)
            except Exception as copy_err:
                logger.warning(f"Chrome History locked, copy failed: {copy_err}")
                if tmp_path and Path(tmp_path).exists():
                    Path(tmp_path).unlink(missing_ok=True)
                return
        else:
            logger.warning(f"Chrome history query failed: {e}")
            return

    try:
        for row in cursor:
            url = row["url"]
            title = row["title"] or url
            if _is_valid_url(url):
                yield {
                    "url": url,
                    "title": title,
                    "source": "history",
                    "visit_count": row["visit_count"] or 0,
                    "last_visit": _webkit_time_to_unix(row["last_visit"] or 0),
                    "folder": "",
                }
    finally:
        conn.close()
        if tmp_path and Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _parse_firefox_places(profile_path: Path, max_items: int) -> Iterator[Dict[str, Any]]:
    """Parse Firefox places.sqlite (bookmarks + history)."""
    places_path = profile_path / "places.sqlite"
    if not places_path.exists():
        return

    conn = _read_sqlite_safe(places_path, max_rows=max_items * 2)
    if not conn:
        return

    bookmark_urls = set()
    try:
        # Bookmarks: moz_bookmarks + moz_places
        cursor = conn.execute(
            """
            SELECT p.url, p.title, COALESCE(p.visit_count, 0) as visit_count,
                   p.last_visit_date
            FROM moz_places p
            JOIN moz_bookmarks b ON b.fk = p.id
            WHERE p.url IS NOT NULL AND p.url != ''
            ORDER BY b.dateAdded DESC
            LIMIT ?
            """,
            (max_items,),
        )
        for row in cursor:
            url = row["url"]
            title = row["title"] or url
            if _is_valid_url(url):
                bookmark_urls.add(url)
                lv = row["last_visit_date"]
                last_visit = int(lv / 1_000_000) if lv else 0
                yield {
                    "url": url,
                    "title": title,
                    "source": "bookmark",
                    "visit_count": row["visit_count"] or 0,
                    "last_visit": last_visit,
                    "folder": "",
                }
    except sqlite3.OperationalError:
        pass

    try:
        # History: moz_places, exclude bookmarks
        cursor = conn.execute(
            """
            SELECT url, title, COALESCE(visit_count, 0) as visit_count, last_visit_date
            FROM moz_places
            WHERE url IS NOT NULL AND url != ''
            ORDER BY visit_count DESC, last_visit_date DESC
            LIMIT ?
            """,
            (max_items,),
        )
        for row in cursor:
            url = row["url"]
            if url in bookmark_urls or not _is_valid_url(url):
                continue
            title = row["title"] or url
            lv = row["last_visit_date"]
            last_visit = int(lv / 1_000_000) if lv else 0
            yield {
                "url": url,
                "title": title,
                "source": "history",
                "visit_count": row["visit_count"] or 0,
                "last_visit": last_visit,
                "folder": "",
            }
    except sqlite3.OperationalError as e:
        logger.warning(f"Firefox history query failed: {e}")
    finally:
        conn.close()
        if getattr(conn, "_temp_path", None):
            try:
                Path(conn._temp_path).unlink(missing_ok=True)
            except Exception:
                pass


def _collect_browser_entries(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect all browser entries from configured browsers."""
    browser_config = config.get("browser", {})
    max_bookmarks = browser_config.get("max_bookmarks", DEFAULT_MAX_BOOKMARKS)
    max_history = browser_config.get("max_history", DEFAULT_MAX_HISTORY)
    enabled = browser_config.get("enabled_browsers", ["chrome", "firefox"])

    entries: List[Dict[str, Any]] = []
    seen_keys: set = set()

    home = Path.home()

    # Chrome / Chromium / Brave / Edge
    if "chrome" in enabled:
        chrome_base = home / "Library" / "Application Support"
        for name in ["Google/Chrome", "Chromium", "Brave Software/Brave-Browser", "Microsoft Edge"]:
            base = chrome_base / name
            if not base.exists():
                continue
            for profile in ["Default", "Profile 1", "Profile 2"]:
                profile_path = base / profile
                if not profile_path.exists():
                    continue
                for e in _parse_chrome_bookmarks(profile_path, max_bookmarks):
                    key = (e["url"], e["source"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        entries.append(e)
                for e in _parse_chrome_history(profile_path, max_history):
                    key = (e["url"], e["source"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        entries.append(e)

    # Firefox
    if "firefox" in enabled:
        ff_base = home / "Library" / "Application Support" / "Firefox" / "Profiles"
        if ff_base.exists():
            for profile_dir in ff_base.iterdir():
                if profile_dir.is_dir():
                    for e in _parse_firefox_places(profile_dir, max_bookmarks + max_history):
                        key = (e["url"], e["source"])
                        if key not in seen_keys:
                            seen_keys.add(key)
                            entries.append(e)

    return entries


def _entry_to_chunk(entry: Dict[str, Any]) -> Chunk:
    """Convert browser entry to Chunk for indexing."""
    url = entry["url"]
    title = entry["title"]
    source = entry["source"]
    visit_count = entry.get("visit_count", 0)
    last_visit = entry.get("last_visit", 0)

    # Searchable text: title + URL (helps semantic + lexical)
    text = f"{title}\n{url}".strip()
    if not text:
        text = url

    fid = _browser_file_id(url, source)
    cid = chunk_id(fid, 0)
    path = _browser_path(url, source)

    return Chunk(
        path=path,
        file_id=fid,
        chunk_id=cid,
        text=text,
        token_start=0,
        token_end=len(text.split()),
        mtime=last_visit,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        idx=0,
    )


def run_browser_index(config: Dict[str, Any] = None) -> IndexStats:
    """
    Index browser bookmarks and history. Robust to locked DBs and missing files.
    """
    config = config or get_config()
    stats = IndexStats()

    entries = _collect_browser_entries(config)
    if not entries:
        logger.info("No browser entries found to index")
        return stats

    logger.info(f"Collected {len(entries)} browser entries")

    # Delete existing browser entries (full re-index)
    qdrant, catalog = create_storage(config)
    qdrant.ensure_collection()

    try:
        # Clear catalog (files + chunks; FTS cleaned via trigger)
        with catalog.transaction():
            cursor = catalog.conn.execute(
                "SELECT file_id FROM files WHERE path LIKE 'browser:%'"
            )
            browser_file_ids = [row[0] for row in cursor]
            for fid in browser_file_ids:
                catalog.conn.execute("DELETE FROM chunks WHERE file_id = ?", (fid,))
            catalog.conn.execute("DELETE FROM files WHERE path LIKE 'browser:%'")
        logger.info(f"Cleared {len(browser_file_ids)} existing browser entries from catalog")
    except Exception as e:
        logger.warning(f"Could not clear browser entries from catalog: {e}")

    # Clear Qdrant vectors for browser entries
    try:
        deleted = qdrant.delete_points_by_path_prefix("browser:")
        if deleted > 0:
            logger.info(f"Cleared {deleted} browser vectors from Qdrant")
    except Exception as e:
        logger.warning(f"Could not clear browser vectors from Qdrant: {e}")

    # Load model
    model = get_embedding_model()
    if not model:
        logger.error("Failed to load embedding model")
        stats.errors = len(entries)
        return stats

    embed_batch = config["index"].get("embed_batch", 1024)
    upsert_batch = config["index"].get("upsert_batch", 4000)

    start_time = time.time()
    chunks_created = 0

    for i in range(0, len(entries), embed_batch):
        batch_entries = entries[i : i + embed_batch]
        chunks = [_entry_to_chunk(e) for e in batch_entries]

        try:
            texts = [c.text for c in chunks]
            embeddings = model.encode(texts, convert_to_tensor=False).tolist()

            points = []
            for chunk, emb in zip(chunks, embeddings):
                text_snippet = (chunk.text[:500] + "...") if len(chunk.text) > 500 else chunk.text
                entry = next(e for e in batch_entries if _browser_path(e["url"], e["source"]) == chunk.path)
                points.append({
                    "id": chunk.chunk_id,
                    "vector": emb,
                    "payload": {
                        "path": chunk.path,
                        "file_id": chunk.file_id,
                        "chunk_id": chunk.chunk_id,
                        "idx": 0,
                        "text": text_snippet,
                        "url": entry["url"],
                        "title": entry["title"],
                        "source": entry["source"],
                        "visit_count": entry.get("visit_count", 0),
                    },
                })

            # Upsert to Qdrant
            for j in range(0, len(points), upsert_batch):
                batch = points[j : j + upsert_batch]
                qdrant.upsert_vectors(batch)

            # Catalog + FTS
            with catalog.transaction():
                for chunk, entry in zip(chunks, batch_entries):
                    catalog.upsert_file(
                        chunk.path,
                        size=0,
                        mtime=entry.get("last_visit", 0),
                        sha256=chunk.sha256,
                        in_transaction=True,
                        file_id=chunk.file_id,
                    )
                    catalog.insert_chunks(chunk.file_id, [chunk], in_transaction=True)
                    catalog.fts_insert(chunk.chunk_id, chunk.text, chunk.path, in_transaction=True)

            chunks_created += len(chunks)
            stats.chunks_created = chunks_created
            stats.files_processed = chunks_created  # 1 chunk per entry

        except Exception as e:
            logger.error(f"Browser index batch failed: {e}")
            stats.errors += len(batch_entries)

    stats.duration_seconds = time.time() - start_time

    # Record metrics for GraphQL/dashboard
    try:
        catalog.insert_index_stats(
            operation="browser_index",
            files_processed=stats.files_processed,
            chunks_created=stats.chunks_created,
            files_skipped=0,
            errors=stats.errors,
            duration_seconds=stats.duration_seconds,
        )
    except Exception:
        pass

    logger.info(f"Browser indexing complete: {chunks_created} entries, {stats.duration_seconds:.2f}s")
    return stats
