"""
Storage layer: Qdrant client + SQLite catalog/FTS5 integration.
"""

import sqlite3
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
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
        """Search vectors in Qdrant with timeout."""
        if not self.client:
            raise RuntimeError("Qdrant client not available")
        
        try:
            start_time = time.time()
            
            # Perform search with timeout consideration
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=embedding,
                limit=limit,
                timeout=int(timeout)
            )
            
            # Convert to our format
            hits = []
            for result in results:
                hits.append({
                    "chunk_id": result.id,
                    "score": result.score,
                    "payload": result.payload
                })
            
            elapsed = time.time() - start_time
            logger.debug(f"Vector search returned {len(hits)} results in {elapsed:.3f}s")
            
            return hits
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []


class Catalog:
    """SQLite catalog for file metadata and FTS5 search."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database connection and ensure schema exists."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        
        # Enable foreign key constraints
        self.conn.execute("PRAGMA foreign_keys = ON")
        
        # Check if schema exists
        cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        if not cursor.fetchone():
            logger.warning("Database schema not found. Run schema creation first.")
    
    def upsert_file(self, path: str, size: int, mtime: int, sha256: str) -> str:
        """Upsert file metadata and return file_id."""
        file_id = self._generate_file_id(path, mtime, size)
        
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO files (file_id, path, size, mtime, sha256, indexed_at)
                VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
            """, (file_id, path, size, mtime, sha256))
            
            self.conn.commit()
            return file_id
            
        except Exception as e:
            logger.error(f"Failed to upsert file {path}: {e}")
            raise
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file and cascade to chunks."""
        try:
            cursor = self.conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
            self.conn.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted file {file_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False
    
    def insert_chunks(self, file_id: str, chunks: List[Chunk]) -> bool:
        """Insert chunk metadata into catalog."""
        try:
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
            
            self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert chunks for file {file_id}: {e}")
            return False
    
    def fts_insert(self, chunk_id: str, text: str, path: str) -> bool:
        """Insert text into FTS5 index."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO chunks_fts (chunk_id, text, path)
                VALUES (?, ?, ?)
            """, (chunk_id, text, path))
            
            self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert FTS entry for chunk {chunk_id}: {e}")
            return False
    
    def fts_search(self, query: str, k: int = 200) -> List[Tuple[str, float]]:
        """Search FTS5 index and return (chunk_id, bm25_score) tuples."""
        try:
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
    
    def close(self):
        """Close database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
    
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
