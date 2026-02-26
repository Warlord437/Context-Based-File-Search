"""
Storage layer: Qdrant client + SQLite catalog/FTS5 integration.
"""

import sqlite3
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import time

from .types import Chunk, FileMeta, ScoredChunk
from .config import get_config

logger = logging.getLogger(__name__)

class QdrantStore:
    """Qdrant vector store with server connection."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = None
        self.collection_name = config["qdrant"]["collection"]
        self.dim = config["qdrant"]["dim"]
        self._init_client()
    
    def _init_client(self):
        """Initialize Qdrant client with server connection."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance, PointStruct
            
            self.QdrantClient = QdrantClient
            self.VectorParams = VectorParams
            self.Distance = Distance
            self.PointStruct = PointStruct
            
            # Try server connection first
            url = self.config["qdrant"]["url"]
            prefer_grpc = self.config["qdrant"]["prefer_grpc"]
            
            self.client = QdrantClient(url=url, prefer_grpc=prefer_grpc)
            
            # Test connection
            collections = self.client.get_collections()
            logger.info(f"Connected to Qdrant server at {url}")
            
        except ImportError:
            logger.error("qdrant-client not installed")
            self.client = None
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant server: {e}")
            self.client = None
    
    def ensure_collection(self):
        """Ensure the collection exists with proper configuration."""
        if not self.client:
            raise RuntimeError("Qdrant client not available")
        
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                # Create collection with optimized parameters
                hnsw_config = self.config["qdrant"]["hnsw_config"]
                optimizers_config = self.config["qdrant"]["optimizers_config"]
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=self.VectorParams(
                        size=self.dim,
                        distance=self.Distance.COSINE
                    ),
                    hnsw_config=hnsw_config,
                    optimizers_config=optimizers_config
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Using existing Qdrant collection: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise
    
    def upsert_vectors(self, points: List[Dict[str, Any]]) -> bool:
        """Upsert vectors to Qdrant in batches."""
        if not self.client:
            raise RuntimeError("Qdrant client not available")
        
        if not points:
            return True
        
        try:
            # Convert to Qdrant points
            qdrant_points = []
            for point in points:
                qdrant_points.append(self.PointStruct(
                    id=point["id"],
                    vector=point["vector"],
                    payload=point["payload"]
                ))
            
            # Batch upsert
            batch_size = self.config["index"]["upsert_batch"]
            
            for i in range(0, len(qdrant_points), batch_size):
                batch = qdrant_points[i:i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
            
            logger.info(f"Upserted {len(points)} vectors to Qdrant")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert vectors: {e}")
            return False
    
    def vector_search(self, embedding: List[float], limit: int, timeout: float = 2.5) -> List[Dict[str, Any]]:
        """Search vectors in Qdrant with timeout. Uses query_points API (qdrant-client 1.7+)."""
        if not self.client:
            raise RuntimeError("Qdrant client not available")
        
        try:
            start_time = time.time()
            
            # Use query_points (replaces deprecated search() in qdrant-client 1.7+)
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=limit,
                timeout=int(timeout) if timeout else None
            )
            
            # Convert to our format (response.points = list of ScoredPoint)
            hits = []
            for point in (response.points or []):
                hits.append({
                    "chunk_id": point.id,
                    "score": point.score,
                    "payload": point.payload or {}
                })
            
            elapsed = time.time() - start_time
            logger.debug(f"Vector search returned {len(hits)} results in {elapsed:.3f}s")
            
            return hits
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def delete_points_by_path_prefix(self, path_prefix: str) -> int:
        """
        Delete points whose payload path starts with prefix (e.g. 'browser:').
        Returns number of points deleted.
        """
        if not self.client or not path_prefix:
            return 0
        try:
            ids = []
            offset = None
            while True:
                result, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=None,
                    limit=2000,
                    offset=offset,
                    with_payload=["path"],
                    with_vectors=False,
                )
                for rec in result:
                    path_val = (rec.payload or {}).get("path", "")
                    if isinstance(path_val, str) and path_val.startswith(path_prefix):
                        ids.append(rec.id)
                if offset is None or not result:
                    break
            if ids:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=ids,
                )
                logger.info(f"Deleted {len(ids)} Qdrant points with path prefix '{path_prefix}'")
            return len(ids)
        except Exception as e:
            logger.warning(f"Qdrant delete by prefix failed: {e}")
            return 0


