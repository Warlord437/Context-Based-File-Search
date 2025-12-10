"""
Constants and utilities for store paths and file management.
"""

from pathlib import Path
from typing import Dict, Any

def get_store_paths(config: Dict[str, Any] = None) -> Dict[str, Path]:
    """Get all store-related paths from config."""
    if config is None:
        from .config import get_config
        config = get_config()
    
    paths = config.get("paths", {})
    store_root = Path(paths.get("store", "store"))
    
    return {
        "store": store_root,
        "catalog": Path(paths.get("catalog", store_root / "catalog.db")),
        "frontier": Path(paths.get("frontier", store_root / "frontier.json")),
        "benchmarks": Path(paths.get("benchmarks", store_root / "runs")),
        "vectors": store_root / "vectors",  # Legacy compatibility
        "cache": store_root / "cache",      # Search result cache
        "logs": store_root / "logs"         # Operation logs
    }

def ensure_store_directories(config: Dict[str, Any] = None) -> Dict[str, Path]:
    """Ensure all store directories exist and return their paths."""
    paths = get_store_paths(config)
    
    # Create directories that don't exist
    for name, path in paths.items():
        if name in ["benchmarks", "vectors", "cache", "logs"]:
            path.mkdir(parents=True, exist_ok=True)
    
    return paths

def get_catalog_path(config: Dict[str, Any] = None) -> Path:
    """Get the catalog database path."""
    paths = get_store_paths(config)
    return paths["catalog"]

def get_frontier_path(config: Dict[str, Any] = None) -> Path:
    """Get the frontier state file path."""
    paths = get_store_paths(config)
    return paths["frontier"]

def get_benchmark_path(config: Dict[str, Any] = None) -> Path:
    """Get the benchmark results directory path."""
    paths = get_store_paths(config)
    return paths["benchmarks"]

def get_cache_path(config: Dict[str, Any] = None) -> Path:
    """Get the cache directory path."""
    paths = get_store_paths(config)
    return paths["cache"]

def get_log_path(config: Dict[str, Any] = None) -> Path:
    """Get the logs directory path."""
    paths = get_store_paths(config)
    return paths["logs"]

# Legacy path compatibility
def get_legacy_store_path(config: Dict[str, Any] = None) -> Path:
    """Get the legacy store path for compatibility."""
    paths = get_store_paths(config)
    return paths["vectors"]

# Path validation utilities
def is_valid_store_path(path: Path) -> bool:
    """Check if a path is a valid store location."""
    try:
        # Check if path exists and is writable
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        
        # Test write access
        test_file = path / ".test_write"
        test_file.touch()
        test_file.unlink()
        
        return True
    except (OSError, PermissionError):
        return False

def get_relative_store_path(absolute_path: Path, store_root: Path) -> str:
    """Convert absolute path to relative path from store root."""
    try:
        return str(absolute_path.relative_to(store_root))
    except ValueError:
        # Path is not under store root, return as-is
        return str(absolute_path)

def get_absolute_store_path(relative_path: str, store_root: Path) -> Path:
    """Convert relative path to absolute path under store root."""
    if Path(relative_path).is_absolute():
        return Path(relative_path)
    return store_root / relative_path

# File extension utilities
def get_file_extension(path: str) -> str:
    """Get file extension in lowercase."""
    return Path(path).suffix.lower()

def is_allowed_extension(path: str, allowed_exts: list) -> bool:
    """Check if file extension is in allowed list."""
    ext = get_file_extension(path)
    return ext in allowed_exts

# Path sanitization
def sanitize_path(path: str) -> str:
    """Sanitize path for safe storage."""
    # Remove any dangerous characters
    import re
    sanitized = re.sub(r'[<>:"|?*]', '_', path)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    return sanitized

def normalize_path(path: str) -> str:
    """Normalize path for consistent storage."""
    return str(Path(path).resolve())

if __name__ == "__main__":
    # Test the path utilities
    from .config import get_config
    
    config = get_config()
    paths = ensure_store_directories(config)
    
    print("Store paths:")
    for name, path in paths.items():
        print(f"  {name}: {path}")
        print(f"    exists: {path.exists()}")
        if path.is_file():
            print(f"    size: {path.stat().st_size} bytes")
        elif path.is_dir():
            print(f"    writable: {is_valid_store_path(path)}")
