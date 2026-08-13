"""
Orquestador del prospector externo (Crawl Orchestrator).
Coordina la ejecución secuencial del pipeline: Carga -> Descubrimiento -> Extracción (con descompresión de archivos .zip/.tar) -> Canonicalización -> Deduplicación -> Exportación.
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
from crawler.core.archive_extractor import ArchiveExtractor
from crawler.core.canonicalizer import Canonicalizer
from crawler.core.exporter import MultiFormatExporter
from crawler.sources.base_adapter import BaseSourceAdapter


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
        self.archive_extractor = ArchiveExtractor()
        self.canonicalizer = Canonicalizer(self.adapter)
        self.exporter = MultiFormatExporter(self.output_dir)

    def run(self) -> ExternalSourceMap:
        """Ejecuta el pipeline completo de crawling, descompresión y exportación."""
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
            retrieved_at = datetime.now(timezone.utc).isoformat()
            
            # --- Manejo de Archivos Comprimidos (.zip, .tar, .tar.gz) ---
            if self.archive_extractor.is_archive_extension(cand.file_type):
                logger.info(f"Detectado archivo comprimido [{cand.file_type}]: {canonical_url}. Descargando para extraer contenido interno...")
                success, _, content_bytes = self.fetcher.fetch_bytes(canonical_url)

                if success and content_bytes:
                    extracted_items = self.archive_extractor.extract_archive(
                        content_bytes=content_bytes,
                        archive_name=cand.anchor_text or canonical_url,
                        allowed_extensions=self.adapter.allowed_extensions
                    )

                    if extracted_items:
                        logger.info(f"Se extrajeron exitosamente {len(extracted_items)} archivos desde el paquete '{canonical_url}'")
                        for inner in extracted_items:
                            # Resolver vigencia temporal para el archivo interno
                            date_res, _ = self.extractor.resolve_date_and_metadata(
                                url=inner.inner_filename,
                                anchor_text=cand.anchor_text,
                                context_text=cand.context_text
                            )

                            inner_url = f"{canonical_url}#{inner.inner_filename}"
                            resource_key = self.canonicalizer.generate_resource_key(
                                source_id=self.adapter.source_id,
                                dataset_id=cand.dataset_id,
                                period_end=date_res.period_end,
                                file_type=inner.file_type,
                                canonical_url=inner_url
                            )

                            if resource_key in processed_keys:
                                continue
                            processed_keys.add(resource_key)

                            meta = ResourceMetadata(
                                content_length_bytes=inner.size_bytes,
                                sha256=inner.sha256,
                                date_extraction_method=date_res.method,
                                date_confidence=date_res.confidence,
                                extracted_from_archive=canonical_url,
                                geographic_coverage=["Bolivia"] if "finrural" in self.adapter.source_id else []
                            )

                            evidence = ResourceEvidence(
                                anchor_text=f"{cand.anchor_text} -> {inner.inner_filename}",
                                context_text=f"Descomprimido desde {canonical_url} (archivo {inner.inner_filename})",
                                discovered_from=cand.url_origin,
                                extraction_methods=[date_res.method, "archive_extraction"]
                            )

                            resource_item = ResourceItem(
                                id=resource_key,
                                title=f"{cand.anchor_text} ({inner.inner_filename})",
                                url_origin=cand.url_origin,
                                download_url=inner_url,
                                canonical_url=inner_url,
                                file_type=inner.file_type,
                                period_start=date_res.period_start,
                                period_end=date_res.period_end,
                                published_at=date_res.published_at,
                                retrieved_at=retrieved_at,
                                metadata=meta,
                                evidence=evidence
                            )

                            self._add_resource_to_dataset(datasets_dict, cand.dataset_id, cand.url_origin, resource_item)

                        # Si se descomprimieron archivos internos, continuar con el siguiente candidato
                        continue

            # --- Procesamiento estándar para archivos no comprimidos o comprimidos no legibles ---
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

            if resource_key in processed_keys:
                continue
            processed_keys.add(resource_key)

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
                retrieved_at=retrieved_at,
                metadata=meta,
                evidence=evidence
            )

            self._add_resource_to_dataset(datasets_dict, cand.dataset_id, cand.url_origin, resource_item)

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

    def _add_resource_to_dataset(
        self,
        datasets_dict: Dict[str, DatasetItem],
        dataset_id: str,
        source_url: str,
        resource: ResourceItem
    ) -> None:
        """Agrega un recurso al dataset correspondiente dentro del diccionario de datasets."""
        if dataset_id not in datasets_dict:
            ds_name = "Reporte Financiero Mensual" if dataset_id == "reporte_financiero_mensual" else dataset_id.replace("_", " ").title()
            datasets_dict[dataset_id] = DatasetItem(
                id=dataset_id,
                name=ds_name,
                source_url=source_url,
                periodicity="monthly",
                resources=[]
            )
        datasets_dict[dataset_id].resources.append(resource)
