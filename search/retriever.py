"""
Hybrid retriever: vector + BM25 + merge & score.
"""

import time
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

from .config import get_config
from .storage import create_storage
from .types import ScoredChunk, ScoreBreakdown, CandidateDict
from .model_loader import get_embedding_model
from .validation import sanitize_fts_query, validate_search_params

logger = logging.getLogger(__name__)

# Query expansion: optional, uses WordNet synonyms when nltk available
_query_expansion_enabled: Optional[bool] = None


def _expand_query_with_synonyms(query: str, max_synonyms_per_word: int = 2) -> str:
    """
    Expand query with WordNet synonyms for better semantic recall.
    Returns original query if WordNet unavailable.
    """
    global _query_expansion_enabled
    if _query_expansion_enabled is False:
        return query

    try:
        import nltk
        from nltk.corpus import wordnet

        # Lazy download of wordnet data
        try:
            wordnet.synsets("test")
        except LookupError:
            try:
                nltk.download("wordnet", quiet=True)
                nltk.download("omw-1.4", quiet=True)
            except Exception:
                _query_expansion_enabled = False
                return query

        _query_expansion_enabled = True
        words = query.split()
        expanded = set(words)

        for word in words:
            if len(word) < 3:
                continue
            for syn in wordnet.synsets(word)[:2]:
                for lemma in syn.lemmas()[:max_synonyms_per_word]:
                    synonym = lemma.name().replace("_", " ")
                    if synonym.lower() != word.lower():
                        expanded.add(synonym)

        result = " ".join(expanded)
        if result != query:
            logger.debug(f"Query expanded: '{query}' -> '{result}'")
        return result

    except ImportError:
        _query_expansion_enabled = False
        return query
    except Exception as e:
        logger.debug(f"Query expansion skipped: {e}")
        return query

