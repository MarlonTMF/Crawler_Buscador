"""Real document-content extraction layer for downloaded files.

This module converts file bytes into evidence: a small snippet, keyword hits,
file-type and quality signals. It is intentionally lightweight and does not
require heavy OCR unless a future stage adds it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DocumentExtractor:
    """Extract evidence from a downloaded document payload."""

    KEYWORDS = {
        "reporte": "reporte",
        "informe": "informe",
        "financiero": "financiero",
        "instituciones": "instituciones",
        "desarrollo": "desarrollo",
        "actividad": "actividad",
        "activo": "activo",
        "banco": "banco",
        "financiera": "financiera",
        "estadistica": "estadistica",
        "boletin": "boletin",
        "documento": "documento",
        "mensual": "mensual",
        "anual": "anual",
        "trimestral": "trimestral",
        "archivo": "archivo",
    }

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="ignore")
            except Exception:
                return value.decode("latin-1", errors="ignore")
        return str(value)

    def extract_document_evidence(self, content: Any, url: str, file_type: str | None = None) -> Dict[str, Any]:
        text = self._safe_text(content)
        lowered = text.lower()
        file_ext = (file_type or "").lower().strip(".")

        keyword_hits: List[str] = []
        for token, canonical in self.KEYWORDS.items():
            if token in lowered:
                keyword_hits.append(canonical)

        snippet = ""
        if text:
            for pattern in [
                r"[A-Za-zÀ-ÿ0-9\s\-_/]{0,180}(reporte|informe|financiero|instituciones|estadistica|archivo)[A-Za-zÀ-ÿ0-9\s\-_/]{0,180}",
                r"[A-Za-zÀ-ÿ0-9\s\-_/]{0,180}(202[0-9]|mensual|anual|trimestral)[A-Za-zÀ-ÿ0-9\s\-_/]{0,180}",
            ]:
                match = re.search(pattern, lowered, re.IGNORECASE)
                if match:
                    snippet = match.group(0).strip()
                    break

        if not snippet and len(text) > 0:
            snippet = text[:240].strip().replace("\n", " ")

        has_evidence = bool(keyword_hits) or bool(snippet) or bool(file_ext)
        quality_score = 2.0 if has_evidence else 0.0
        if has_evidence and ("reporte" in keyword_hits or "informe" in keyword_hits or "financiero" in keyword_hits):
            quality_score = max(quality_score, 3.0)
        if has_evidence and len(keyword_hits) >= 3:
            quality_score = max(quality_score, 4.0)

        return {
            "url": url,
            "file_type": file_ext,
            "keyword_hits": sorted(dict.fromkeys(keyword_hits)),
            "snippet_text": snippet,
            "has_evidence": has_evidence,
            "quality_score": round(quality_score, 1),
        }
