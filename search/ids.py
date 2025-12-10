"""
Utility functions for generating stable IDs for files and chunks.
"""

import hashlib
from pathlib import Path
from typing import Optional

def file_id(path: str, mtime: int, size: int) -> str:
    """Generate stable file ID based on path, modification time, and size."""
    content = f"{path}|{mtime}|{size}"
    return hashlib.sha1(content.encode()).hexdigest()

def chunk_id(file_id: str, idx: int) -> str:
    """Generate chunk ID from file ID and chunk index."""
    import uuid
    
    # Generate a deterministic UUID based on file_id and chunk index
    # This ensures uniqueness while being Qdrant-compatible
    content = f"{file_id}_{idx}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content))

def generate_file_sha256(path: str) -> Optional[str]:
    """Generate SHA256 hash of file content."""
    try:
        import hashlib
        
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
        
    except (OSError, IOError) as e:
        print(f"Error reading file {path}: {e}")
        return None

def get_file_stats(path: str) -> Optional[dict]:
    """Get file statistics for ID generation."""
    try:
        path_obj = Path(path)
        if not path_obj.exists():
            return None
        
        stat = path_obj.stat()
        return {
            "size": stat.st_size,
            "mtime": int(stat.st_mtime)
        }
        
    except (OSError, IOError) as e:
        print(f"Error getting stats for {path}: {e}")
        return None

def is_file_unchanged(path: str, expected_sha256: str) -> bool:
    """Check if file content has changed by comparing SHA256."""
    current_sha256 = generate_file_sha256(path)
    return current_sha256 == expected_sha256

def normalize_path(path: str) -> str:
    """Normalize path for consistent ID generation."""
    return str(Path(path).resolve())

if __name__ == "__main__":
    # Test ID generation
    test_path = "/Users/tathagatasaha/Desktop/localagentandcliwithvectordb/README.md"
    
    stats = get_file_stats(test_path)
    if stats:
        fid = file_id(test_path, stats["mtime"], stats["size"])
        cid = chunk_id(fid, 0)
        
        print(f"File: {test_path}")
        print(f"File ID: {fid}")
        print(f"Chunk ID: {cid}")
        
        sha256 = generate_file_sha256(test_path)
        print(f"SHA256: {sha256[:16]}..." if sha256 else "SHA256: Failed")
