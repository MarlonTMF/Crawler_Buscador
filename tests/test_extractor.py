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


def test_b50_real_date_patterns_and_separation():
    adapter = FinruralAdapter()
    fetcher = HttpFetcher()
    extractor = MetadataExtractor(fetcher, adapter)

    # 1. ASFI pattern: /AAAA-MM/ in folder + year in filename (published_at vs period_start)
    res1 = extractor.extract_date_layer1_url("https://www.asfi.gob.bo/sites/default/files/2026-06/MEMORIA_2025.pdf")
    assert res1 is not None
    assert res1.published_at == "2026-06-01"
    assert res1.period_start == "2025-01-01"
    assert res1.period_end == "2025-12-31"
    assert res1.confidence == "high"

    # 2. ASFI publication folder only (no period in filename): confidence must be low, never high!
    res2 = extractor.extract_date_layer1_url("https://www.asfi.gob.bo/sites/default/files/2026-05/circular_normativa.pdf")
    assert res2 is not None
    assert res2.published_at == "2026-05-01"
    assert res2.period_start is None
    assert res2.confidence == "low"

    # 3. BCB pattern: /AAAA/MM/ (or /AAAA/MM/DD/) in folder + period in filename
    res3 = extractor.extract_date_layer1_url("https://www.bcb.gob.bo/webdocs/publicacionesbcb/2019/05/17/BCB%20Memoria%202018%20CAPITULO%204.pdf")
    assert res3 is not None
    assert res3.published_at == "2019-05-17"
    assert res3.period_start == "2018-01-01"
    assert res3.period_end == "2018-12-31"
    assert res3.confidence == "high"

    # 4. Pattern AAAAMM_
    res4 = extractor.extract_date_layer1_url("https://example.com/docs/202401_boletin.pdf")
    assert res4 is not None
    assert res4.period_start == "2024-01-01"
    assert res4.period_end == "2024-01-31"
    assert res4.published_at is None
    assert res4.confidence == "medium"

    # 5. Pattern DDmesAAAA
    res5 = extractor.extract_date_layer1_url("https://www.bcb.gob.bo/webdocs/files_noticias/C8%202026-9%20DE%20SEPTIEMBRE.pdf")
    assert res5 is not None
    assert res5.period_start == "2026-09-09"
    assert res5.period_end == "2026-09-09"
    assert res5.confidence == "medium"

    # 6. Año suelto
    res6 = extractor.extract_date_layer1_url("https://www.bcb.gob.bo/webdocs/Otros/Cronograma_anual_de_publicaciones_2026.xlsx")
    assert res6 is not None
    assert res6.period_start == "2026-01-01"
    assert res6.period_end == "2026-12-31"
    assert res6.confidence == "medium"




