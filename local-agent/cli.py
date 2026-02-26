#!/usr/bin/env python3
"""CLI entrypoint for local-agent.

Commands:
- bfs-index <path>: Index files using BFS streaming indexer
- find "<query>": Search for content using hybrid retrieval
- ask "<query>": Ask questions (if LLM integration is enabled)
- status: Check system status
- reset-db: Clear all indexed data
- daemon: Auto-indexing daemon (--startup-index, --idle-updates)
"""
import os
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import multiprocessing as mp
try:
    mp.set_start_method("spawn", force=True)
except RuntimeError:
    pass

import argparse
import signal
import sys
import logging
import time
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path for search module
parent_dir = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(parent_dir))

try:
    import yaml
except Exception:
    yaml = None


def load_config():
    cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    if yaml is None:
        return {}
    try:
        with open(cfg_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _bfs_index(args):
    """Index files using BFS streaming indexer."""
    try:
        from search.indexer import run_complete_index
        
        # Convert paths to Path objects
        paths = [Path(p).expanduser().resolve() for p in args.paths]
        
        # Parse allowed extensions
        allow_exts = [".txt", ".md", ".markdown", ".pdf", ".docx", ".html", ".htm", ".rtf"]
        if hasattr(args, 'allow') and args.allow:
            allow_exts = [ext.strip() for ext in args.allow.split(',')]
        
        # Run complete indexing
        stats = run_complete_index(
            roots=[str(p) for p in paths],
            allow_exts=allow_exts,
            max_tokens=args.max_tokens,
            overlap=args.overlap,
            embed_batch=1024,
            upsert_batch=4000,
            ocr_enabled=args.ocr,
            max_items_per_slice=args.max_items,
            max_pdf_pages=args.max_pdf_pages
        )
        
        print(f"\n✅ BFS Indexing Complete!")
        print(f"📁 Files processed: {stats.files_processed}")
        print(f"📄 Chunks created: {stats.chunks_created}")
        print(f"⏱️  Duration: {stats.duration_seconds:.2f}s")
        print(f"🚀 Rate: {stats.files_processed/stats.duration_seconds:.1f} files/sec")
        
    except Exception as e:
        logger.error(f"BFS indexing failed: {e}")
        print(f"❌ Error: {e}")


def _find(args):
    """Search for content using hybrid retrieval."""
    try:
        from search.api import run

        # Build filters from CLI args
        filters = {}
        if getattr(args, 'file_type', None):
            filters['file_ext'] = [f'.{ext.strip()}' if not ext.strip().startswith('.') else ext.strip()
                                   for ext in args.file_type.split(',')]
        if getattr(args, 'path_contains', None):
            filters['path_contains'] = args.path_contains

        # Run search
        result = run(
            query=args.query,
            k=args.max_results,
            page=args.page,
            per_page=args.per_page,
            opts={
                'show_context': args.show_context,
                'case_sensitive': args.case_sensitive,
                'exact_match': args.exact,
                'filters': filters,
                'expand_query': not getattr(args, 'no_expand', False),
            }
        )
        
        print(f"\n🔍 Search Results for: '{args.query}'")
        print(f"📊 Found {result['total_hits']} results (page {result['page']}/{result['total_hits']//result['per_page'] + 1})")
        print("=" * 80)
        
        if not result['items']:
            print("❌ No results found. Try running 'bfs-index' to index your documents.")
            return
        
        for i, hit in enumerate(result['items'], 1):
            # Format browser links nicely (browser:bookmark:url or browser:history:url)
            display_path = hit.path
            if hit.path.startswith("browser:"):
                parts = hit.path.split(":", 2)
                if len(parts) >= 3:
                    display_path = f"🔗 {parts[2]} ({parts[1]})"
            print(f"\n{i}. 📄 {display_path}")
            print(f"   🎯 Score: {hit.score:.3f}")
            print(f"   📊 Breakdown: cos={hit.score_breakdown.cosine:.2f}, bm25={hit.score_breakdown.bm25:.2f}, exact={hit.score_breakdown.exact:.2f}")
            if args.show_context and hit.snippet:
                print(f"   📝 Context: ...{hit.snippet}...")
            print(f"   🏷️  Type: {hit.file_type}")
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        print(f"❌ Error: {e}")


def _ask(args):
    """Ask questions (placeholder for LLM integration)."""
    print("❌ LLM integration not yet implemented in new architecture.")
    print("💡 Use 'find' command for document search.")


def _status(args):
    """Check system status."""
    try:
        from search.storage import create_storage
        from search.config import get_config
        
        config = get_config()
        
        print("🔍 Local-Agent System Status")
        print("=" * 40)
        
        # Check Qdrant connection
        try:
            qdrant, catalog = create_storage(config)
            print("✅ Qdrant: Connected")
            
            # Get collection info
            try:
                collection_info = qdrant.client.get_collection(qdrant.collection_name)
                point_count = collection_info.points_count
                print(f"📊 Vectors: {point_count:,} points")
            except Exception as e:
                print(f"❌ Qdrant: Collection error - {e}")
                point_count = 0
                
        except Exception as e:
            print(f"❌ Qdrant: Connection failed - {e}")
            point_count = 0
        
        # Check SQLite catalog
        try:
            if 'catalog' in locals():
                chunk_count = catalog.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                file_count = catalog.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                print(f"📚 Files: {file_count:,} indexed")
                print(f"📄 Chunks: {chunk_count:,} chunks")
            else:
                print("❌ Catalog: Not accessible")
        except Exception as e:
            print(f"❌ Catalog: Error - {e}")
        
        # Check configuration
        config = load_config()
        if config:
            print("⚙️  Config: Loaded from config.yaml")
        else:
            print("⚙️  Config: Using defaults")
        
        # Recommendations
        if point_count == 0:
            print("\n💡 Recommendation: Run 'bfs-index ~/Documents' to start indexing")
        else:
            print(f"\n✅ System ready! Try: find 'your search query'")
            
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        print(f"❌ Error: {e}")


def _index_browser(args):
    """Index browser bookmarks and history."""
    try:
        from search.browser_indexer import run_browser_index
        from search.config import get_config

        config = get_config()
        if not config.get("browser", {}).get("enabled", True):
            print("Browser indexing is disabled in config.")
            return

        print("Indexing browser bookmarks and history...")
        stats = run_browser_index(config)
        print(f"\nBrowser indexing complete!")
        print(f"Links indexed: {stats.chunks_created}")
        print(f"Duration: {stats.duration_seconds:.2f}s")
        if stats.errors:
            print(f"Errors: {stats.errors}")
    except Exception as e:
        logger.error(f"Browser indexing failed: {e}")
        print(f"Error: {e}")


def _get_daemon_roots(config):
    """Get index roots from config for daemon mode."""
    paths = config.get("index", {}).get("paths", ["~/Documents"])
    roots = []
    for p in paths:
        try:
            resolved = Path(p).expanduser().resolve()
            if resolved.exists():
                roots.append(str(resolved))
            else:
                logger.warning("Daemon: path does not exist, skipping: %s", p)
        except Exception as e:
            logger.warning("Daemon: invalid path %s: %s", p, e)
    return roots if roots else [str(Path("~/Documents").expanduser().resolve())]


def _daemon(args):
    """Run daemon mode: optional startup index + periodic idle updates."""
    from search.config import get_config
    from search.indexer import run_complete_index, run_bfs_slice

    config = get_config()
    roots = _get_daemon_roots(config)
    daemon_config = config.get("daemon", {})
    interval_min = daemon_config.get("idle_interval_minutes", 30)
    max_items = daemon_config.get("max_items_per_slice", 1000)

    # Override from CLI
    if getattr(args, "interval", None):
        interval_min = args.interval
    if getattr(args, "max_items", None):
        max_items = args.max_items

    shutdown_requested = [False]  # use list for closure in signal handler

    def _on_signal(signum, frame):
        shutdown_requested[0] = True
        logger.info("Daemon: shutdown requested (signal %s)", signum)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    print("Daemon: starting with roots:", roots)
    if args.startup_index:
        print("Daemon: running startup index...")
        try:
            stats = run_complete_index(
                roots=roots,
                max_items_per_slice=max_items,
                ocr_enabled=config.get("index", {}).get("ocr_enabled", False),
            )
            print(f"Daemon: startup index done — {stats.files_processed} files, {stats.chunks_created} chunks")
        except Exception as e:
            logger.error("Daemon: startup index failed: %s", e)
            print(f"Daemon: startup index error: {e}")
        if shutdown_requested[0]:
            print("Daemon: exiting after startup")
            return

    if not args.idle_updates:
        print("Daemon: --idle-updates not set, exiting (use --idle-updates for periodic updates)")
        return

    print(f"Daemon: idle updates every {interval_min} min (Ctrl+C to stop)")
    last_run = time.time()

    while not shutdown_requested[0]:
        elapsed = time.time() - last_run
        if elapsed >= interval_min * 60:
            try:
                # Full index each cycle to pick up new/changed files
                stats = run_complete_index(
                    roots=roots,
                    max_items_per_slice=max_items,
                    ocr_enabled=config.get("index", {}).get("ocr_enabled", False),
                )
                last_run = time.time()
                logger.info("Daemon: idle cycle — %d files, %d chunks", stats.files_processed, stats.chunks_created)
            except Exception as e:
                logger.error("Daemon: idle cycle failed: %s", e)
            continue

        # Sleep in small chunks to allow responsive shutdown
        for _ in range(30):
            if shutdown_requested[0]:
                break
            time.sleep(1)

    print("Daemon: stopped")


def _reset_db(args):
    """Clear all indexed data."""
    try:
        from search.storage import create_storage
        from search.config import get_config
        
        config = get_config()
        
        print("🗑️  Resetting database...")
        
        # Clear Qdrant
        try:
            qdrant, catalog = create_storage(config)
            qdrant.client.delete_collection(qdrant.collection_name)
            print("✅ Qdrant collection deleted")
        except Exception as e:
            print(f"⚠️  Qdrant reset warning: {e}")
        
        # Clear SQLite catalog
        try:
            if 'catalog' in locals():
                catalog.conn.execute("DELETE FROM chunks")
                catalog.conn.execute("DELETE FROM files")
                catalog.conn.execute("DELETE FROM index_stats")
                catalog.conn.execute("DELETE FROM search_stats")
                catalog.conn.commit()
                print("✅ SQLite catalog cleared")
        except Exception as e:
            print(f"⚠️  SQLite reset warning: {e}")
        
        # Clear frontier
        try:
            frontier_path = Path("store/frontier.json")
            if frontier_path.exists():
                frontier_path.unlink()
                print("✅ BFS frontier cleared")
        except Exception as e:
            print(f"⚠️  Frontier reset warning: {e}")
        
        print("🎉 Database reset complete!")
        print("💡 Run 'bfs-index ~/Documents' to start fresh indexing")
        
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        print(f"❌ Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Local-Agent: Hybrid Document Search Engine")
    subparsers = parser.add_subparsers(dest="cmd", help="Available commands")
    
    # BFS Index command
    p_bfs = subparsers.add_parser("bfs-index", help="Index all files using BFS streaming indexer")
    p_bfs.add_argument("paths", nargs="+", help="Paths to index")
    p_bfs.add_argument("--max-items", type=int, default=1000, help="Maximum items per BFS level")
    p_bfs.add_argument("--max-tokens", type=int, default=1200, help="Maximum tokens per chunk")
    p_bfs.add_argument("--overlap", type=int, default=80, help="Token overlap between chunks")
    p_bfs.add_argument("--ocr", action="store_true", help="Enable OCR for images")
    p_bfs.add_argument("--max-pdf-pages", type=int, default=50, help="Maximum PDF pages to process")
    p_bfs.add_argument("--allow", type=str, help="Comma-separated allowed extensions")
    p_bfs.set_defaults(func=_bfs_index)
    
    # Find command
    p_find = subparsers.add_parser("find", help="Search for content")
    p_find.add_argument("query", help="Search query")
    p_find.add_argument("--max-results", type=int, default=10, help="Maximum results to return")
    p_find.add_argument("--page", type=int, default=1, help="Page number")
    p_find.add_argument("--per-page", type=int, default=10, help="Results per page")
    p_find.add_argument("--show-context", action="store_true", help="Show context snippets")
    p_find.add_argument("--case-sensitive", action="store_true", help="Case-sensitive search")
    p_find.add_argument("--exact", action="store_true", help="Exact match only")
    p_find.add_argument("--file-type", type=str, help="Filter by file extension (e.g. pdf,docx or .pdf,.docx)")
    p_find.add_argument("--path-contains", type=str, help="Filter: path must contain this string")
    p_find.add_argument("--no-expand", action="store_true", help="Disable query expansion with synonyms")
    p_find.set_defaults(func=_find)
    
    # Ask command
    p_ask = subparsers.add_parser("ask", help="Ask questions (placeholder)")
    p_ask.add_argument("query", help="Question to ask")
    p_ask.set_defaults(func=_ask)
    
    # Status command
    p_status = subparsers.add_parser("status", help="Check system status")
    p_status.set_defaults(func=_status)
    
    # Index browser command
    p_browser = subparsers.add_parser("index-browser", help="Index browser bookmarks and history")
    p_browser.set_defaults(func=_index_browser)

    # Reset DB command
    p_reset = subparsers.add_parser("reset-db", help="Clear all indexed data")
    p_reset.set_defaults(func=_reset_db)

    # Daemon command
    p_daemon = subparsers.add_parser("daemon", help="Run daemon for auto-indexing")
    p_daemon.add_argument("--startup-index", action="store_true", help="Run full index on startup")
    p_daemon.add_argument("--idle-updates", action="store_true", help="Run periodic full re-index when idle")
    p_daemon.add_argument("--interval", type=int, default=None, help="Minutes between idle updates (default: from config)")
    p_daemon.add_argument("--max-items", type=int, default=None, help="Max items per BFS slice")
    p_daemon.set_defaults(func=_daemon)
    
    args = parser.parse_args()
    
    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    logger.info("local-agent command: %s", args.cmd)
    try:
        args.func(args)
        return 0
    except Exception as e:
        logger.exception("Command failed: %s", e)
        print("Error:", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())