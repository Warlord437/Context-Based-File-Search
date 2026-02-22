"""
Hybrid retriever: vector + BM25 + merge & score.
"""

import time
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from .config import get_config
from .storage import create_storage
from .types import ScoredChunk, ScoreBreakdown, CandidateDict

logger = logging.getLogger(__name__)

class HybridRetriever:
    """Hybrid retrieval combining vector and lexical search."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config()
        self.qdrant, self.catalog = create_storage(self.config)
        self.search_config = self.config["search"]
        
        # Pre-compile patterns for efficiency
        self._punctuation_pattern = re.compile(r'[^\w\s]')
        self._whitespace_pattern = re.compile(r'\s+')
    
    def embed_query(self, text: str) -> Optional[np.ndarray]:
        """Embed query text using SentenceTransformer."""
        try:
            from sentence_transformers import SentenceTransformer
            import torch
            
            # Load model (with MPS support if available)
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
            
            # Generate embedding
            embedding = model.encode([text], convert_to_tensor=False)
            return embedding[0]
            
        except ImportError:
            logger.error("sentence-transformers not available")
            return None
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return None
    
    def vector_candidates(self, query_embedding: np.ndarray, vec_k: int = None, timeout: float = 2.5) -> CandidateDict:
        """Get vector similarity candidates from Qdrant."""
        vec_k = vec_k or self.search_config["vec_k"]
        
        try:
            # Search Qdrant
            hits = self.qdrant.vector_search(
                embedding=query_embedding.tolist(),
                limit=vec_k,
                timeout=timeout
            )
            
            # Convert to candidate dict
            candidates = {}
            for hit in hits:
                chunk_id = hit["chunk_id"]
                score = hit["score"]
                candidates[chunk_id] = score
            
            logger.debug(f"Vector search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return {}
    
    def lexical_candidates(self, query: str, lex_k: int = None) -> CandidateDict:
        """Get BM25 lexical candidates from FTS5."""
        lex_k = lex_k or self.search_config["lex_k"]
        
        try:
            # Clean and prepare query
            clean_query = self._clean_query(query)
            
            # Search FTS5
            results = self.catalog.fts_search(clean_query, lex_k)
            
            # Convert to candidate dict with normalized scores
            candidates = {}
            for chunk_id, bm25_score in results:
                candidates[chunk_id] = bm25_score
            
            logger.debug(f"Lexical search returned {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Lexical search failed: {e}")
            return {}
    
    def merge_and_score(self, query: str, vec_candidates: CandidateDict, lex_candidates: CandidateDict, 
                       weights: Dict[str, float] = None, boosts: Dict[str, float] = None) -> List[ScoredChunk]:
        """Merge and score candidates from both search methods."""
        
        # Default weights and boosts
        weights = weights or {
            "bm25_weight": self.search_config["bm25_weight"],
            "cosine_weight": self.search_config["cosine_weight"]
        }
        
        boosts = boosts or {
            "exact_boost": self.search_config["exact_boost"],
            "early_pos_boost": self.search_config["early_pos_boost"]
        }
        
        # Get all unique chunk IDs
        all_chunk_ids = set(vec_candidates.keys()) | set(lex_candidates.keys())
        
        if not all_chunk_ids:
            return []
        
        # Normalize scores to [0, 1] range
        vec_scores_norm = self._normalize_scores(vec_candidates)
        lex_scores_norm = self._normalize_scores(lex_candidates)
        
        scored_chunks = []
        
        for chunk_id in all_chunk_ids:
            # Get normalized scores (0 if not found)
            cosine_score = vec_scores_norm.get(chunk_id, 0.0)
            bm25_score = lex_scores_norm.get(chunk_id, 0.0)
            
            # Get chunk metadata and text
            chunk_meta = self.catalog.chunk_meta(chunk_id)
            chunk_text = self.catalog.get_chunk_text(chunk_id)
            
            if not chunk_meta or not chunk_text:
                continue
            
            # Calculate exact match bonus
            exact_match = self._calculate_exact_match(query, chunk_text)
            
            # Calculate position bonus
            position_bonus = self._calculate_position_bonus(query, chunk_text)
            
            # Calculate final score
            base_score = (weights["bm25_weight"] * bm25_score + 
                         weights["cosine_weight"] * cosine_score)
            
            final_score = (base_score + 
                          boosts["exact_boost"] * exact_match + 
                          boosts["early_pos_boost"] * position_bonus)
            
            # Create score breakdown
            score_breakdown = ScoreBreakdown(
                cosine=cosine_score,
                bm25=bm25_score,
                exact=exact_match,
                position_bonus=position_bonus,
                final=final_score
            )
            
            # Create scored chunk
            scored_chunk = ScoredChunk(
                chunk_id=chunk_id,
                file_id=chunk_meta["file_id"],
                path=chunk_meta["path"],
                text=chunk_text,
                score=final_score,
                score_breakdown=score_breakdown,
                chunk_idx=chunk_meta["idx"]
            )
            
            scored_chunks.append(scored_chunk)
        
        # Sort by final score (descending)
        scored_chunks.sort(key=lambda x: x.score, reverse=True)
        
        # Limit to merge_k
        merge_k = self.search_config["merge_k"]
        return scored_chunks[:merge_k]
    
    def dedupe_by_file(self, scored_chunks: List[ScoredChunk], max_results_per_file: int = 1) -> List[ScoredChunk]:
        """Deduplicate by file, keeping best chunks per file."""
        file_best = {}
        
        for chunk in scored_chunks:
            file_id = chunk.file_id
            
            if file_id not in file_best:
                file_best[file_id] = []
            
            file_best[file_id].append(chunk)
        
        # Keep best chunks per file
        deduped = []
        for file_id, chunks in file_best.items():
            # Sort by score and take best ones
            chunks.sort(key=lambda x: x.score, reverse=True)
            deduped.extend(chunks[:max_results_per_file])
        
        # Sort final results by score
        deduped.sort(key=lambda x: x.score, reverse=True)
        
        return deduped
    
    def search(self, query: str, k: int = None, timeout: float = 2.5) -> List[ScoredChunk]:
        """Perform hybrid search and return top results."""
        k = k or self.search_config["top_k"]
        
        start_time = time.time()
        
        # Embed query
        query_embedding = self.embed_query(query)
        if query_embedding is None:
            logger.error("Failed to embed query")
            return []
        
        # Get candidates from both methods
        vec_candidates = self.vector_candidates(query_embedding, timeout=timeout)
        lex_candidates = self.lexical_candidates(query)
        
        # Merge and score
        scored_chunks = self.merge_and_score(query, vec_candidates, lex_candidates)
        
        # Deduplicate by file
        deduped_chunks = self.dedupe_by_file(scored_chunks)
        
        # Take top k results
        results = deduped_chunks[:k]
        
        elapsed = time.time() - start_time
        logger.info(f"Hybrid search completed in {elapsed:.3f}s: {len(results)} results")
        
        return results
    
    def _clean_query(self, query: str) -> str:
        """Clean query for FTS5 search."""
        # Remove punctuation and normalize whitespace
        clean = self._punctuation_pattern.sub(' ', query.lower())
        clean = self._whitespace_pattern.sub(' ', clean).strip()
        return clean
    
    def _normalize_scores(self, candidates: CandidateDict) -> CandidateDict:
        """Normalize scores to [0, 1] range using min-max normalization."""
        if not candidates:
            return {}
        
        scores = list(candidates.values())
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            # All scores are the same, return as-is
            return candidates
        
        normalized = {}
        for chunk_id, score in candidates.items():
            normalized[chunk_id] = (score - min_score) / (max_score - min_score)
        
        return normalized
    
    def _calculate_exact_match(self, query: str, text: str) -> float:
        """Calculate exact match bonus (0.0 to 1.0)."""
        query_lower = query.lower().strip()
        text_lower = text.lower()
        
        # Exact phrase match
        if query_lower in text_lower:
            return 1.0
        
        # Individual word matches
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        
        if not query_words:
            return 0.0
        
        word_matches = len(query_words & text_words)
        word_ratio = word_matches / len(query_words)
        
        # Boost if most words match
        if word_ratio >= 0.7:
            return word_ratio
        
        return 0.0
    
    def _calculate_position_bonus(self, query: str, text: str) -> float:
        """Calculate early position bonus (0.0 to 1.0)."""
        query_lower = query.lower().strip()
        text_lower = text.lower()
        
        # Find first occurrence of query
        pos = text_lower.find(query_lower)
        if pos == -1:
            return 0.0
        
        # Calculate position as ratio of text length
        position_ratio = pos / len(text_lower)
        
        # Bonus if found in first 30% of text
        if position_ratio <= 0.3:
            return 1.0 - position_ratio
        
        return 0.0


def create_retriever(config: Dict[str, Any] = None) -> HybridRetriever:
    """Create and initialize hybrid retriever."""
    return HybridRetriever(config)


if __name__ == "__main__":
    # Test the retriever
    retriever = create_retriever()
    
    query = "test query"
    print(f"Testing hybrid retriever with query: '{query}'")
    
    results = retriever.search(query, k=5)
    
    print(f"Found {len(results)} results:")
    for i, chunk in enumerate(results, 1):
        print(f"{i}. {chunk.path} (score: {chunk.score:.3f})")
        print(f"   Cosine: {chunk.score_breakdown.cosine:.3f}, "
              f"BM25: {chunk.score_breakdown.bm25:.3f}, "
              f"Exact: {chunk.score_breakdown.exact:.3f}")
        print(f"   Text: {chunk.text[:100]}...")
        print()
