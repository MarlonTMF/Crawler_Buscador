"""PDF metadata and text extraction with optional pdfplumber/OCR fallback hooks."""

import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PdfExtractionResult:
    text: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    used_ocr: bool = False


class PdfTextExtractor:
    """Extracts metadata/text from PDFs without making pdfplumber mandatory."""

    def extract(self, content_bytes: bytes, enable_ocr: bool = False) -> PdfExtractionResult:
        result = PdfExtractionResult(metadata=self._extract_raw_metadata(content_bytes))

        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content_bytes)) as pdf:
                result.metadata.update({str(k): str(v) for k, v in (pdf.metadata or {}).items() if v is not None})
                result.text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as exc:
            logger.info("pdfplumber extraction unavailable or failed: %s", exc)

        if not result.text and enable_ocr:
            logger.warning("OCR requested but no OCR dependency is configured in this lightweight build.")
            result.used_ocr = False

        return result

    @staticmethod
    def _extract_raw_metadata(content_bytes: bytes) -> Dict[str, str]:
        head = content_bytes[: min(len(content_bytes), 200000)].decode("latin-1", errors="ignore")
        metadata = {}
        for key in ("Title", "Author", "CreationDate", "ModDate"):
            match = re.search(rf"/{key}\s*\((.*?)\)", head)
            if match:
                metadata[key] = match.group(1)
        return metadata
