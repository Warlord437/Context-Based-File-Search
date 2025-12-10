"""
Public API for hybrid search with pagination and caching.
"""

import time
import hashlib
import logging
from functools import lru_cache
from typing import Dict, Any, List, Optional

from .config import get_config
from .retriever import create_retriever
from .types import SearchHit, SearchOptions
from .snippets import make_snippet, highlight_query, truncate_snippet, clean_snippet

logger = logging.getLogger(__name__)

class SearchAPI:
    """Public search API with caching and pagination."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config()
        self.retriever = create_retriever(self.config)
        self.search_config = self.config["search"]
        
        # Initialize cache
        self._cache = {}
        self._cache_max_size = self.search_config["cache_size"]
        self._cache_ttl = 3600  # 1 hour TTL
    
    def run(self, query: str, k: int = None, page: int = 1, per_page: int = 10, 
            opts: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Main search API function.
        
        Args:
            query: Search query string
            k: Maximum number of results (overrides per_page)
            page: Page number (1-based)
            per_page: Results per page
            opts: Search options (exact_match, case_sensitive, etc.)
        
        Returns:
            Dict with search results, pagination info, and metadata
        """
        start_time = time.time()
        
        # Default values
        k = k or self.search_config["top_k"]
        opts = opts or {}
        
        # Prepare search options
        search_opts = SearchOptions(
            exact_match=opts.get("exact_match", False),
            case_sensitive=opts.get("case_sensitive", False),
            max_results_per_file=opts.get("max_results_per_file", self.search_config["max_results_per_file"]),
            include_snippets=opts.get("include_snippets", True),
            snippet_radius=opts.get("snippet_radius", self.search_config["snippet_radius"])
        )
        
        # Check cache
        cache_key = self._generate_cache_key(query, k, page, per_page, opts)
        cached_result = self._get_cached_result(cache_key)
        
        if cached_result:
            logger.debug(f"Cache hit for query: {query}")
            cached_result["cache_hit"] = True
            return cached_result
        
        # Perform search
        try:
            scored_chunks = self.retriever.search(
                query=query,
                k=k,
                timeout=self.search_config["timeout_sec"]
            )
            
            # Apply search options
            if search_opts.max_results_per_file > 0:
                scored_chunks = self.retriever.dedupe_by_file(
                    scored_chunks, 
                    max_results_per_file=search_opts.max_results_per_file
                )
            
            # Generate search hits with snippets
            search_hits = []
            for chunk in scored_chunks:
                hit = self._create_search_hit(chunk, query, search_opts)
                search_hits.append(hit)
            
            # Apply pagination
            total_hits = len(search_hits)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_hits = search_hits[start_idx:end_idx]
            
            # Calculate pagination info
            total_pages = (total_hits + per_page - 1) // per_page
            has_next = page < total_pages
            has_prev = page > 1
            
            # Build result
            result = {
                "query": query,
                "total_hits": total_hits,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
                "items": paginated_hits,
                "search_time": time.time() - start_time,
                "cache_hit": False,
                "timestamp": int(time.time())
            }
            
            # Cache result
            self._cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return {
                "query": query,
                "total_hits": 0,
                "page": page,
                "per_page": per_page,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False,
                "items": [],
                "search_time": time.time() - start_time,
                "cache_hit": False,
                "error": str(e),
                "timestamp": int(time.time())
            }
    
    def _create_search_hit(self, chunk, query: str, opts: SearchOptions) -> SearchHit:
        """Create a SearchHit from a ScoredChunk."""
        
        # Generate snippet if requested
        snippet = ""
        context_range = (0, 0)
        
        if opts.include_snippets:
            snippet, start_pos, end_pos = make_snippet(
                chunk.text, 
                query, 
                radius=opts.snippet_radius
            )
            snippet = clean_snippet(snippet)
            snippet = truncate_snippet(snippet, max_length=200)
            context_range = (start_pos, end_pos)
            
            # Highlight query terms if not exact match mode
            if not opts.exact_match:
                snippet = highlight_query(snippet, query)
        
        # Determine file type
        file_type = "unknown"
        if chunk.path:
            if chunk.path.endswith(('.md', '.markdown')):
                file_type = "markdown"
            elif chunk.path.endswith('.pdf'):
                file_type = "pdf"
            elif chunk.path.endswith(('.txt', '.text')):
                file_type = "text"
            elif chunk.path.endswith(('.html', '.htm')):
                file_type = "html"
            elif chunk.path.endswith(('.docx', '.doc')):
                file_type = "document"
        
        return SearchHit(
            path=chunk.path,
            score=chunk.score,
            score_breakdown=chunk.score_breakdown,
            file_type=file_type,
            chunk_id=chunk.chunk_id,
            snippet=snippet,
            context_range=context_range,
            file_id=chunk.file_id,
            chunk_idx=chunk.chunk_idx
        )
    
    def _generate_cache_key(self, query: str, k: int, page: int, per_page: int, opts: Dict[str, Any]) -> str:
        """Generate cache key for query and parameters."""
        # Create a deterministic hash of all parameters
        key_data = {
            "query": query,
            "k": k,
            "page": page,
            "per_page": per_page,
            "opts": sorted(opts.items()) if opts else {}
        }
        
        key_string = str(key_data)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if valid."""
        if cache_key not in self._cache:
            return None
        
        cache_entry = self._cache[cache_key]
        
        # Check TTL
        if time.time() - cache_entry["timestamp"] > self._cache_ttl:
            del self._cache[cache_key]
            return None
        
        return cache_entry["result"]
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """Cache search result."""
        # Simple LRU eviction
        if len(self._cache) >= self._cache_max_size:
            # Remove oldest entry
            oldest_key = min(self._cache.keys(), 
                           key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]
        
        self._cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }
    
    def clear_cache(self):
        """Clear search cache."""
        self._cache.clear()
        logger.info("Search cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_max_size": self._cache_max_size,
            "cache_ttl": self._cache_ttl
        }


# Global API instance
_api_instance = None

def get_api(config: Dict[str, Any] = None) -> SearchAPI:
    """Get or create global API instance."""
    global _api_instance
    if _api_instance is None:
        _api_instance = SearchAPI(config)
    return _api_instance

def run(query: str, k: int = None, page: int = 1, per_page: int = 10, 
        opts: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Convenience function for search API.
    
    This is the main entry point for the search system.
    """
    api = get_api()
    return api.run(query, k, page, per_page, opts)


if __name__ == "__main__":
    # Test the API
    api = SearchAPI()
    
    # Test search
    result = api.run("local agent", k=5, page=1, per_page=3)
    
    print(f"Query: {result['query']}")
    print(f"Total hits: {result['total_hits']}")
    print(f"Page: {result['page']}/{result['total_pages']}")
    print(f"Search time: {result['search_time']:.3f}s")
    print(f"Cache hit: {result['cache_hit']}")
    print()
    
    for i, hit in enumerate(result["items"], 1):
        print(f"{i}. {hit.path} (score: {hit.score:.3f})")
        print(f"   {hit.file_type} | {hit.snippet}")
        print()