class HybridRetriever:
    """Hybrid retrieval combining vector and lexical search."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config()
        self.qdrant, self.catalog = create_storage(self.config)
        self.search_config = self.config["search"]
        
        # Pre-compile patterns for efficiency
        self._punctuation_pattern = re.compile(r'[^\w\s]')
        self._whitespace_pattern = re.compile(r'\s+')
        self._closed = False
    
    def close(self):
        """Close all resources (database connections, etc.)."""
        if self._closed:
            return
        
        try:
            if hasattr(self, 'catalog') and self.catalog:
                self.catalog.close()
            logger.debug("HybridRetriever resources closed")
        except Exception as e:
            logger.warning(f"Error closing HybridRetriever resources: {e}")
        finally:
            self._closed = True
    
    def __enter__(self):
        """Context manager entry - allows 'with HybridRetriever(...)' usage."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically closes resources."""
        self.close()
        return False  # Don't suppress exceptions
    
    def __del__(self):
        """Cleanup on deletion - ensures resources are closed."""
        if not self._closed:
            try:
                self.close()
            except Exception:
                pass  # Ignore errors during cleanup
    
    def embed_query(self, text: str) -> Optional[np.ndarray]:
        """Embed query text using SentenceTransformer (with cached model)."""
        try:
            model = get_embedding_model()
            if model is None:
                return None
            normalize = self.config.get("embedding", {}).get("normalize_embeddings", True)
            embedding = model.encode(
                [text],
                convert_to_tensor=False,
                show_progress_bar=False,
                normalize_embeddings=normalize,
            )
            return embedding[0]
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
            # Sanitize query to prevent FTS5 injection, then clean for search
            safe_query = sanitize_fts_query(query)
            clean_query = self._clean_query(safe_query) if safe_query else ""
            
            if not clean_query:
                return {}
            
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
        """Merge and score candidates from both search methods (weighted or RRF)."""
        merge_strategy = self.search_config.get("merge_strategy", "weighted")
        rrf_k = self.search_config.get("rrf_k", 60)

        weights = weights or {
            "bm25_weight": self.search_config["bm25_weight"],
            "cosine_weight": self.search_config["cosine_weight"]
        }
        boosts = boosts or {
            "exact_boost": self.search_config["exact_boost"],
            "early_pos_boost": self.search_config["early_pos_boost"]
        }

        all_chunk_ids = list(set(vec_candidates.keys()) | set(lex_candidates.keys()))
        if not all_chunk_ids:
            return []

        if merge_strategy == "rrf":
            vec_rank = {cid: r for r, cid in enumerate(sorted(vec_candidates, key=vec_candidates.get, reverse=True), 1)}
            lex_rank = {cid: r for r, cid in enumerate(sorted(lex_candidates, key=lex_candidates.get, reverse=True), 1)}
            vec_scores_norm = {cid: 1.0 / (rrf_k + vec_rank.get(cid, 9999)) for cid in all_chunk_ids}
            lex_scores_norm = {cid: 1.0 / (rrf_k + lex_rank.get(cid, 9999)) for cid in all_chunk_ids}
            rrf_scale = 2.0
        else:
            vec_scores_norm = self._normalize_scores(vec_candidates)
            lex_scores_norm = self._normalize_scores(lex_candidates)
            rrf_scale = 1.0
        
        # Batch fetch all chunk metadata and text (1-2 queries vs N)
        batch_data = self.catalog.chunks_meta_and_text_batch(all_chunk_ids)
        
        scored_chunks = []
        
        for chunk_id in all_chunk_ids:
            # Get normalized scores (0 if not found)
            cosine_score = vec_scores_norm.get(chunk_id, 0.0)
            bm25_score = lex_scores_norm.get(chunk_id, 0.0)
            
            # Get chunk metadata and text from batch
            pair = batch_data.get(chunk_id)
            if not pair:
                continue
            chunk_meta, chunk_text = pair
            if not chunk_meta or not chunk_text:
                continue
            
            # Calculate exact match bonus
            exact_match = self._calculate_exact_match(query, chunk_text)
            
            # Calculate position bonus
            position_bonus = self._calculate_position_bonus(query, chunk_text)
            
            if merge_strategy == "rrf":
                base_score = (vec_scores_norm.get(chunk_id, 0) + lex_scores_norm.get(chunk_id, 0)) / rrf_scale
            else:
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
    
    def search(
        self,
        query: str,
        k: int = None,
        timeout: float = 2.5,
        filters: Optional[Dict[str, Any]] = None,
        expand_query: bool = True,
    ) -> List[ScoredChunk]:
        """
        Perform hybrid search and return top results.

        Args:
            query: Search query string
            k: Max results to return
            timeout: Vector search timeout
            filters: Optional filters - file_ext (list), path_contains (str)
            expand_query: If True, expand query with synonyms for vector search
        """
        # Validate search params
        valid, err = validate_search_params(k=k)
        if not valid and k is not None:
            logger.warning(f"Invalid search param k={k}: {err}")
        k = k or self.search_config["top_k"]
        k = min(max(1, k), 1000)  # Clamp to safe range
        filters = filters or {}

        start_time = time.time()
        max_search_sec = self.search_config.get("max_search_sec", 20.0)

        # Config: expand query (adds latency, disable for speed)
        expand_query = expand_query and self.search_config.get("expand_query", False)
        embed_query_text = _expand_query_with_synonyms(query) if expand_query else query

        # Embed query (with timeout for model load on cold start)
        if time.time() - start_time > max_search_sec:
            logger.warning("Search aborted: exceeded time limit before embedding")
            return []
        query_embedding = self.embed_query(embed_query_text)
        if query_embedding is None:
            logger.error("Failed to embed query")
            return []
        if time.time() - start_time > max_search_sec:
            logger.warning("Search aborted: exceeded time limit after embedding")
            return []

        # Get candidates: run vector in thread (Qdrant), lexical in main (SQLite not thread-safe)
        parallel = self.search_config.get("parallel_search", False)
        if parallel:
            with ThreadPoolExecutor(max_workers=1) as ex:
                vec_future = ex.submit(self.vector_candidates, query_embedding, None, timeout)
                lex_candidates = self.lexical_candidates(query)
                vec_candidates = vec_future.result()
        else:
            vec_candidates = self.vector_candidates(query_embedding, timeout=timeout)
            lex_candidates = self.lexical_candidates(query)

        # Merge and score (RRF or weighted)
        scored_chunks = self.merge_and_score(query, vec_candidates, lex_candidates)

        # Apply filters
        scored_chunks = self._apply_filters(scored_chunks, filters)

        # Deduplicate by file
        deduped_chunks = self.dedupe_by_file(scored_chunks)

        # Take top k results
        results = deduped_chunks[:k]

        elapsed = time.time() - start_time
        if elapsed > max_search_sec:
            logger.warning(f"Search exceeded {max_search_sec}s limit (took {elapsed:.1f}s), returning partial results")
        logger.info(f"Hybrid search completed in {elapsed:.3f}s: {len(results)} results")

        return results

    def _apply_filters(
        self, chunks: List[ScoredChunk], filters: Dict[str, Any]
    ) -> List[ScoredChunk]:
        """Apply search filters to scored chunks."""
        if not filters:
            return chunks

        file_ext = filters.get("file_ext")
        exclude_file_ext = filters.get("exclude_file_ext")
        path_contains = filters.get("path_contains")

        def _norm_ext(x: str) -> str:
            x = x.lower().strip()
            return x if x.startswith(".") else "." + x

        filtered = []
        for chunk in chunks:
            path_lower = chunk.path.lower()

            if file_ext:
                ext_ok = any(path_lower.endswith(_norm_ext(e)) for e in file_ext)
                if not ext_ok:
                    continue

            if exclude_file_ext:
                # Exclude images when searching documents only
                ext_excluded = any(path_lower.endswith(_norm_ext(e)) for e in exclude_file_ext)
                if ext_excluded:
                    continue

            if path_contains and path_contains.lower() not in path_lower:
                continue

            filtered.append(chunk)

        return filtered
    
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
