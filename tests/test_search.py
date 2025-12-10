"""
Test suite for the hybrid search system.
"""

import pytest
import tempfile
import sqlite3
import shutil
from pathlib import Path
import time

# Import the modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from search.config import get_config, validate_config
from search.storage import Catalog, create_storage
from search.types import Chunk, SearchHit, ScoreBreakdown
from search.ids import file_id, chunk_id, generate_file_sha256
from search.snippets import make_snippet, highlight_query
from search.retriever import HybridRetriever
from search.api import SearchAPI


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_catalog.db"
    
    # Create schema
    conn = sqlite3.connect(str(db_path))
    with open(Path(__file__).parent.parent / "search" / "schemas.sql", 'r') as f:
        schema = f.read()
        conn.executescript(schema)
    conn.close()
    
    yield str(db_path)
    
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_config():
    """Create test configuration."""
    config = get_config()
    # Use temporary paths for testing
    config["paths"]["catalog"] = str(Path(tempfile.mkdtemp()) / "test_catalog.db")
    config["paths"]["store"] = tempfile.mkdtemp()
    return config


@pytest.fixture
def test_chunks():
    """Create test chunks."""
    chunks = [
        Chunk(
            path="/test/taipei.txt",
            file_id="file1",
            chunk_id="chunk1",
            text="Taipei is the capital city of Taiwan. It's a bustling metropolis with modern architecture.",
            token_start=0,
            token_end=20,
            mtime=int(time.time()),
            sha256="hash1",
            idx=0
        ),
        Chunk(
            path="/test/astrabit.txt", 
            file_id="file2",
            chunk_id="chunk2",
            text="Astrabit is a technology company focused on artificial intelligence and machine learning solutions.",
            token_start=0,
            token_end=25,
            mtime=int(time.time()),
            sha256="hash2",
            idx=0
        ),
        Chunk(
            path="/test/lorem.txt",
            file_id="file3", 
            chunk_id="chunk3",
            text="Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
            token_start=0,
            token_end=50,
            mtime=int(time.time()),
            sha256="hash3",
            idx=0
        )
    ]
    return chunks


class TestConfig:
    """Test configuration loading and validation."""
    
    def test_get_config(self):
        """Test configuration loading."""
        config = get_config()
        assert "index" in config
        assert "search" in config
        assert "qdrant" in config
        assert "paths" in config
    
    def test_validate_config(self):
        """Test configuration validation."""
        config = get_config()
        assert validate_config(config) == True
        
        # Test invalid config
        invalid_config = config.copy()
        invalid_config["search"]["bm25_weight"] = 2.0  # Invalid weight
        assert validate_config(invalid_config) == False


class TestIDs:
    """Test ID generation utilities."""
    
    def test_file_id(self):
        """Test file ID generation."""
        fid = file_id("/test/file.txt", 1234567890, 1024)
        assert isinstance(fid, str)
        assert len(fid) == 40  # SHA1 hex length
        
        # Same inputs should produce same ID
        fid2 = file_id("/test/file.txt", 1234567890, 1024)
        assert fid == fid2
    
    def test_chunk_id(self):
        """Test chunk ID generation."""
        file_id_str = "test_file_id_12345"
        cid = chunk_id(file_id_str, 0)
        assert isinstance(cid, str)
        assert len(cid) == 36  # UUID4 length
        
        # Same inputs should produce same ID
        cid2 = chunk_id(file_id_str, 0)
        assert cid == cid2
    
    def test_generate_file_sha256(self):
        """Test SHA256 generation."""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = f.name
        
        try:
            sha256 = generate_file_sha256(temp_path)
            assert isinstance(sha256, str)
            assert len(sha256) == 64  # SHA256 hex length
        finally:
            Path(temp_path).unlink()


class TestStorage:
    """Test storage layer."""
    
    def test_catalog_creation(self, temp_db):
        """Test catalog creation and basic operations."""
        catalog = Catalog(temp_db)
        
        # Test file upsert
        file_id = catalog.upsert_file("/test/file.txt", 1024, 1234567890, "sha256_hash")
        assert isinstance(file_id, str)
        
        # Test chunk insertion
        chunks = [
            Chunk(
                path="/test/file.txt",
                file_id=file_id,
                chunk_id="chunk1",
                text="test content",
                token_start=0,
                token_end=10,
                mtime=1234567890,
                sha256="chunk_hash",
                idx=0
            )
        ]
        
        success = catalog.insert_chunks(file_id, chunks)
        assert success == True
        
        # Test FTS insertion
        success = catalog.fts_insert("chunk1", "test content", "/test/file.txt")
        assert success == True
        
        # Test FTS search
        results = catalog.fts_search("test", 10)
        assert len(results) == 1
        assert results[0][0] == "chunk1"  # chunk_id
        
        catalog.close()
    
    def test_catalog_metadata(self, temp_db):
        """Test catalog metadata operations."""
        catalog = Catalog(temp_db)
        
        file_id = catalog.upsert_file("/test/file.txt", 1024, 1234567890, "sha256_hash")
        
        # Test chunk metadata
        chunks = [
            Chunk(
                path="/test/file.txt",
                file_id=file_id,
                chunk_id="chunk1",
                text="test content",
                token_start=0,
                token_end=10,
                mtime=1234567890,
                sha256="chunk_hash",
                idx=0
            )
        ]
        
        catalog.insert_chunks(file_id, chunks)
        
        # Test getting chunk metadata
        meta = catalog.chunk_meta("chunk1")
        assert meta is not None
        assert meta["chunk_id"] == "chunk1"
        assert meta["file_id"] == file_id
        
        # Test getting file path
        path = catalog.get_file_path(file_id)
        assert path == "/test/file.txt"
        
        catalog.close()


