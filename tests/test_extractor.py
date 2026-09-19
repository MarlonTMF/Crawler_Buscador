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


def test_extract_date_layer3_http_scheme_guard():
    """Regresión B-28 / B-30: extract_date_layer3_http no debe invocar fetch_head
    ante URLs sin esquema http/https (ej. nombres internos de archivo en ZIP o rutas locales)."""
    from unittest.mock import MagicMock
    adapter = FinruralAdapter()
    fetcher = HttpFetcher()
    fetcher.fetch_head = MagicMock()
    extractor = MetadataExtractor(fetcher, adapter)

    # 1. Nombre de archivo interno de ZIP sin esquema HTTP
    res1, meta1 = extractor.extract_date_layer3_http("reporte_mensual_2025.xlsx")
    assert res1 is None
    assert meta1["content_length_bytes"] is None
    fetcher.fetch_head.assert_not_called()

    # 2. Esquema no-HTTP (file://, mailto:, etc.)
    res2, meta2 = extractor.extract_date_layer3_http("file:///local/archive/doc.pdf")
    assert res2 is None
    fetcher.fetch_head.assert_not_called()



