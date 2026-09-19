"""
tests/test_deduplication.py
===========================
Pruebas para el deduplicador intra-corrida en DiscoveryEngine y CrawlOrchestrator
(Etapa D · B-24 / Precondición O-31 / AI_LOG E-17).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import sqlite3

from crawler.core.discovery import DiscoveryEngine, DiscoveredCandidate
from crawler.core.fetcher import HttpFetcher
from crawler.core.orchestrator import CrawlOrchestrator
from crawler.sources.base_adapter import BaseSourceAdapter


class MockAdapter(BaseSourceAdapter):
    def __init__(self, config_dict: dict):
        self.config = config_dict
        self.config_path = Path("mock_config.yaml")

    def is_url_excluded(self, url: str) -> bool:
        return False

    def classify_dataset(self, url: str, anchor_text: str = ""):
        return "dataset_test"


def test_discovery_deduplicates_candidate_urls():
    """Verifica que si múltiples enlaces o páginas apuntan al mismo documento, se añade solo una vez."""
    mock_fetcher = MagicMock(spec=HttpFetcher)
    mock_fetcher.fetch_html.return_value = (
        True,
        200,
        """
        <html><body>
          <a href="/docs/reporte_2026.pdf">Reporte 2026</a>
          <a href="/docs/reporte_2026.pdf">Descargar Reporte 2026 PDF</a>
          <a href="https://example.com/docs/reporte_2026.pdf">Enlace duplicado absoluto</a>
        </body></html>
        """
    )
    mock_fetcher.honor_robots_txt = False

    adapter = MockAdapter({
        "source": {"id": "test", "name": "Test", "base_url": "https://example.com"},
        "crawl": {"seeds": ["https://example.com"], "max_depth": 0, "max_pages": 1}
    })

    discovery = DiscoveryEngine(mock_fetcher, adapter)
    candidates = discovery.discover_from_seeds()

    # Aunque el HTML tiene 3 enlaces al mismo PDF, solo debe haber 1 candidato
    assert len(candidates) == 1
    assert candidates[0].url == "https://example.com/docs/reporte_2026.pdf"


def test_discovery_deduplicates_bfs_queue():
    """Verifica que una misma URL de navegación no se encole múltiples veces en BFS."""
    from collections import deque

    mock_fetcher = MagicMock(spec=HttpFetcher)
    def _mock_fetch(url):
        if url == "https://example.com":
            return (True, 200, "<html><body><a href='/seccion'>Seccion 1</a><a href='/seccion'>Seccion 2</a></body></html>")
        elif url == "https://example.com/seccion":
            return (True, 200, "<html><body><a href='/docs/informe.pdf'>Informe</a></body></html>")
        return (False, 404, None)

    mock_fetcher.fetch_html.side_effect = _mock_fetch
    mock_fetcher.honor_robots_txt = False

    adapter = MockAdapter({
        "source": {"id": "test", "name": "Test", "base_url": "https://example.com", "allowed_domains": ["example.com"]},
        "crawl": {"seeds": ["https://example.com"], "max_depth": 1, "max_pages": 5, "use_sitemaps": False}
    })

    appended_items = []
    class TrackingDeque(deque):
        def append(self, item):
            appended_items.append(item)
            super().append(item)

    with patch("crawler.core.discovery.deque", side_effect=lambda *args, **kwargs: TrackingDeque(*args, **kwargs)):
        discovery = DiscoveryEngine(mock_fetcher, adapter)
        candidates = discovery.discover_from_seeds()

    assert len(candidates) == 1
    # /seccion aparece 2 veces en el HTML, pero solo debió encolarse 1 vez en la cola BFS
    seccion_enqueued = [url for url, depth in appended_items if "/seccion" in url]
    assert len(seccion_enqueued) == 1, f"/seccion se encoló {len(seccion_enqueued)} veces en BFS (esperado: 1)"
    assert len(discovery.visited_urls) == 2


def test_orchestrator_intra_run_deduplication(tmp_path: Path):
    """Verifica que el orquestador no duplique registros en inventory.db en una misma corrida."""
    cfg_file = tmp_path / "source_dedup.yaml"
    db_file = str(tmp_path / "inventory.db").replace("\\", "/")
    cfg_file.write_text(
        f"""
source:
  id: dedup_src
  name: "Dedup Test"
  base_url: "https://example.com"
  allowed_domains: ["example.com"]
crawl:
  seeds: ["https://example.com"]
  max_depth: 0
  max_pages: 1
  strategy: bfs
audit:
  enabled: true
  db_path: "{db_file}"
""",
        encoding="utf-8",
    )

    adapter = MockAdapter({
        "source": {"id": "dedup_src", "name": "Dedup Test", "base_url": "https://example.com", "allowed_domains": ["example.com"]},
        "crawl": {"seeds": ["https://example.com"], "max_depth": 0, "max_pages": 1, "strategy": "bfs"},
        "audit": {"enabled": True, "db_path": db_file},
    })
    orchestrator = CrawlOrchestrator(adapter, output_dir=tmp_path / "output")

    # Inyectamos artificialmente candidatos que comparten la misma URL canónica pero distinto dataset_id.
    # Pre-fix: processed_keys chequeaba `resource_key` (que incluye dataset_id), por lo que sin
    # seen_canonical_urls ambos candidatos se procesaban y auditaban, duplicando la fila en la BD.
    c1 = DiscoveredCandidate(
        url="https://example.com/doc.pdf",
        url_origin="https://example.com",
        anchor_text="Doc 1",
        context_text="",
        dataset_id="dataset_a",
        file_type="pdf",
    )
    c2 = DiscoveredCandidate(
        url="https://example.com/doc.pdf",
        url_origin="https://example.com/otra_pagina",
        anchor_text="Doc 2",
        context_text="",
        dataset_id="dataset_b",
        file_type="pdf",
    )
    orchestrator.discovery.discover_from_seeds = MagicMock(return_value=[c1, c2])

    mock_head_resp = MagicMock()
    mock_head_resp.status_code = 200
    mock_head_resp.headers = {"Content-Length": "100"}
    with patch.object(orchestrator.fetcher.session, "head", return_value=mock_head_resp):
        source_map = orchestrator.run()

    # En los datasets exportados debe haber exactamente 1 recurso en total
    total_resources = sum(len(ds.resources) for ds in source_map.datasets)
    assert total_resources == 1, f"Se esperaban 1 recurso, se obtuvieron {total_resources}"

    # En la base inventory.db debe haber exactamente 1 fila
    conn = sqlite3.connect(db_file)
    count = conn.execute("SELECT COUNT(*) FROM resource_audit_log").fetchone()[0]
    conn.close()
    assert count == 1, f"Se esperaba 1 fila en inventory.db, se encontraron {count}"
