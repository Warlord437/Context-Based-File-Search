"""
Data contracts and type definitions for the hybrid search system.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

@dataclass
class Chunk:
    """Represents a text chunk with metadata."""
    path: str
    file_id: str
    chunk_id: str
    text: str
    token_start: int
    token_end: int
    mtime: int
    sha256: str
    idx: int = 0

@dataclass
class ScoreBreakdown:
    """Detailed scoring breakdown for search results."""
    cosine: float = 0.0
    bm25: float = 0.0
    exact: float = 0.0
    position_bonus: float = 0.0
    final: float = 0.0

@dataclass
class SearchHit:
    """A search result with scoring details."""
    path: str
    score: float
    score_breakdown: ScoreBreakdown
    file_type: str
    chunk_id: str
    snippet: str
    context_range: Tuple[int, int]
    file_id: str
    chunk_idx: int = 0

@dataclass
class FileMeta:
    """File metadata for tracking changes."""
    file_id: str
    path: str
    size: int
    mtime: int
    sha256: str

@dataclass
class ScoredChunk:
    """A chunk with its search score."""
    chunk_id: str
    file_id: str
    path: str
    text: str
    score: float
    score_breakdown: ScoreBreakdown
    chunk_idx: int = 0

@dataclass
class SearchOptions:
    """Options for search behavior."""
    exact_match: bool = False
    case_sensitive: bool = False
    max_results_per_file: int = 1
    include_snippets: bool = True
    snippet_radius: int = 50

@dataclass
class IndexStats:
    """Statistics for indexing operations."""
    files_processed: int = 0
    chunks_created: int = 0
    files_skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0

@dataclass
class SearchStats:
    """Statistics for search operations."""
    query: str
    total_candidates: int = 0
    vector_candidates: int = 0
    lexical_candidates: int = 0
    final_results: int = 0
    duration_seconds: float = 0.0
    cache_hit: bool = False

@dataclass
class FrontierState:
    """State for BFS indexing frontier."""
    queue: List[str]  # Directory paths to process
    seen: Dict[str, Tuple[int, int]]  # path -> (device, inode)
    processed_files: int = 0
    processed_dirs: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []

# Type aliases for better readability
SearchResults = List[SearchHit]
ChunkList = List[Chunk]
ScoredChunkList = List[ScoredChunk]
CandidateDict = Dict[str, float]  # chunk_id -> score

# Result types for different operations
SearchResult = Dict[str, Any]  # API response format
IndexResult = Dict[str, Any]   # Indexing operation result
BenchmarkResult = Dict[str, Any]  # Benchmark measurement result
