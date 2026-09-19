"""
Orquestador del prospector externo (Crawl Orchestrator).
Coordina la ejecución secuencial del pipeline: Carga -> Descubrimiento -> Extracción (con descompresión) -> Canonicalización -> Deduplicación -> Exportación por carpetas dedicadas.
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
from crawler.core.async_fetcher import AsyncFetcher
from crawler.core.contingency_engine import ContingencyEngine
from crawler.core.control_db import ControlDatabase, ResourceStatus
from crawler.core.alert_notifier import AlertNotifier
from crawler.core.drift_monitor import DriftMonitor


logger = logging.getLogger(__name__)


class CrawlOrchestrator:
    """Coordinador principal de la prospección externa de fuentes."""

    def __init__(self, adapter: BaseSourceAdapter, output_dir: Path):
        self.adapter = adapter
        # Organización por carpetas dedicadas por fuente/URL (ej. output/finrural/, output/bbv/)
        self.source_output_dir = output_dir / self.adapter.source_id
        self.source_output_dir.mkdir(parents=True, exist_ok=True)

        # Allow optional async fetcher (opt-in via config: crawl.use_async_fetcher)
        use_playwright = getattr(self.adapter, "use_playwright", False)
        use_async = False
        try:
            use_async = bool(self.adapter.config.get("crawl", {}).get("use_async_fetcher", False)) and not use_playwright
        except Exception:
            use_async = False

        if use_async:
            # wrap AsyncFetcher sync helpers to provide same interface used in the codebase
            async_client = AsyncFetcher()

            class _SyncAsyncFetcherWrapper:
                def __init__(self, client):
                    self._client = client

                def fetch_html(self, url: str):
                    return self._client.fetch_html_sync(url)

                def fetch_bytes(self, url: str):
                    return self._client.fetch_bytes_sync(url)

                def fetch_head(self, url: str):
                    return self._client.fetch_head_sync(url)

            self.fetcher = _SyncAsyncFetcherWrapper(async_client)
        else:
            self.fetcher = HttpFetcher(
                rate_limit_seconds=self.adapter.rate_limit,
                use_playwright=use_playwright,
            )
        self.discovery = DiscoveryEngine(self.fetcher, self.adapter)
        self.extractor = MetadataExtractor(self.fetcher, self.adapter)
        self.archive_extractor = ArchiveExtractor()
        self.canonicalizer = Canonicalizer(self.adapter)
        self.exporter = MultiFormatExporter(self.source_output_dir)
        self.contingency = ContingencyEngine(self.fetcher)

        audit_cfg = self.adapter.config.get("audit", {})
        self.audit_enabled = bool(audit_cfg.get("enabled", True))
        self.control_db: Optional[ControlDatabase] = None
        if self.audit_enabled:
            db_path = Path(audit_cfg.get("db_path", self.source_output_dir / "inventory.db"))
            self.control_db = ControlDatabase(db_path)
            self.control_db.upsert_source(
                source_id=self.adapter.source_id,
                name=self.adapter.source_name,
                base_url=self.adapter.base_url,
                config_path=str(self.adapter.config_path),
            )

        self.alert_notifier = AlertNotifier(self.source_output_dir / "alerts")

    def run(self) -> ExternalSourceMap:
        """Ejecuta el pipeline completo de crawling, descompresión y exportación."""
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = f"crawl_{self.adapter.source_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Iniciando corrida de prospección: {run_id} para fuente [{self.adapter.source_name}]")

        # 1. Fase de Descubrimiento
        candidates = self.discovery.discover_from_seeds()
        logger.info(f"Se descubrieron {len(candidates)} candidatos a recursos descargables.")
        self._check_volumetric_alert(len(candidates))

        # 2. Fase de Extracción, Canonicalización y Procesamiento
        datasets_dict: Dict[str, DatasetItem] = {}
        processed_keys: Set[str] = set()

        for cand in candidates:
            canonical_url = self.canonicalizer.canonicalize_url(cand.url)
            retrieved_at = datetime.now(timezone.utc).isoformat()
            
            # --- Manejo de Archivos Comprimidos (.zip, .tar, .tar.gz) ---
            if self.archive_extractor.is_archive_extension(cand.file_type):
                logger.info(f"Detectado archivo comprimido [{cand.file_type}]: {canonical_url}. Descargando para extraer contenido interno...")
                fallback_result = self.contingency.fetch_bytes_with_fallback(canonical_url)
                success = fallback_result.success
                content_bytes = fallback_result.content_bytes
                archive_url_used = fallback_result.resolved_url or canonical_url

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

                            is_headless = False
                            if hasattr(self.fetcher, "is_resolved_via_headless"):
                                if self.fetcher.is_resolved_via_headless(cand.url_origin) or self.fetcher.is_resolved_via_headless(canonical_url):
                                    is_headless = True

                            meta = ResourceMetadata(
                                content_length_bytes=inner.size_bytes,
                                sha256=inner.sha256,
                                date_extraction_method=date_res.method,
                                date_confidence=date_res.confidence,
                                extracted_from_archive=archive_url_used,
                                geographic_coverage=["Bolivia"] if "finrural" in self.adapter.source_id else [],
                                resolved_via_headless=is_headless,
                            )

                            archive_methods = [date_res.method, "archive_extraction", fallback_result.method]
                            if is_headless:
                                archive_methods.append("resuelto_via_headless")

                            evidence = ResourceEvidence(
                                anchor_text=f"{cand.anchor_text} -> {inner.inner_filename}",
                                context_text=f"Descomprimido desde {archive_url_used} (archivo {inner.inner_filename})",
                                discovered_from=cand.url_origin,
                                extraction_methods=archive_methods,
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
                            self._audit_resource(
                                resource=resource_item,
                                dataset_id=cand.dataset_id,
                                status=ResourceStatus.RECOVERED if fallback_result.method == "wayback_snapshot" else ResourceStatus.PROCESSED,
                            )

                        # Si se descomprimieron archivos internos, continuar con el siguiente candidato
                        continue
                else:
                    self._audit_failed_candidate(cand, canonical_url, str(fallback_result.status_code))

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

            is_headless = False
            if hasattr(self.fetcher, "is_resolved_via_headless"):
                if self.fetcher.is_resolved_via_headless(cand.url_origin) or self.fetcher.is_resolved_via_headless(canonical_url):
                    is_headless = True

            meta = ResourceMetadata(
                content_length_bytes=http_meta.get("content_length_bytes"),
                etag=http_meta.get("etag"),
                last_modified=http_meta.get("last_modified"),
                date_extraction_method=date_res.method,
                date_confidence=date_res.confidence,
                geographic_coverage=["Bolivia"] if "finrural" in self.adapter.source_id else [],
                resolved_via_headless=is_headless,
            )

            extraction_methods = [date_res.method]
            if is_headless:
                extraction_methods.append("resuelto_via_headless")
                logger.info("Auditoría: Recurso %s registrado como resuelto vía headless tras bloqueo 403", canonical_url)

            evidence = ResourceEvidence(
                anchor_text=cand.anchor_text,
                context_text=cand.context_text,
                discovered_from=cand.url_origin,
                extraction_methods=extraction_methods,
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
            final_status = self._maybe_hash_resource(resource_item, cand.dataset_id)
            self._audit_resource(resource_item, cand.dataset_id, final_status)

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

        # 3. Fase de Exportación Multi-Formato en carpeta dedicada por fuente
        self.exporter.export_standard(source_map, f"mapa_{self.adapter.source_id}.json")
        self.exporter.export_tree_format(source_map, f"mapa_{self.adapter.source_id}_tree.json")
        self.exporter.export_compact_ai(source_map, f"mapa_{self.adapter.source_id}_compact.json")
        if self.control_db:
            self.control_db.close()

        return source_map

    def _maybe_hash_resource(self, resource: ResourceItem, dataset_id: str) -> str:
        """Optionally downloads a resource to calculate SHA-256 and use contingency fallback."""
        hash_cfg = self.adapter.config.get("content_hashing", {})
        if not bool(hash_cfg.get("enabled", False)):
            return ResourceStatus.PROCESSED

        result = self.contingency.fetch_bytes_with_fallback(resource.canonical_url)
        if not result.success or result.content_bytes is None:
            self._audit_resource(resource, dataset_id, ResourceStatus.ERROR, error_code=str(result.status_code))
            return ResourceStatus.ERROR

        resource.metadata.sha256 = MetadataExtractor.compute_sha256(result.content_bytes)
        resource.metadata.content_length_bytes = len(result.content_bytes)
        if result.method == "wayback_snapshot" and result.resolved_url:
            resource.download_url = result.resolved_url
            resource.evidence.extraction_methods.append("wayback_snapshot")
            return ResourceStatus.RECOVERED

        return ResourceStatus.PROCESSED

    def _audit_resource(
        self,
        resource: ResourceItem,
        dataset_id: str,
        status: str,
        error_code: Optional[str] = None,
    ) -> None:
        if not self.control_db:
            return
        self.control_db.upsert_resource(
            source_id=self.adapter.source_id,
            dataset_id=dataset_id,
            canonical_url=resource.canonical_url,
            download_url=resource.download_url,
            status=status,
            resource_id=resource.id,
            content_sha256=resource.metadata.sha256,
            file_size_bytes=resource.metadata.content_length_bytes,
            period_start=resource.period_start,
            period_end=resource.period_end,
            date_confidence_score=resource.metadata.date_confidence,
            error_code=error_code,
        )

    def _audit_failed_candidate(self, cand: DiscoveredCandidate, canonical_url: str, error_code: str) -> None:
        if not self.control_db:
            return
        self.control_db.upsert_resource(
            source_id=self.adapter.source_id,
            dataset_id=cand.dataset_id,
            canonical_url=canonical_url,
            download_url=cand.url,
            status=ResourceStatus.ERROR,
            error_code=error_code,
        )

    def _check_volumetric_alert(self, current_count: int) -> None:
        monitoring_cfg = self.adapter.config.get("monitoring", {})
        history = monitoring_cfg.get("historical_resource_counts", [])
        if not history:
            return

        monitor = DriftMonitor(threshold=float(monitoring_cfg.get("drift_threshold", 0.30)))
        if monitor.volumetric_anomaly(history, current_count):
            self.alert_notifier.notify(
                self.adapter.source_id,
                "volumetric_anomaly",
                {
                    "current_count": current_count,
                    "historical_resource_counts": history,
                    "status": "REQUIERE_REVISION_ESTRUCTURAL",
                },
            )

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
