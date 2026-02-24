"""
OCR backends: Tesseract (default), PaddleOCR, EasyOCR.
AI models (PaddleOCR, EasyOCR) are faster on GPU and often more accurate on complex images.
"""

import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Lazy-loaded engines (singleton per backend)
_paddleocr_engine = None
_easyocr_reader = None


def _detect_gpu_for_paddle() -> bool:
    """Detect if PaddlePaddle can use GPU (CUDA)."""
    try:
        import paddle
        return paddle.device.is_compiled_with_cuda()
    except Exception:
        return False


def _detect_gpu_for_easyocr() -> bool:
    """Detect if EasyOCR can use GPU (CUDA only; MPS/Apple Silicon has limited support)."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def _tesseract_extract(file_path: str) -> Optional[str]:
    """Extract text using pytesseract (Tesseract OCR)."""
    global _tesseract_fn
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        logger.debug(f"Tesseract dependencies not available: {e}")
        return None

    try:
        img = Image.open(file_path)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img)
        return text.strip() if text else None
    except Exception as e:
        logger.debug(f"Tesseract OCR failed for {file_path}: {e}")
        return None


def _paddleocr_extract(file_path: str) -> Optional[str]:
    """Extract text using PaddleOCR (AI-based, faster on GPU)."""
    global _paddleocr_engine
    try:
        from paddleocr import PaddleOCR
        import numpy as np
        from PIL import Image
    except ImportError as e:
        logger.debug(f"PaddleOCR dependencies not available: {e}")
        return None

    try:
        if _paddleocr_engine is None:
            use_gpu = _detect_gpu_for_paddle()
            logger.info(f"Initializing PaddleOCR (use_gpu={use_gpu})")
            _paddleocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=use_gpu,
                show_log=False,
            )

        img = Image.open(file_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img_np = np.array(img)

        result = _paddleocr_engine.ocr(img_np, cls=True)
        if not result or result[0] is None:
            return None

        # result[0] = [[[bbox], (text, conf)], ...]
        texts = [line[1][0] for line in result[0]]
        return " ".join(texts).strip() or None
    except Exception as e:
        logger.debug(f"PaddleOCR failed for {file_path}: {e}")
        return None


def _easyocr_extract(file_path: str) -> Optional[str]:
    """Extract text using EasyOCR (AI-based, good accuracy)."""
    global _easyocr_reader
    try:
        import easyocr
        from PIL import Image
    except ImportError as e:
        logger.debug(f"EasyOCR dependencies not available: {e}")
        return None

    try:
        if _easyocr_reader is None:
            use_gpu = _detect_gpu_for_easyocr()
            logger.info(f"Initializing EasyOCR (gpu={use_gpu})")
            _easyocr_reader = easyocr.Reader(["en"], gpu=use_gpu)

        img = Image.open(file_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        import numpy as np
        img_np = np.array(img)

        detections = _easyocr_reader.readtext(img_np)
        # Filter by confidence, join text
        text = " ".join(
            t for (_, t, conf) in detections if conf >= 0.5
        ).strip()
        return text or None
    except Exception as e:
        logger.debug(f"EasyOCR failed for {file_path}: {e}")
        return None


def get_ocr_extractor(backend: str) -> Callable[[str], Optional[str]]:
    """
    Return OCR extract function for the given backend.
    Falls back to tesseract if the requested backend is unavailable.
    """
    backend = (backend or "tesseract").lower().strip()
    extractors = {
        "tesseract": _tesseract_extract,
        "paddleocr": _paddleocr_extract,
        "easyocr": _easyocr_extract,
    }
    fn = extractors.get(backend, _tesseract_extract)
    return fn
