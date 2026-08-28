"""OCR adapter using pytesseract (optional).

Provides a small wrapper to run OCR on images produced by the renderer.
"""
from typing import Optional
import logging
import os
import shutil

logger = logging.getLogger(__name__)


def _ensure_tesseract_available():
    try:
        import pytesseract
    except Exception as e:
        logger.warning("pytesseract not available: %s", e)
        return None

    existing = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
    if existing and os.path.exists(existing):
        return pytesseract

    resolved = shutil.which("tesseract")
    if resolved and os.path.exists(resolved):
        pytesseract.pytesseract.tesseract_cmd = resolved
        return pytesseract

    candidates = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Tesseract-OCR", "tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            tesseract_dir = os.path.dirname(candidate)
            if tesseract_dir not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = tesseract_dir + os.pathsep + os.environ.get("PATH", "")
            return pytesseract

    logger.warning("Tesseract executable not found in PATH or standard install directories")
    return None


def image_to_text(image_path: str) -> Optional[str]:
    pytesseract = _ensure_tesseract_available()
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
