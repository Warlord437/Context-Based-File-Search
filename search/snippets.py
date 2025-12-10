"""
Snippet generation utilities for search results.
"""

import re
from typing import Tuple, Optional

def make_snippet(chunk_text: str, query: str, radius: int = 50) -> Tuple[str, int, int]:
    """
    Generate a snippet with query highlighted and context.
    
    Args:
        chunk_text: Full text of the chunk
        query: Search query to highlight
        radius: Number of characters around the match to include
    
    Returns:
        Tuple of (snippet, start_pos, end_pos) in original text
    """
    if not chunk_text or not query:
        return chunk_text[:radius * 2], 0, min(radius * 2, len(chunk_text))
    
    # Find the best match position
    match_pos = _find_best_match(chunk_text, query)
    
    if match_pos == -1:
        # No match found, return beginning of text
        snippet = chunk_text[:radius * 2]
        return snippet, 0, min(radius * 2, len(chunk_text))
    
    # Calculate snippet boundaries
    start_pos = max(0, match_pos - radius)
    end_pos = min(len(chunk_text), match_pos + len(query) + radius)
    
    # Extract snippet
    snippet = chunk_text[start_pos:end_pos]
    
    # Add ellipsis if needed
    if start_pos > 0:
        snippet = "..." + snippet
    if end_pos < len(chunk_text):
        snippet = snippet + "..."
    
    return snippet, start_pos, end_pos

def _find_best_match(text: str, query: str) -> int:
    """Find the best match position for the query in text."""
    text_lower = text.lower()
    query_lower = query.lower()
    
    # Try exact phrase match first
    pos = text_lower.find(query_lower)
    if pos != -1:
        return pos
    
    # Try individual word matches
    query_words = query_lower.split()
    if not query_words:
        return -1
    
    # Find the earliest occurrence of any query word
    earliest_pos = len(text)
    for word in query_words:
        pos = text_lower.find(word)
        if pos != -1 and pos < earliest_pos:
            earliest_pos = pos
    
    return earliest_pos if earliest_pos < len(text) else -1

def highlight_query(snippet: str, query: str) -> str:
    """Highlight query terms in the snippet."""
    if not query:
        return snippet
    
    # Split query into words
    query_words = query.lower().split()
    
    # Create pattern to match query words (case insensitive)
    pattern = r'\b(' + '|'.join(re.escape(word) for word in query_words) + r')\b'
    
    # Replace with highlighted version
    def highlight_match(match):
        return f"**{match.group(1)}**"
    
    highlighted = re.sub(pattern, highlight_match, snippet, flags=re.IGNORECASE)
    return highlighted

def truncate_snippet(snippet: str, max_length: int = 200) -> str:
    """Truncate snippet to maximum length."""
    if len(snippet) <= max_length:
        return snippet
    
    # Try to break at word boundary
    truncated = snippet[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.8:  # If we can break at a reasonable word boundary
        truncated = truncated[:last_space]
    
    return truncated + "..."

def clean_snippet(snippet: str) -> str:
    """Clean snippet by removing excessive whitespace."""
    # Replace multiple whitespace with single space
    cleaned = re.sub(r'\s+', ' ', snippet)
    
    # Remove leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned

if __name__ == "__main__":
    # Test snippet generation
    test_text = """
    This is a long document about machine learning and artificial intelligence. 
    The document contains information about neural networks, deep learning, 
    and various algorithms used in AI research. Machine learning has become 
    increasingly important in recent years.
    """
    
    test_query = "machine learning"
    
    snippet, start, end = make_snippet(test_text, test_query, radius=30)
    print(f"Snippet: {snippet}")
    print(f"Position: {start}-{end}")
    
    highlighted = highlight_query(snippet, test_query)
    print(f"Highlighted: {highlighted}")
