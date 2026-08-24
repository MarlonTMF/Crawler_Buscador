"""OCR adapter using pytesseract (optional).

Provides a small wrapper to run OCR on images produced by the renderer.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _import_pytesseract():
    try:
        import pytesseract

        return pytesseract
    except Exception as e:
        logger.warning("pytesseract not available: %s", e)
        return None


def image_to_text(image_path: str) -> Optional[str]:
    pytesseract = _import_pytesseract()
    if not pytesseract:
        return None
    try:
        from PIL import Image

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        logger.warning("OCR failed for %s: %s", image_path, e)
        return None