class Catalog:
    """SQLite catalog for file metadata and FTS5 search."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database connection and ensure schema exists."""
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access

        # Performance: WAL mode and tuning for faster reads/writes
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            self.conn.execute("PRAGMA temp_store = MEMORY")
        except Exception as e:
            logger.debug("SQLite pragmas (non-fatal): %s", e)

        # Enable foreign key constraints
        self.conn.execute("PRAGMA foreign_keys = ON")
        
        # Check if schema exists
        cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        if not cursor.fetchone():
            logger.info("Database schema not found. Creating schema...")
            self._create_schema()
    
    def _create_schema(self):
        """Create database schema from schemas.sql file."""
        try:
            # Get the path to schemas.sql relative to this file
            schema_path = Path(__file__).parent / "schemas.sql"
            
            if not schema_path.exists():
                logger.error(f"Schema file not found at {schema_path}")
                raise FileNotFoundError(f"Schema file not found: {schema_path}")
            
            # Read and execute schema
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            # Execute the schema (executescript handles multiple statements)
            with self.transaction():
                self.conn.executescript(schema_sql)
                # Auto-commits on success, auto-rollback on error
            
            logger.info("Database schema created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create database schema: {e}")
            raise RuntimeError(f"Failed to initialize database schema: {e}") from e
    
    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions with automatic rollback on errors.
        
        Usage:
            with catalog.transaction():
                catalog.conn.execute("INSERT ...")
                # Auto-commits on success, auto-rollback on error
        """
        try:
            yield self.conn
            self.conn.commit()
            logger.debug("Transaction committed successfully")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back due to error: {e}")
            raise
    
    def upsert_file(self, path: str, size: int, mtime: int, sha256: str, 
                    in_transaction: bool = False, file_id: str = None) -> str:
        """
        Upsert file metadata and return file_id.
        
        Args:
            path: File path
            size: File size in bytes
            mtime: Modification time
            sha256: File hash
            in_transaction: If True, don't commit (caller handles transaction)
            file_id: Optional explicit file_id (e.g. for browser entries)
        
        Returns:
            file_id string
        """
        file_id = file_id or self._generate_file_id(path, mtime, size)
        
        try:
            if in_transaction:
                # Part of larger transaction, don't commit here
                self.conn.execute("""
                    INSERT OR REPLACE INTO files (file_id, path, size, mtime, sha256, indexed_at)
                    VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
                """, (file_id, path, size, mtime, sha256))
            else:
                # Standalone operation, use transaction
                with self.transaction():
                    self.conn.execute("""
                        INSERT OR REPLACE INTO files (file_id, path, size, mtime, sha256, indexed_at)
                        VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
                    """, (file_id, path, size, mtime, sha256))
            
            return file_id
            
        except Exception as e:
            logger.error(f"Failed to upsert file {path}: {e}")
            raise
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file and cascade to chunks."""
        try:
            with self.transaction():
                cursor = self.conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
                # Auto-commits on success, auto-rollback on error
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted file {file_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False
    
    def insert_chunks(self, file_id: str, chunks: List[Chunk], 
                     in_transaction: bool = False) -> bool:
        """
        Insert chunk metadata into catalog.
        
        Args:
            file_id: File ID
            chunks: List of Chunk objects
            in_transaction: If True, don't commit (caller handles transaction)
        
        Returns:
            True if successful
        """
        try:
            if in_transaction:
                # Part of larger transaction, don't commit here
                # Delete existing chunks for this file
                self.conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
                
                # Insert new chunks
                chunk_data = []
                for chunk in chunks:
                    chunk_data.append((
                        chunk.chunk_id,
                        file_id,
                        chunk.idx,
                        chunk.token_start,
                        chunk.token_end
                    ))
                
                self.conn.executemany("""
                    INSERT INTO chunks (chunk_id, file_id, idx, token_start, token_end, created_at)
                    VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
                """, chunk_data)
            else:
                # Standalone operation, use transaction
                with self.transaction():
                    # Delete existing chunks for this file
                    self.conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
                    
                    # Insert new chunks
                    chunk_data = []
                    for chunk in chunks:
                        chunk_data.append((
                            chunk.chunk_id,
                            file_id,
                            chunk.idx,
                            chunk.token_start,
                            chunk.token_end
                        ))
                    
                    self.conn.executemany("""
                        INSERT INTO chunks (chunk_id, file_id, idx, token_start, token_end, created_at)
                        VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
                    """, chunk_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert chunks for file {file_id}: {e}")
            return False
    
    def fts_insert(self, chunk_id: str, text: str, path: str, 
                   in_transaction: bool = False) -> bool:
        """
        Insert text into FTS5 index.
        
        Args:
            chunk_id: Chunk ID
            text: Chunk text
            path: File path
            in_transaction: If True, don't commit (caller handles transaction)
        
        Returns:
            True if successful
        """
        try:
            if in_transaction:
                # Part of larger transaction, don't commit here
                self.conn.execute("""
                    INSERT OR REPLACE INTO chunks_fts (chunk_id, text, path)
                    VALUES (?, ?, ?)
                """, (chunk_id, text, path))
            else:
                # Standalone operation, use transaction
                with self.transaction():
                    self.conn.execute("""
                        INSERT OR REPLACE INTO chunks_fts (chunk_id, text, path)
                        VALUES (?, ?, ?)
                    """, (chunk_id, text, path))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert FTS entry for chunk {chunk_id}: {e}")
            return False
    
    def fts_search(self, query: str, k: int = 200) -> List[Tuple[str, float]]:
        """Search FTS5 index and return (chunk_id, bm25_score) tuples."""
        try:
            # Sanitize query (defense-in-depth if called directly)
            from .validation import sanitize_fts_query
            query = sanitize_fts_query(query)
            if not query:
                return []
            k = max(1, min(int(k) if isinstance(k, (int, float)) else 200, 1000))

            # Use FTS5 match syntax with BM25 ranking
            cursor = self.conn.execute("""
                SELECT chunk_id, bm25(chunks_fts) as score
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY bm25(chunks_fts)
                LIMIT ?
            """, (query, k))
            
            results = []
            for row in cursor:
                # BM25 scores are typically negative, convert to positive
                score = abs(float(row["score"]))
                results.append((row["chunk_id"], score))
            
            logger.debug(f"FTS search returned {len(results)} results for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"FTS search failed for query '{query}': {e}")
            return []
    
    def get_sample_texts_for_paths(self, paths: List[str], max_chars: int = 600) -> str:
        """Get combined sample text from chunks_fts for given paths (for AI categorization)."""
        if not paths:
            return ""
        try:
            limited_paths = paths[:20]
            placeholders = ",".join("?" * len(limited_paths))
            cursor = self.conn.execute(f"""
                SELECT text FROM chunks_fts
                WHERE path IN ({placeholders})
                LIMIT 5
            """, limited_paths)
            texts = []
            total = 0
            for row in cursor:
                t = (row["text"] or "").strip()
                if t and total < max_chars:
                    snippet = t[:max_chars - total] if len(t) + total > max_chars else t
                    texts.append(snippet)
                    total += len(snippet)
            return "\n---\n".join(texts) if texts else ""
        except Exception as e:
            logger.debug(f"get_sample_texts_for_paths failed: {e}")
            return ""

    def get_chunk_text(self, chunk_id: str) -> Optional[str]:
        """Get chunk text from FTS5 index."""
        try:
            cursor = self.conn.execute("""
                SELECT text FROM chunks_fts WHERE chunk_id = ?
            """, (chunk_id,))
            
            row = cursor.fetchone()
            return row["text"] if row else None
            
        except Exception as e:
            logger.error(f"Failed to get chunk text for {chunk_id}: {e}")
            return None
    
    def get_file_path(self, file_id: str) -> Optional[str]:
        """Get file path by file_id."""
        try:
            cursor = self.conn.execute("""
                SELECT path FROM files WHERE file_id = ?
            """, (file_id,))
            
            row = cursor.fetchone()
            return row["path"] if row else None
            
        except Exception as e:
            logger.error(f"Failed to get file path for {file_id}: {e}")
            return None
    
    def chunk_meta(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get chunk metadata."""
        try:
            cursor = self.conn.execute("""
                SELECT c.chunk_id, c.file_id, c.idx, c.token_start, c.token_end, f.path
                FROM chunks c
                JOIN files f ON c.file_id = f.file_id
                WHERE c.chunk_id = ?
            """, (chunk_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "chunk_id": row["chunk_id"],
                    "file_id": row["file_id"],
                    "idx": row["idx"],
                    "token_start": row["token_start"],
                    "token_end": row["token_end"],
                    "path": row["path"]
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chunk metadata for {chunk_id}: {e}")
            return None

    def chunks_meta_and_text_batch(self, chunk_ids: List[str]) -> Dict[str, Tuple[Dict[str, Any], str]]:
        """
        Batch fetch chunk metadata and text for many chunk IDs in 2 queries.
        Returns dict: chunk_id -> (meta_dict, text)
        """
        if not chunk_ids:
            return {}
        try:
            seen = set(chunk_ids)
            chunk_ids = list(seen)
            placeholders = ",".join("?" * len(chunk_ids))

            # Single query for metadata
            meta_rows = self.conn.execute(f"""
                SELECT c.chunk_id, c.file_id, c.idx, c.token_start, c.token_end, f.path
                FROM chunks c
                JOIN files f ON c.file_id = f.file_id
                WHERE c.chunk_id IN ({placeholders})
            """, chunk_ids).fetchall()

            # Single query for text
            text_rows = self.conn.execute(f"""
                SELECT chunk_id, text FROM chunks_fts WHERE chunk_id IN ({placeholders})
            """, chunk_ids).fetchall()

            text_map = {r["chunk_id"]: (r["text"] or "") for r in text_rows}
            result = {}
            for row in meta_rows:
                cid = row["chunk_id"]
                meta = {
                    "chunk_id": cid,
                    "file_id": row["file_id"],
                    "idx": row["idx"],
                    "token_start": row["token_start"],
                    "token_end": row["token_end"],
                    "path": row["path"]
                }
                result[cid] = (meta, text_map.get(cid, ""))
            return result
        except Exception as e:
            logger.error(f"Batch chunk fetch failed: {e}")
            return {}
    
    def list_files_for_visualization(self, limit: int = 500) -> List[Dict[str, Any]]:
        """
        List files with path and metadata for visualization.
        Returns path, file_id, derived category, file_type, and source (local|browser).
        Uses balanced sampling so both local files and browser links are included.
        """
        try:
            # Balanced sampling: get ~half from local, ~half from browser (if both exist)
            half = max(limit // 2, 50)
            local_rows = []
            browser_rows = []
            cursor = self.conn.execute("""
                SELECT f.file_id, f.path, f.size,
                       (SELECT COUNT(*) FROM chunks c WHERE c.file_id = f.file_id) as chunk_count
                FROM files f
                WHERE f.path NOT LIKE 'browser:%'
                ORDER BY f.indexed_at DESC
                LIMIT ?
            """, (half,))
            local_rows = [dict(r) for r in cursor.fetchall()]
            cursor = self.conn.execute("""
                SELECT f.file_id, f.path, f.size,
                       (SELECT COUNT(*) FROM chunks c WHERE c.file_id = f.file_id) as chunk_count
                FROM files f
                WHERE f.path LIKE 'browser:%'
                ORDER BY f.indexed_at DESC
                LIMIT ?
            """, (half,))
            browser_rows = [dict(r) for r in cursor.fetchall()]
            # Interleave: local first, then browser, up to limit
            rows = (local_rows + browser_rows)[:limit]
            result = []
            for row in rows:
                path = row["path"]
                category, file_type = self._derive_category_and_type(path)
                source = "browser" if path.lower().startswith("browser:") else "local"
                result.append({
                    "file_id": row["file_id"],
                    "path": path,
                    "size": row["size"],
                    "chunk_count": row["chunk_count"],
                    "category": category,
                    "file_type": file_type,
                    "source": source,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to list files for visualization: {e}")
            return []

    def _derive_category_and_type(self, path: str) -> Tuple[str, str]:
        """Derive category (folder/source) and file type from path."""
        path_lower = path.lower()
        if path_lower.startswith("browser:"):
            parts = path.split(":", 3)
            source = parts[1] if len(parts) > 1 else "browser"
            return f"browser/{source}", "url"
        ext = Path(path).suffix.lower() if "." in path else ""
        if not ext and ("http" in path_lower or "www." in path_lower):
            return "web", "url"
        # Local file: use parent path as category (e.g. Documents/Projects)
        try:
            p = Path(path).expanduser()
            parts = p.parts
            if len(parts) >= 2:
                # Skip root, use first 2 dirs e.g. Users/name/Documents/Projects -> Documents/Projects
                home_parts = Path.home().parts
                if len(parts) > len(home_parts) and parts[: len(home_parts)] == home_parts:
                    category = "/".join(parts[len(home_parts) : -1]) or "root"
                else:
                    category = "/".join(parts[-2:-1]) if len(parts) > 1 else "root"
            else:
                category = "root"
        except Exception:
            category = "other"
        type_map = {
            ".pdf": "pdf", ".md": "markdown", ".markdown": "markdown",
            ".txt": "text", ".docx": "docx", ".html": "html", ".htm": "html",
            ".rtf": "rtf",
        }
        file_type = type_map.get(ext, ext.lstrip(".") or "file")
        return category, file_type

    def get_file_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        try:
            cursor = self.conn.execute("SELECT * FROM db_stats")
            row = cursor.fetchone()
            
            if row:
                return {
                    "total_files": row["total_files"],
                    "total_chunks": row["total_chunks"],
                    "total_fts_entries": row["total_fts_entries"],
                    "unique_paths": row["unique_paths"],
                    "total_size_bytes": row["total_size_bytes"]
                }
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get file stats: {e}")
            return {}

    def get_recent_indexing(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent indexing operations for metrics."""
        try:
            cursor = self.conn.execute(
                "SELECT operation, files_processed, chunks_created, files_skipped, errors, "
                "duration_seconds, timestamp, datetime(timestamp, 'unixepoch') as timestamp_str "
                "FROM index_stats ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"get_recent_indexing: {e}")
            return []

    def get_recent_searches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent search operations for metrics."""
        try:
            cursor = self.conn.execute(
                "SELECT query, total_candidates, vector_candidates, lexical_candidates, "
                "final_results, duration_seconds, cache_hit, timestamp, "
                "datetime(timestamp, 'unixepoch') as timestamp_str "
                "FROM search_stats ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"get_recent_searches: {e}")
            return []

    def get_index_stats_summary(self) -> Dict[str, Any]:
        """Get aggregated indexing metrics."""
        try:
            cursor = self.conn.execute(
                "SELECT COUNT(*) as total_ops, SUM(files_processed) as total_files, "
                "SUM(chunks_created) as total_chunks, SUM(errors) as total_errors, "
                "AVG(duration_seconds) as avg_duration "
                "FROM index_stats"
            )
            row = cursor.fetchone()
            return dict(row) if row else {}
        except Exception as e:
            logger.debug(f"get_index_stats_summary: {e}")
            return {}

    def get_search_stats_summary(self) -> Dict[str, Any]:
        """Get aggregated search metrics."""
        try:
            cursor = self.conn.execute(
                "SELECT COUNT(*) as total_searches, SUM(cache_hit) as cache_hits, "
                "AVG(duration_seconds) as avg_duration, AVG(final_results) as avg_results "
                "FROM search_stats"
            )
            row = cursor.fetchone()
            return dict(row) if row else {}
        except Exception as e:
            logger.debug(f"get_search_stats_summary: {e}")
            return {}

    def insert_index_stats(
        self,
        operation: str = "bfs_slice",
        files_processed: int = 0,
        chunks_created: int = 0,
        files_skipped: int = 0,
        errors: int = 0,
        duration_seconds: float = 0,
    ) -> None:
        """Record an indexing operation for metrics."""
        try:
            self.conn.execute(
                "INSERT INTO index_stats (operation, files_processed, chunks_created, files_skipped, errors, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (operation, files_processed, chunks_created, files_skipped, errors, duration_seconds),
            )
            self.conn.commit()
        except Exception as e:
            logger.debug(f"insert_index_stats: {e}")

    def insert_search_stats(
        self,
        query: str,
        total_candidates: int = 0,
        vector_candidates: int = 0,
        lexical_candidates: int = 0,
        final_results: int = 0,
        duration_seconds: float = 0,
        cache_hit: bool = False,
    ) -> None:
        """Record a search operation for metrics."""
        try:
            self.conn.execute(
                "INSERT INTO search_stats (query, total_candidates, vector_candidates, lexical_candidates, "
                "final_results, duration_seconds, cache_hit) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (query[:500], total_candidates, vector_candidates, lexical_candidates, final_results, duration_seconds, 1 if cache_hit else 0),
            )
            self.conn.commit()
        except Exception as e:
            logger.debug(f"insert_search_stats: {e}")

    def get_file_type_distribution(self) -> List[Dict[str, Any]]:
        """Get file count by type (extension) for analytics."""
        try:
            cursor = self.conn.execute("""
                SELECT
                  CASE
                    WHEN path LIKE 'browser:%' THEN 'link'
                    WHEN path LIKE '%.pdf' THEN 'pdf'
                    WHEN path LIKE '%.md' OR path LIKE '%.markdown' THEN 'markdown'
                    WHEN path LIKE '%.txt' THEN 'txt'
                    WHEN path LIKE '%.docx' OR path LIKE '%.doc' THEN 'docx'
                    WHEN path LIKE '%.html' OR path LIKE '%.htm' THEN 'html'
                    WHEN path LIKE '%.png' OR path LIKE '%.jpg' OR path LIKE '%.jpeg' THEN 'image'
                    ELSE 'other'
                  END as file_type,
                  COUNT(*) as count
                FROM files
                GROUP BY file_type
                ORDER BY count DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"get_file_type_distribution: {e}")
            return []

    def get_top_queries(self, limit: int = 20, since_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get most frequent search queries."""
        try:
            if since_hours:
                since_ts = int(time.time()) - (since_hours * 3600)
                cursor = self.conn.execute("""
                    SELECT query, COUNT(*) as count, AVG(duration_seconds) as avg_duration
                    FROM search_stats WHERE timestamp >= ?
                    GROUP BY LOWER(TRIM(query))
                    ORDER BY count DESC LIMIT ?
                """, (since_ts, limit))
            else:
                cursor = self.conn.execute("""
                    SELECT query, COUNT(*) as count, AVG(duration_seconds) as avg_duration
                    FROM search_stats
                    GROUP BY LOWER(TRIM(query))
                    ORDER BY count DESC LIMIT ?
                """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"get_top_queries: {e}")
            return []

    def get_search_time_series(
        self, since_hours: int = 24, bucket_hours: int = 1
    ) -> List[Dict[str, Any]]:
        """Get search volume over time (bucket by hour)."""
        try:
            since_ts = int(time.time()) - (since_hours * 3600)
            cursor = self.conn.execute("""
                SELECT
                  (timestamp / ?) * ? as bucket_start,
                  datetime((timestamp / ?) * ?, 'unixepoch') as bucket_str,
                  COUNT(*) as count,
                  AVG(duration_seconds) as avg_duration,
                  SUM(cache_hit) as cache_hits
                FROM search_stats
                WHERE timestamp >= ?
                GROUP BY bucket_start
                ORDER BY bucket_start
            """, (bucket_hours * 3600, bucket_hours * 3600, bucket_hours * 3600, bucket_hours * 3600, since_ts))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"get_search_time_series: {e}")
            return []

    def get_index_time_series(
        self, since_hours: int = 168, bucket_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get indexing volume over time (bucket by day by default)."""
        try:
            since_ts = int(time.time()) - (since_hours * 3600)
            bucket_sec = bucket_hours * 3600
            cursor = self.conn.execute("""
                SELECT
                  (timestamp / ?) * ? as bucket_start,
                  datetime((timestamp / ?) * ?, 'unixepoch') as bucket_str,
                  SUM(files_processed) as files_processed,
                  SUM(chunks_created) as chunks_created,
                  COUNT(*) as ops_count
                FROM index_stats
                WHERE timestamp >= ?
                GROUP BY bucket_start
                ORDER BY bucket_start
            """, (bucket_sec, bucket_sec, bucket_sec, bucket_sec, since_ts))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"get_index_time_series: {e}")
            return []

    def get_search_percentiles(self, since_hours: Optional[int] = None) -> Dict[str, float]:
        """Get p50, p95, p99 for search duration (seconds)."""
        try:
            if since_hours:
                since_ts = int(time.time()) - (since_hours * 3600)
                cursor = self.conn.execute(
                    "SELECT duration_seconds FROM search_stats WHERE timestamp >= ? ORDER BY duration_seconds",
                    (since_ts,),
                )
            else:
                cursor = self.conn.execute(
                    "SELECT duration_seconds FROM search_stats ORDER BY duration_seconds"
                )
            rows = [r["duration_seconds"] for r in cursor.fetchall()]
            if not rows:
                return {"p50": 0, "p95": 0, "p99": 0}
            n = len(rows)
            return {
                "p50": float(rows[int(n * 0.50)]),
                "p95": float(rows[int(n * 0.95)]) if n > 20 else float(rows[-1]),
                "p99": float(rows[int(n * 0.99)]) if n > 100 else float(rows[-1]),
            }
        except Exception as e:
            logger.debug(f"get_search_percentiles: {e}")
            return {"p50": 0, "p95": 0, "p99": 0}

    def close(self):
        """Close database connection."""
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")
    
    def __enter__(self):
        """Context manager entry - allows 'with Catalog(...)' usage."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically closes connection."""
        self.close()
        return False  # Don't suppress exceptions
    
    def _generate_file_id(self, path: str, mtime: int, size: int) -> str:
        """Generate stable file ID."""
        content = f"{path}|{mtime}|{size}"
        return hashlib.sha1(content.encode()).hexdigest()


def create_storage(config: Dict[str, Any]) -> Tuple[QdrantStore, Catalog]:
    """Create and initialize storage instances."""
    # Create Qdrant store
    qdrant_store = QdrantStore(config)
    qdrant_store.ensure_collection()
    
    # Create catalog
    catalog_path = config["paths"]["catalog"]
    catalog = Catalog(catalog_path)
    
    return qdrant_store, catalog


if __name__ == "__main__":
    # Test storage layer
    config = get_config()
    qdrant, catalog = create_storage(config)
    
    print("Storage layer initialized:")
    print(f"Qdrant: {'Connected' if qdrant.client else 'Not available'}")
    print(f"Catalog: {catalog.db_path}")
    
    # Test FTS search
    results = catalog.fts_search("test", 10)
    print(f"FTS search test: {len(results)} results")
    
    catalog.close()
