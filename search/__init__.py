"""
Local-Agent Hybrid Search System

A production-ready hybrid search implementation combining:
- Vector search (Qdrant + SentenceTransformers)
- Lexical search (SQLite FTS5 + BM25)
- Streaming BFS indexing with checkpointing
- Advanced ranking and deduplication
"""

__version__ = "2.0.0"
