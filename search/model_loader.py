"""
Shared model loader with caching for SentenceTransformer.

This module provides a singleton pattern for loading and caching
the SentenceTransformer model to avoid reloading on every operation.
"""

import logging
from typing import Optional
import threading

logger = logging.getLogger(__name__)

# Module-level cache for the model
_model_cache: Optional[object] = None
_model_lock = threading.Lock()
_model_device: Optional[str] = None
_model_name: Optional[str] = None


def _get_model_name_from_config() -> str:
    """Get model name from config, with fallback to default."""
    try:
        from .config import get_config
        config = get_config()
        model = config.get("embedding", {}).get("model", "sentence-transformers/all-MiniLM-L6-v2")
        if model and "/" not in model:
            return f"sentence-transformers/{model}"
        return model or "sentence-transformers/all-MiniLM-L6-v2"
    except Exception:
        return "sentence-transformers/all-MiniLM-L6-v2"


def get_embedding_model(device: Optional[str] = None, model_name: Optional[str] = None):
    """
    Get or create the SentenceTransformer model instance.
    
    Uses singleton pattern to cache the model and avoid reloading.
    Model name is read from config.embedding.model when not provided.
    
    Args:
        device: Device to load model on ('mps', 'cuda', 'cpu', or None for auto-detect)
        model_name: Name of the model to load (None = use config)
    
    Returns:
        SentenceTransformer model instance, or None if import fails
    """
    global _model_cache, _model_device, _model_name
    
    if model_name is None:
        model_name = _get_model_name_from_config()
    
    try:
        from sentence_transformers import SentenceTransformer
        import torch
    except ImportError:
        logger.error("sentence-transformers not available")
        return None
    
    # Auto-detect device if not provided
    if device is None:
        if torch.backends.mps.is_available():
            device = 'mps'
        elif torch.cuda.is_available():
            device = 'cuda'
        else:
            device = 'cpu'
    
    # Check if we have a cached model for the same device and model
    with _model_lock:
        if _model_cache is not None and _model_device == device and _model_name == model_name:
            logger.debug(f"Reusing cached model '{model_name}' on device: {device}")
            return _model_cache
        
        # Load model (first time or device/model changed)
        use_onnx = False
        try:
            from .config import get_config
            use_onnx = get_config().get("embedding", {}).get("use_onnx", False)
        except Exception:
            pass

        logger.info(f"Loading SentenceTransformer model '{model_name}' on device: {device}" + (" (ONNX)" if use_onnx else ""))
        try:
            if use_onnx:
                try:
                    _model_cache = SentenceTransformer(model_name, backend="onnx", device=device)
                except (ImportError, TypeError, ValueError) as e:
                    logger.warning(f"ONNX backend failed ({e}), falling back to PyTorch")
                    _model_cache = SentenceTransformer(model_name, device=device)
            else:
                _model_cache = SentenceTransformer(model_name, device=device)
            _model_device = device
            _model_name = model_name
            logger.info(f"Model loaded successfully on {device}")
            return _model_cache
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return None


def clear_model_cache():
    """Clear the cached model (useful for testing or memory management)."""
    global _model_cache, _model_device, _model_name
    with _model_lock:
        _model_cache = None
        _model_device = None
        _model_name = None
        logger.info("Model cache cleared")


def encode_text(texts, model_name: str = 'all-MiniLM-L6-v2', device: Optional[str] = None, 
                convert_to_tensor: bool = False):
    """
    Convenience function to encode text(s) using cached model.
    
    Args:
        texts: Single string or list of strings to encode
        model_name: Name of the model to use
        device: Device to use (None for auto-detect)
        convert_to_tensor: Whether to return tensors or numpy arrays
    
    Returns:
        Embeddings as numpy array or tensor
    """
    model = get_embedding_model(device=device, model_name=model_name)
    if model is None:
        return None
    
    # Ensure texts is a list
    if isinstance(texts, str):
        texts = [texts]
    
    return model.encode(texts, convert_to_tensor=convert_to_tensor)
