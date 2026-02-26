"""
FastAPI server for Local-Agent web UI.

Serves the search API and static frontend.
Run with: uvicorn web.server:app --reload
"""

import json
import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# GraphQL
from strawberry.fastapi import GraphQLRouter
from web.graphql_schema import schema

app = FastAPI(
    title="Local-Agent Search",
    description="Hybrid document search engine - semantic + lexical",
    version="1.0.0",
)

# CORS for local development
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GraphQL API for metrics
graphql_app = GraphQLRouter(schema, graphql_ide="graphiql")
app.include_router(graphql_app, prefix="/graphql")


@app.on_event("startup")
def preload_embedding_model():
    """Preload embedding model on startup so first search is fast (< 1s vs ~13s cold)."""
    try:
        from search.model_loader import get_embedding_model
        model = get_embedding_model()
        if model:
            model.encode(["warmup"], convert_to_tensor=False)
    except Exception:
        pass


class SearchRequest(BaseModel):
    query: str
    page: int = 1
    per_page: int = 10
    file_type: Optional[str] = None
    path_contains: Optional[str] = None
    exclude_images: bool = False  # Exclude image files when searching documents only
    expand_query: bool = True


class IndexRequest(BaseModel):
    path: str
    max_items: int = 100


class OpenFileRequest(BaseModel):
    path: str