class TestSnippets:
    """Test snippet generation."""
    
    def test_make_snippet(self):
        """Test snippet generation."""
        text = "This is a long document about artificial intelligence and machine learning technologies."
        query = "artificial intelligence"
        
        snippet, start, end = make_snippet(text, query, radius=20)
        
        assert isinstance(snippet, str)
        assert len(snippet) > 0
        assert start >= 0
        assert end <= len(text)
    
    def test_highlight_query(self):
        """Test query highlighting."""
        snippet = "This document discusses artificial intelligence and machine learning."
        query = "artificial intelligence"
        
        highlighted = highlight_query(snippet, query)
        
        assert "**artificial**" in highlighted
        assert "**intelligence**" in highlighted
    
    def test_make_snippet_no_match(self):
        """Test snippet generation with no match."""
        text = "This document has no relevant content."
        query = "nonexistent"
        
        snippet, start, end = make_snippet(text, query, radius=20)
        
        assert len(snippet) > 0
        assert start == 0
        assert end <= len(text)


class TestRetriever:
    """Test hybrid retriever."""
    
    def test_retriever_creation(self, test_config):
        """Test retriever creation."""
        # Mock the storage creation to avoid Qdrant dependency
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            retriever = HybridRetriever(test_config)
            assert retriever is not None
            assert retriever.config == test_config
    
    def test_query_embedding(self, test_config):
        """Test query embedding generation."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            retriever = HybridRetriever(test_config)
            
            # Mock sentence transformer
            import numpy as np
            m.setattr('sentence_transformers.SentenceTransformer', lambda x, device=None: type('MockModel', (), {
                'encode': lambda self, texts, convert_to_tensor=False: np.random.random((len(texts), 384))
            })())
            
            embedding = retriever.embed_query("test query")
            assert embedding is not None
            assert len(embedding) == 384
    
    def test_score_normalization(self, test_config):
        """Test score normalization."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            retriever = HybridRetriever(test_config)
            
            candidates = {"chunk1": 0.8, "chunk2": 0.6, "chunk3": 0.4}
            normalized = retriever._normalize_scores(candidates)
            
            assert len(normalized) == 3
            assert max(normalized.values()) == 1.0
            assert min(normalized.values()) == 0.0
    
    def test_exact_match_calculation(self, test_config):
        """Test exact match calculation."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            retriever = HybridRetriever(test_config)
            
            # Test exact phrase match
            score1 = retriever._calculate_exact_match("artificial intelligence", "This is about artificial intelligence research")
            assert score1 == 1.0
            
            # Test word match
            score2 = retriever._calculate_exact_match("machine learning", "This document discusses machine algorithms and learning techniques")
            assert 0.5 <= score2 <= 1.0  # Should be high due to word overlap
            
            # Test no match
            score3 = retriever._calculate_exact_match("nonexistent", "This has no relevant content")
            assert score3 == 0.0


class TestAPI:
    """Test search API."""
    
    def test_api_creation(self, test_config):
        """Test API creation."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            api = SearchAPI(test_config)
            assert api is not None
            assert api.config == test_config
    
    def test_cache_functionality(self, test_config):
        """Test search result caching."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            api = SearchAPI(test_config)
            
            # Mock retriever to return consistent results
            mock_results = []
            m.setattr('search.retriever.HybridRetriever.search', lambda self, query, k, timeout: mock_results)
            
            query = "test query"
            cache_key = api._generate_cache_key(query, 10, 1, 10, {})
            
            # First search (should miss cache)
            result1 = api.run(query, k=10, page=1, per_page=10)
            assert result1["cache_hit"] == False
            
            # Second search (should hit cache)
            result2 = api.run(query, k=10, page=1, per_page=10)
            assert result2["cache_hit"] == True
    
    def test_pagination(self, test_config):
        """Test result pagination."""
        with pytest.MonkeyPatch().context() as m:
            m.setattr('search.storage.create_storage', lambda x: (None, None))
            
            api = SearchAPI(test_config)
            
            # Mock retriever to return multiple results
            mock_results = [
                type('MockChunk', (), {
                    'path': f'/test/file{i}.txt',
                    'score': 1.0 - i * 0.1,
                    'score_breakdown': ScoreBreakdown(final=1.0 - i * 0.1),
                    'chunk_id': f'chunk{i}',
                    'file_id': f'file{i}',
                    'chunk_idx': 0,
                    'text': f'Content of file {i}'
                })() for i in range(5)
            ]
            
            m.setattr('search.retriever.HybridRetriever.search', lambda self, query, k, timeout: mock_results)
            m.setattr('search.retriever.HybridRetriever.dedupe_by_file', lambda self, chunks, max_results_per_file: chunks)
            
            # Test first page
            result1 = api.run("test", k=10, page=1, per_page=2)
            assert result1["page"] == 1
            assert result1["per_page"] == 2
            assert len(result1["items"]) == 2
            assert result1["total_hits"] == 5
            
            # Test second page
            result2 = api.run("test", k=10, page=2, per_page=2)
            assert result2["page"] == 2
            assert len(result2["items"]) == 2
            
            # Test third page (should have remaining results)
            result3 = api.run("test", k=10, page=3, per_page=2)
            assert result3["page"] == 3
            assert len(result3["items"]) == 1


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
