"""
Central configuration loader with sane defaults and environment overlay.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

DEFAULT = {
    "index": {
        "max_tokens": 1200,
        "overlap": 80,
        "embed_batch": 1024,
        "upsert_batch": 4000,
        "allow_exts": [".txt", ".md", ".pdf", ".docx", ".html", ".htm", ".rtf"],
        "ocr_enabled": False,
        "max_pdf_pages": 50,
        "extraction_timeout": 10,
        "exclude_patterns": [
            "**/node_modules/**",
            "**/.git/**", 
            "**/__pycache__/**",
            "**/.venv/**",
            "**/venv/**",
            "**/Library/**",
            "**/System/**",
            "**/Applications/**",
            "**/usr/**",
            "**/var/**",
            "**/tmp/**",
            "**/.cache/**",
            "**/.Trash/**",
            "**/.*/**"
        ]
    },
    "search": {
        "top_k": 50,
        "lex_k": 200,
        "vec_k": 300,
        "merge_k": 400,
        "timeout_sec": 2.5,
        "bm25_weight": 0.55,
        "cosine_weight": 0.45,
        "exact_boost": 0.20,
        "early_pos_boost": 0.10,
        "cache_size": 128,
        "snippet_radius": 50,
        "max_results_per_file": 1
    },
    "qdrant": {
        "url": "http://localhost:6333",
        "prefer_grpc": True,
        "collection": "local_agent_vectors",
        "dim": 384,
        "hnsw_config": {"m": 32, "ef_construct": 256},
        "optimizers_config": {"default_segment_number": 4}
    },
    "paths": {
        "store": "store",
        "catalog": "store/catalog.db",
        "frontier": "store/frontier.json",
        "benchmarks": "store/runs"
    }
}

def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from file and environment variables."""
    
    # Start with defaults
    config = DEFAULT.copy()
    
    # Load from YAML file if exists
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config = _deep_merge(config, file_config)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
    
    # Override with environment variables
    config = _apply_env_overrides(config)
    
    # Ensure paths are absolute
    config = _resolve_paths(config)
    
    return config

def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge dictionaries."""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result

def _apply_env_overrides(config: Dict) -> Dict:
    """Apply environment variable overrides."""
    
    # Index settings
    if os.getenv("LA_INDEX_MAX_TOKENS"):
        config["index"]["max_tokens"] = int(os.getenv("LA_INDEX_MAX_TOKENS"))
    if os.getenv("LA_INDEX_OCR_ENABLED"):
        config["index"]["ocr_enabled"] = os.getenv("LA_INDEX_OCR_ENABLED").lower() == "true"
    
    # Search settings
    if os.getenv("LA_SEARCH_TIMEOUT"):
        config["search"]["timeout_sec"] = float(os.getenv("LA_SEARCH_TIMEOUT"))
    if os.getenv("LA_SEARCH_BM25_WEIGHT"):
        config["search"]["bm25_weight"] = float(os.getenv("LA_SEARCH_BM25_WEIGHT"))
    if os.getenv("LA_SEARCH_COSINE_WEIGHT"):
        config["search"]["cosine_weight"] = float(os.getenv("LA_SEARCH_COSINE_WEIGHT"))
    
    # Qdrant settings
    if os.getenv("LA_QDRANT_URL"):
        config["qdrant"]["url"] = os.getenv("LA_QDRANT_URL")
    if os.getenv("LA_QDRANT_COLLECTION"):
        config["qdrant"]["collection"] = os.getenv("LA_QDRANT_COLLECTION")
    
    # Path settings
    if os.getenv("LA_STORE_PATH"):
        config["paths"]["store"] = os.getenv("LA_STORE_PATH")
    
    return config

def _resolve_paths(config: Dict) -> Dict:
    """Resolve relative paths to absolute paths."""
    store_path = Path(config["paths"]["store"]).resolve()
    
    config["paths"]["store"] = str(store_path)
    config["paths"]["catalog"] = str(store_path / "catalog.db")
    config["paths"]["frontier"] = str(store_path / "frontier.json")
    config["paths"]["benchmarks"] = str(store_path / "runs")
    
    return config

def get_config(config_path: str = None) -> Dict[str, Any]:
    """Get the current configuration."""
    return load_config(config_path)

def validate_config(config: Dict) -> bool:
    """Validate configuration values."""
    try:
        # Validate search weights sum to reasonable range
        bm25_weight = config["search"]["bm25_weight"]
        cosine_weight = config["search"]["cosine_weight"]
        
        if not (0 <= bm25_weight <= 1 and 0 <= cosine_weight <= 1):
            logger.error("Search weights must be between 0 and 1")
            return False
        
        # Validate timeout is positive
        if config["search"]["timeout_sec"] <= 0:
            logger.error("Search timeout must be positive")
            return False
        
        # Validate batch sizes are positive
        if config["index"]["embed_batch"] <= 0 or config["index"]["upsert_batch"] <= 0:
            logger.error("Batch sizes must be positive")
            return False
        
        return True
        
    except KeyError as e:
        logger.error(f"Missing required config key: {e}")
        return False
    except Exception as e:
        logger.error(f"Config validation error: {e}")
        return False

if __name__ == "__main__":
    # Test the config loader
    config = get_config()
    print("Configuration loaded successfully:")
    print(f"Search timeout: {config['search']['timeout_sec']}s")
    print(f"BM25 weight: {config['search']['bm25_weight']}")
    print(f"Cosine weight: {config['search']['cosine_weight']}")
    print(f"Catalog path: {config['paths']['catalog']}")
    print(f"Qdrant URL: {config['qdrant']['url']}")
