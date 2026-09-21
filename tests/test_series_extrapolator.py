"""
Pruebas unitarias para el motor de extrapolación de series observadas (Decisión D-17 / Bloque B-47).
Verifica:
1. Lectura de configuración declarativa de series_extrapolation.
2. Generación y validación obligatoria con HTTP HEAD (solo status 200).
3. Regla de parada por corte histórico ante períodos vacíos consecutivos.
4. Integración en DiscoveryEngine.
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock

from crawler.core.discovery import DiscoveryEngine, DiscoveredCandidate
from crawler.core.fetcher import HttpFetcher
from crawler.core.series_extrapolator import SeriesExtrapolator
from crawler.sources.generic_adapter import GenericSourceAdapter


def test_series_extrapolator_is_enabled():
    adapter = GenericSourceAdapter(Path("config/source_asfi.yaml"))
    fetcher = MagicMock(spec=HttpFetcher)
    extrapolator = SeriesExtrapolator(fetcher, adapter)
    assert extrapolator.is_enabled() is True


def test_series_extrapolator_validates_head_and_discards_404():
    adapter = MagicMock()
    adapter.config = {
        "crawl": {
            "series_extrapolation": {
                "enabled": True,
                "template": "https://example.com/data/{year}/{month:02d}/{year}{month:02d}_{serie}.zip",
                "url_origin": "https://example.com/portal",
                "dataset_id": "test_dataset",
                "file_type": "zip",
                "start_year": 2026,
                "end_year": 2026,
                "end_month": 2,
                "series": ["SerieA", "SerieB"],
            }
        }
    }
    fetcher = MagicMock(spec=HttpFetcher)

    # Simulamos que SerieA existe (200) y SerieB no existe (404)
    def fake_head(url):
        if "SerieA" in url:
            return True, 200, {"content-length": "1024", "content-type": "application/zip"}
        return False, 404, {}

    fetcher.fetch_head.side_effect = fake_head

    extrapolator = SeriesExtrapolator(fetcher, adapter, max_consecutive_empty_periods=5)
    candidates = extrapolator.extrapolate_series()

    # 2 meses (feb, ene) x 1 serie exitosa = 2 candidatos confirmados
    assert len(candidates) == 2
    for c in candidates:
        assert "SerieA" in c.url
        assert "SerieB" not in c.url
        assert c.file_type == "zip"
        assert c.dataset_id == "test_dataset"
        assert c.relevance_score == 100.0


def test_series_extrapolator_stops_at_max_consecutive_empty_periods():
    adapter = MagicMock()
    adapter.config = {
        "crawl": {
            "series_extrapolation": {
                "enabled": True,
                "template": "https://example.com/{year}/{month:02d}_{serie}.zip",
                "start_year": 2020,
                "end_year": 2026,
                "end_month": 12,
                "series": ["Serie1"],
            }
        }
    }
    fetcher = MagicMock(spec=HttpFetcher)
    # Todos los períodos responden 404
    fetcher.fetch_head.return_value = (False, 404, {})

    max_empty = 3
    extrapolator = SeriesExtrapolator(fetcher, adapter, max_consecutive_empty_periods=max_empty)
    candidates = extrapolator.extrapolate_series()

    assert len(candidates) == 0
    # Solo debe haber sondeado max_empty períodos antes de abortar
    assert fetcher.fetch_head.call_count == max_empty


def test_discovery_engine_integrates_series_candidates():
    adapter = MagicMock()
    adapter.config = {
        "crawl": {
            "seeds": ["https://example.com/home"],
            "allowed_extensions": ["zip"],
            "strategy": "bfs",
            "max_pages": 1,
            "max_depth": 0,
            "use_sitemaps": False,
            "use_wayback": False,
            "series_extrapolation": {
                "enabled": True,
                "template": "https://example.com/{year}/{month:02d}_{serie}.zip",
                "start_year": 2026,
                "end_year": 2026,
                "end_month": 1,
                "series": ["SerieTest"],
            },
        }
    }
    adapter.seeds = ["https://example.com/home"]
    adapter.allowed_domains = ["example.com"]
    adapter.is_url_excluded.return_value = False
    adapter.classify_dataset.return_value = "dataset_mock"

    fetcher = MagicMock(spec=HttpFetcher)
    fetcher.fetch_head.return_value = (True, 200, {"content-length": "5000"})
    fetcher.fetch_html.return_value = (True, 200, "<html><body>Hola</body></html>")

    discovery = DiscoveryEngine(fetcher, adapter)
    candidates = discovery.discover_from_seeds()

    urls = [c.url for c in candidates]
    assert any("2026/01_SerieTest.zip" in u for u in urls)
