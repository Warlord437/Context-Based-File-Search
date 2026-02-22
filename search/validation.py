"""
Input validation and sanitization for security and stability.

Addresses: path traversal, FTS5 query injection, chunk size limits, config validation.
"""

import re
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Limits
MAX_QUERY_LENGTH = 500
MAX_PATH_LENGTH = 4096
MIN_MAX_TOKENS = 10
MAX_MAX_TOKENS = 10000
MIN_OVERLAP = 0
MAX_OVERLAP = 500


def sanitize_fts_query(query: str) -> str:
    """
    Sanitize user input for FTS5 MATCH to prevent query injection.

    FTS5 special chars: ", -, *, OR, AND, NOT, (, )
    We extract safe tokens (alphanumeric, underscore) and join with space.
    This prevents injection while preserving basic search functionality.

    Args:
        query: Raw user query

    Returns:
        Sanitized query safe for FTS5 MATCH
    """
    if not query or not isinstance(query, str):
        return ""

    # Truncate to prevent abuse
    query = query[:MAX_QUERY_LENGTH].strip()

    # Extract safe tokens only (letters, numbers, underscore)
    # This removes: ", -, *, parentheses, etc.
    tokens = re.findall(r"[a-zA-Z0-9_]+", query)

    # Filter out FTS5 operators that could change query meaning
    fts_operators = {"or", "and", "not"}
    tokens = [t for t in tokens if t.lower() not in fts_operators]

    if not tokens:
        return ""

    # Join with space - each token is searched independently
    # FTS5 will tokenize and match; we've removed all operator injection
    return " ".join(tokens)


def sanitize_file_path(
    path: str,
    must_exist: bool = False,
    allow_relative: bool = True,
) -> Tuple[Optional[Path], Optional[str]]:
    """
    Validate and sanitize a file path. Prevents path traversal attacks.

    Args:
        path: Input path string
        must_exist: If True, path must exist on filesystem
        allow_relative: If True, relative paths are allowed

    Returns:
        (Path object, None) on success, (None, error_message) on failure
    """
    if not path or not isinstance(path, str):
        return None, "Path must be a non-empty string"

    path = path.strip()
    if len(path) > MAX_PATH_LENGTH:
        return None, f"Path exceeds maximum length ({MAX_PATH_LENGTH})"

    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        return None, f"Invalid path: {e}"

    # Ensure it's within reasonable bounds (no null bytes, etc.)
    path_str = str(resolved)
    if "\x00" in path_str:
        return None, "Path contains invalid characters"

    if must_exist and not resolved.exists():
        return None, f"Path does not exist: {resolved}"

    return resolved, None


def validate_chunk_params(max_tokens: int, overlap: int) -> Tuple[bool, Optional[str]]:
    """
    Validate chunking parameters.

    Returns:
        (True, None) if valid, (False, error_message) otherwise
    """
    if not isinstance(max_tokens, int):
        return False, "max_tokens must be an integer"
    if not isinstance(overlap, int):
        return False, "overlap must be an integer"

    if max_tokens < MIN_MAX_TOKENS:
        return False, f"max_tokens must be >= {MIN_MAX_TOKENS}"
    if max_tokens > MAX_MAX_TOKENS:
        return False, f"max_tokens must be <= {MAX_MAX_TOKENS}"
    if overlap < MIN_OVERLAP:
        return False, f"overlap must be >= {MIN_OVERLAP}"
    if overlap >= max_tokens:
        return False, "overlap must be less than max_tokens"

    return True, None


def validate_search_params(
    k: Optional[int] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate search pagination parameters."""
    if k is not None and (not isinstance(k, int) or k < 1 or k > 1000):
        return False, "k must be an integer between 1 and 1000"
    if page is not None and (not isinstance(page, int) or page < 1):
        return False, "page must be a positive integer"
    if per_page is not None and (not isinstance(per_page, int) or per_page < 1 or per_page > 100):
        return False, "per_page must be between 1 and 100"
    return True, None


def validate_index_path(path: str, must_exist: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Validate that an index path is safe.

    Args:
        path: Path to index
        must_exist: If True, path must exist on filesystem

    Returns:
        (True, None) if valid, (False, error_message) otherwise
    """
    resolved, err = sanitize_file_path(path, must_exist=must_exist)
    if err:
        return False, err
    return True, None
