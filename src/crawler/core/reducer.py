"""
Capa de Reducción Semántica para Agentes de IA (ADR-004).
Limpia boilerplate de navegación y genera una representación compacta optimizada para minimizar el uso de tokens.
"""

import hashlib
from typing import Dict, Any, List
from crawler.core.models import ResourceItem


class AIContextReducer:
    """Procesa objetos ResourceItem y produce estructuras reducidas para consumo por IA."""

    @staticmethod
    def extract_signals(title: str, context: str) -> List[str]:
        """Extrae palabras clave y señales semánticas relevantes."""
        signals = []
        combined = f"{title} {context}".lower()

        keywords = [
            "reporte financiero", "mensual", "ifd", "cartera",
            "prestatarios", "mora", "indicadores", "boletín", "patrimonial"
        ]
        for kw in keywords:
            if kw in combined:
                signals.append(kw.title())

        return sorted(list(set(signals)))

    @staticmethod
    def compute_content_signature(resource: ResourceItem) -> str:
        """Calcula una firma compacta basada en la identidad del recurso y su fecha de vigencia."""
        raw_str = f"{resource.id}|{resource.download_url}|{resource.period_end or ''}|{resource.metadata.sha256 or ''}"
        return f"sha256:{hashlib.sha256(raw_str.encode('utf-8')).hexdigest()}"

    def build_compact_item(self, source_id: str, dataset_id: str, resource: ResourceItem) -> Dict[str, Any]:
        """
        Construye una ficha compacta de recurso sin ruido institucional.
        
        Returns:
            Dict[str, Any]: Ficha compacta para consumo por IA.
        """
        signals = self.extract_signals(resource.title, resource.evidence.context_text or "")
        content_sig = self.compute_content_signature(resource)

        return {
            "source_id": source_id,
            "dataset_id": dataset_id,
            "resource_id": resource.id,
            "title": resource.title,
            "period_end": resource.period_end,
            "format": resource.file_type,
            "download_url": resource.download_url,
            "content_hash": resource.metadata.sha256 or f"sig:{content_sig[:12]}",
            "signals": signals,
            "extraction_confidence": resource.metadata.date_confidence,
            "content_signature": content_sig
        }
