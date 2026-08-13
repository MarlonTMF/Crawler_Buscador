"""
Prueba de integración para verificar la extracción automática de comprimidos en CrawlOrchestrator.
"""

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock
from crawler.core.orchestrator import CrawlOrchestrator
from crawler.core.discovery import DiscoveredCandidate
from crawler.sources.finrural_adapter import FinruralAdapter


def create_sample_zip_bytes() -> bytes:
    """Buffer ZIP simulado con dos PDFs de prueba."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("financiera_01_2026.pdf", b"%PDF Mock 1")
        zf.writestr("financiera_02_2026.pdf", b"%PDF Mock 2")
    return buf.getvalue()


def test_orchestrator_archive_extraction(tmp_path: Path):
    adapter = FinruralAdapter()
    orchestrator = CrawlOrchestrator(adapter=adapter, output_dir=tmp_path)

    # Simular descubrimiento de un archivo .zip
    zip_candidate = DiscoveredCandidate(
        url="https://www.finrural.org.bo/descargas/reportes_2026.zip",
        anchor_text="Paquete de Reportes 2026",
        context_text="Descargar reporte completo",
        file_type="zip",
        dataset_id="reporte_financiero_mensual",
        url_origin="https://www.finrural.org.bo/estadisticas"
    )

    orchestrator.discovery.discover_from_seeds = MagicMock(return_value=[zip_candidate])
    orchestrator.fetcher.fetch_bytes = MagicMock(return_value=(True, 200, create_sample_zip_bytes()))
    orchestrator.fetcher.fetch_head = MagicMock(return_value=(True, 200, {"content-length": "100"}))

    source_map = orchestrator.run()

    # Verificar que el dataset contiene los 2 archivos extraídos desde el .zip
    assert len(source_map.datasets) == 1
    ds = source_map.datasets[0]
    assert len(ds.resources) == 2

    titles = [res.title for res in ds.resources]
    assert any("financiera_01_2026.pdf" in t for t in titles)
    assert any("financiera_02_2026.pdf" in t for t in titles)

    # Verificar que el metadato indica de qué comprimido proviene
    for res in ds.resources:
        assert res.metadata.extracted_from_archive == "https://www.finrural.org.bo/descargas/reportes_2026.zip"
        assert res.metadata.sha256 is not None