@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Get system status (files indexed, Qdrant connection, etc.)."""
    try:
        from search.storage import create_storage
        from search.config import get_config

        config = get_config()
        qdrant, catalog = create_storage(config)

        # Get stats
        stats = catalog.get_file_stats()
        point_count = 0

        try:
            collection_info = qdrant.client.get_collection(qdrant.collection_name)
            point_count = collection_info.points_count
        except Exception:
            pass

        return {
            "status": "ok",
            "qdrant_connected": True,
            "files_indexed": stats.get("total_files", 0),
            "chunks_indexed": stats.get("total_chunks", 0),
            "vectors_count": point_count,
        }
    except Exception as e:
        return {
            "status": "error",
            "qdrant_connected": False,
            "files_indexed": 0,
            "chunks_indexed": 0,
            "vectors_count": 0,
            "error": str(e),
        }


@app.post("/api/search")
def search(request: SearchRequest) -> Dict[str, Any]:
    """Perform hybrid search."""
    try:
        from search.api import run

        filters = {}
        if request.file_type:
            exts = [f".{e.strip()}" if not e.strip().startswith(".") else e.strip()
                    for e in request.file_type.split(",")]
            filters["file_ext"] = exts
        if request.exclude_images:
            filters["exclude_file_ext"] = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]
        if request.path_contains:
            filters["path_contains"] = request.path_contains

        result = run(
            query=request.query,
            page=request.page,
            per_page=request.per_page,
            opts={
                "filters": filters,
                "expand_query": request.expand_query,
                "include_snippets": True,
            },
        )

        # Convert dataclasses to dicts for JSON
        items = []
        for hit in result.get("items", []):
            sb = hit.score_breakdown
            items.append({
                "path": hit.path,
                "score": hit.score,
                "file_type": hit.file_type,
                "snippet": hit.snippet,
                "chunk_id": hit.chunk_id,
                "score_breakdown": {
                    "cosine": getattr(sb, "cosine", 0),
                    "bm25": getattr(sb, "bm25", 0),
                    "exact": getattr(sb, "exact", 0),
                },
            })

        return {
            "query": result["query"],
            "total_hits": result["total_hits"],
            "page": result["page"],
            "per_page": result["per_page"],
            "total_pages": result["total_pages"],
            "has_next": result["has_next"],
            "has_prev": result["has_prev"],
            "items": items,
            "search_time": result["search_time"],
            "cache_hit": result.get("cache_hit", False),
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/index")
def start_index(request: IndexRequest) -> Dict[str, Any]:
    """Start indexing a directory (runs one BFS slice)."""
    try:
        from search.validation import sanitize_file_path
        from search.indexer import run_bfs_slice

        resolved, err = sanitize_file_path(request.path, must_exist=True)
        if err:
            raise HTTPException(status_code=400, detail=err)

        stats = run_bfs_slice(
            [str(resolved)],
            max_items=request.max_items,
            max_items_per_slice=request.max_items,
        )

        return {
            "status": "ok",
            "path": str(resolved),
            "files_processed": stats.files_processed,
            "chunks_created": stats.chunks_created,
            "duration_seconds": round(stats.duration_seconds, 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Human-friendly labels for known categories (before AI)
DISPLAY_LABELS = {
    "browser/bookmark": "Bookmarks",
    "browser/history": "Browsing history",
    "web": "Web links",
    "root": "Root",
    "other": "Other",
}

_ai_label_cache: Dict[str, str] = {}
_cache_path: Optional[Path] = None


def _get_label_cache_path(config: dict) -> Path:
    global _cache_path
    if _cache_path is None:
        store = Path(config.get("paths", {}).get("store", "store")).resolve()
        cache_dir = store / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_path = cache_dir / "ai_category_labels.json"
    return _cache_path


def _load_label_cache(config: dict) -> Dict[str, str]:
    try:
        p = _get_label_cache_path(config)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_label_cache(config: dict, cache: Dict[str, str]) -> None:
    try:
        p = _get_label_cache_path(config)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=0)
    except Exception:
        pass


def _heuristic_label(category: str) -> Optional[str]:
    """Fast heuristic labels for common paths - avoids Ollama call."""
    c = category.lower()
    if "documents" in c or "docs" in c:
        return "Documents"
    if "downloads" in c:
        return "Downloads"
    if "desktop" in c:
        return "Desktop"
    if "code" in c or "src" in c or "dev" in c:
        return "Code"
    if "pdf" in c or ".pdf" in c:
        return "PDFs"
    if "mail" in c or "email" in c:
        return "Email"
    return None


def _ai_category_label_impl(category: str, sample_text: str, config: dict) -> str:
    """Single Ollama call - used by worker. Optimized: shorter prompt, smaller snippet."""
    # Try heuristic first (no LLM call)
    h = _heuristic_label(category)
    if h:
        return h
    if not sample_text or len(sample_text.strip()) < 20:
        return category.replace("/", " / ")
    try:
        import ollama
        model = config.get("llm", {}).get("model", "llama3.2:3b")
        snippet = sample_text[:200].replace("\n", " ")
        prompt = f"Topic in 2-4 words: {snippet}\nLabel:"
        timeout = config.get("llm", {}).get("timeout_seconds", 15)
        r = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}], options={"num_predict": 10})
        label = (r.get("message", {}).get("content", "") or "").strip()
        for c in ('"', "'", "\n", "."):
            label = label.strip(c)
        if label and len(label) < 50:
            return label
    except Exception:
        pass
    return category.replace("/", " / ")


@app.get("/api/visualization")
def get_visualization(limit: int = 400, ai_labels: bool = True) -> Dict[str, Any]:
    """Get file graph data for 3D visualization and category breakdown."""
    try:
        from search.storage import create_storage
        from search.config import get_config
        from collections import defaultdict

        config = get_config()
        _, catalog = create_storage(config)
        files = catalog.list_files_for_visualization(limit=limit)

        # Build nodes and links for 3D force graph
        nodes = []
        node_ids = set()
        category_to_nodes: Dict[str, List[str]] = defaultdict(list)
        category_to_paths: Dict[str, List[str]] = defaultdict(list)

        for f in files:
            fid = f["file_id"]
            if fid in node_ids:
                continue
            node_ids.add(fid)
            name = Path(f["path"]).name if "/" in f["path"] or "\\" in f["path"] else f["path"]
            if f["path"].startswith("browser:"):
                parts = f["path"].split(":", 3)
                name = parts[2][:50] + "..." if len(parts[2]) > 50 else parts[2]
            nodes.append({
                "id": fid,
                "name": name,
                "path": f["path"],
                "category": f["category"],
                "file_type": f["file_type"],
                "chunk_count": f.get("chunk_count", 0),
                "source": f.get("source", "local" if not f["path"].startswith("browser:") else "browser"),
            })
            category_to_nodes[f["category"]].append(fid)
            category_to_paths[f["category"]].append(f["path"])

        # Links: connect files in same category (creates clusters)
        links = []
        seen_links = set()
        for cat, ids in category_to_nodes.items():
            for i, a in enumerate(ids):
                for b in ids[i + 1 : i + 4]:
                    key = (min(a, b), max(a, b))
                    if key not in seen_links:
                        seen_links.add(key)
                        links.append({"source": a, "target": b})

        # Category breakdown with AI-derived or human-friendly labels
        sorted_cats = sorted(category_to_nodes.items(), key=lambda x: -len(x[1]))
        max_ai_categories = 5
        cache = _load_label_cache(config) if ai_labels else {}
        categories = []
        to_compute: List[tuple] = []  # (cat, sample)

        for i, (cat, ids) in enumerate(sorted_cats):
            label = DISPLAY_LABELS.get(cat) or cache.get(cat)
            if label is not None:
                categories.append({
                    "name": cat,
                    "label": label,
                    "count": len(ids),
                    "file_type": next((n["file_type"] for n in nodes if n["id"] == ids[0]), "file"),
                })
            else:
                default_label = cat.replace("/", " / ")
                categories.append({
                    "name": cat,
                    "label": default_label,
                    "count": len(ids),
                    "file_type": next((n["file_type"] for n in nodes if n["id"] == ids[0]), "file"),
                })
                if ai_labels and len(to_compute) < max_ai_categories:
                    paths = category_to_paths.get(cat, [])
                    sample = catalog.get_sample_texts_for_paths(paths, max_chars=400) if paths else ""
                    to_compute.append((cat, sample))

        # Run Ollama in parallel for cache misses
        if to_compute:
            cache_updated = False
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {ex.submit(_ai_category_label_impl, cat, sample, config): cat for cat, sample in to_compute}
                results = {}
                for f in as_completed(futures, timeout=15):
                    cat = futures[f]
                    try:
                        label = f.result()
                        results[cat] = label
                        cache[cat] = label
                        cache_updated = True
                    except Exception:
                        results[cat] = cat.replace("/", " / ")
            if cache_updated:
                _save_label_cache(config, cache)
            for c in categories:
                if c["name"] in results:
                    c["label"] = results[c["name"]]

        local_count = sum(1 for n in nodes if n.get("source") == "local")
        browser_count = len(nodes) - local_count
        return {
            "nodes": nodes,
            "links": links,
            "categories": categories,
            "total_files": len(nodes),
            "local_count": local_count,
            "browser_count": browser_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/open-file")
def open_file(request: OpenFileRequest) -> Dict[str, Any]:
    """Open a local file in the system default application."""
    try:
        from search.validation import sanitize_file_path

        path_str = request.path.strip()
        if not path_str:
            raise HTTPException(status_code=400, detail="Path is required")

        # Reject browser/URL paths - only allow local filesystem paths
        if path_str.lower().startswith(("browser:", "http://", "https://", "mailto:")):
            raise HTTPException(
                status_code=400,
                detail="Only local file paths can be opened. Web and email links open in the browser.",
            )

        resolved, err = sanitize_file_path(path_str, must_exist=True)
        if err:
            raise HTTPException(status_code=400, detail=err)

        # Ensure path is under user home (security: prevent opening system files)
        home = Path.home().resolve()
        try:
            resolved = resolved.resolve()
            if not str(resolved).startswith(str(home)):
                raise HTTPException(
                    status_code=403,
                    detail="Path must be within your home directory",
                )
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"Invalid path: {e}")

        # Open with system default app
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", str(resolved)], check=True)
        elif system == "Linux":
            subprocess.run(["xdg-open", str(resolved)], check=True)
        elif system == "Windows":
            os.startfile(str(resolved))
        else:
            raise HTTPException(
                status_code=501,
                detail=f"Opening files not supported on {system}",
            )

        return {"status": "ok", "path": str(resolved)}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/index-browser")
def index_browser() -> Dict[str, Any]:
    """Index browser bookmarks and history (Chrome, Firefox)."""
    try:
        from search.browser_indexer import run_browser_index
        from search.config import get_config

        config = get_config()
        if not config.get("browser", {}).get("enabled", True):
            raise HTTPException(status_code=400, detail="Browser indexing is disabled in config")

        stats = run_browser_index(config)

        return {
            "status": "ok",
            "links_indexed": stats.chunks_created,
            "errors": stats.errors,
            "duration_seconds": round(stats.duration_seconds, 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")
else:
    @app.get("/")
    def index():
        return {"message": "Static files not found. Run from project root."}
