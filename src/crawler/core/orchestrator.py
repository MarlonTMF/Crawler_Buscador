"""
Orquestador del prospector externo (Crawl Orchestrator).
Coordina la ejecución secuencial del pipeline: Carga -> Descubrimiento -> Extracción -> Canonicalización -> Deduplicación -> Exportación.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Set, List, Optional

from crawler.core.models import (
    SourceInfo, CrawlRunInfo, ResourceMetadata, ResourceEvidence,
    ResourceItem, DatasetItem, ChangeEventItem, ExternalSourceMap
)
from crawler.core.fetcher import HttpFetcher
from crawler.core.discovery import DiscoveryEngine, DiscoveredCandidate
from crawler.core.extractor import MetadataExtractor
from crawler.core.canonicalizer import Canonicalizer
from crawler.core.exporter import MultiFormatExporter
from crawler.sources.base_adapter import BaseSourceAdapter
from crawler.sources.finrural_adapter import FinruralAdapter

logger = logging.getLogger(__name__)


class CrawlOrchestrator:
    """Coordinador principal de la prospección externa de fuentes."""

    def __init__(self, adapter: BaseSourceAdapter, output_dir: Path):
        self.adapter = adapter
        self.output_dir = output_dir
        self.fetcher = HttpFetcher(
            rate_limit_seconds=self.adapter.rate_limit
        )
        self.discovery = DiscoveryEngine(self.fetcher, self.adapter)
        self.extractor = MetadataExtractor(self.fetcher, self.adapter)
        self.canonicalizer = Canonicalizer(self.adapter)
        self.exporter = MultiFormatExporter(self.output_dir)

    def run(self) -> ExternalSourceMap:
        """Ejecuta el pipeline completo de crawling y exportación."""
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = f"crawl_{self.adapter.source_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Iniciando corrida de prospección: {run_id} para fuente [{self.adapter.source_name}]")

        # 1. Fase de Descubrimiento
        candidates = self.discovery.discover_from_seeds()
        logger.info(f"Se descubrieron {len(candidates)} candidatos a recursos descargables.")

        # 2. Fase de Extracción, Canonicalización y Procesamiento
        datasets_dict: Dict[str, DatasetItem] = {}
        processed_keys: Set[str] = set()

        for cand in candidates:
            canonical_url = self.canonicalizer.canonicalize_url(cand.url)
            
            # Extracción de fecha y metadatos HTTP
            date_res, http_meta = self.extractor.resolve_date_and_metadata(
                url=canonical_url,
                anchor_text=cand.anchor_text,
                context_text=cand.context_text
            )

            resource_key = self.canonicalizer.generate_resource_key(
                source_id=self.adapter.source_id,
                dataset_id=cand.dataset_id,
                period_end=date_res.period_end,
                file_type=cand.file_type,
                canonical_url=canonical_url
            )

            # Deduplicación por resource_key
            if resource_key in processed_keys:
                continue
            processed_keys.add(resource_key)

            # Construir metadatos y evidencia
            meta = ResourceMetadata(
                content_length_bytes=http_meta.get("content_length_bytes"),
                etag=http_meta.get("etag"),
                last_modified=http_meta.get("last_modified"),
                date_extraction_method=date_res.method,
                date_confidence=date_res.confidence,
                geographic_coverage=["Bolivia"] if "finrural" in self.adapter.source_id else []
            )

            evidence = ResourceEvidence(
                anchor_text=cand.anchor_text,
                context_text=cand.context_text,
                discovered_from=cand.url_origin,
                extraction_methods=[date_res.method]
            )

            resource_item = ResourceItem(
                id=resource_key,
                title=cand.anchor_text,
                url_origin=cand.url_origin,
                download_url=canonical_url,
                canonical_url=canonical_url,
                file_type=cand.file_type,
                period_start=date_res.period_start,
                period_end=date_res.period_end,
                published_at=date_res.published_at,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                metadata=meta,
                evidence=evidence
            )

            # Organizar por dataset
            if cand.dataset_id not in datasets_dict:
                ds_name = "Reporte Financiero Mensual" if cand.dataset_id == "reporte_financiero_mensual" else cand.dataset_id.replace("_", " ").title()
                datasets_dict[cand.dataset_id] = DatasetItem(
                    id=cand.dataset_id,
                    name=ds_name,
                    source_url=cand.url_origin,
                    periodicity="monthly",
                    resources=[]
                )

            datasets_dict[cand.dataset_id].resources.append(resource_item)

        finished_at = datetime.now(timezone.utc).isoformat()

        # Construir objeto de dominio final
        source_info = SourceInfo(
            id=self.adapter.source_id,
            name=self.adapter.source_name,
            base_url=self.adapter.base_url,
            allowed_domains=self.adapter.allowed_domains
        )

        crawl_info = CrawlRunInfo(
            id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            status="success" if len(candidates) > 0 else "partial"
        )

        source_map = ExternalSourceMap(
            schema_version="1.0.0",
            source=source_info,
            crawl_run=crawl_info,
            datasets=list(datasets_dict.values()),
            change_events=[]
        )

        # 3. Fase de Exportación Multi-Formato
        self.exporter.export_standard(source_map, f"mapa_{self.adapter.source_id}.json")
        self.exporter.export_tree_format(source_map, f"mapa_{self.adapter.source_id}_tree.json")
        self.exporter.export_compact_ai(source_map, f"mapa_{self.adapter.source_id}_compact.json")

        return source_map
