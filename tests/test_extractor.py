"""
Pruebas unitarias para la extracción de fechas y metadatos en 4 capas.
"""

from pathlib import Path
from crawler.core.fetcher import HttpFetcher
from crawler.sources.finrural_adapter import FinruralAdapter
from crawler.core.extractor import MetadataExtractor


def test_layered_date_extraction():
    adapter = FinruralAdapter()
    fetcher = HttpFetcher()
    extractor = MetadataExtractor(fetcher, adapter)

    # Capa 1: URL Pattern (financiera_05_2025.pdf -> 2025-05-01 al 2025-05-31)
    res_l1 = extractor.extract_date_layer1_url("https://www.finrural.org.bo/archivos/info_financiera/2025/financiera_05_2025.pdf")
    assert res_l1 is not None
    assert res_l1.period_start == "2025-05-01"
    assert res_l1.period_end == "2025-05-31"
    assert res_l1.confidence == "high"
    assert res_l1.method == "url_pattern"

    # Capa 2: DOM Context ("Información Financiera Mayo 2025")
    res_l2 = extractor.extract_date_layer2_dom("Reporte Mensual", "Publicación correspondiente a mayo 2025.")
    assert res_l2 is not None
    assert res_l2.period_start == "2025-05-01"
    assert res_l2.period_end == "2025-05-31"
    assert res_l2.confidence == "medium"
    assert res_l2.method == "dom_context"


def test_fetch_head_network_error_resilience(monkeypatch):
    from unittest.mock import MagicMock
    import requests

    fetcher = HttpFetcher(max_retries=2)
    fetcher.session = MagicMock()
    fetcher.session.head.side_effect = requests.exceptions.ConnectionError("Connection refused")
    monkeypatch.setattr("time.sleep", lambda s: None)

    success, status, headers = fetcher.fetch_head("https://broken.example.com/test.pdf")
    assert success is False
    assert status == 0
    assert headers == {}
    assert fetcher.session.head.call_count == 2


