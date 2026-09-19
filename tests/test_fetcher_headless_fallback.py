"""
tests/test_fetcher_headless_fallback.py
=======================================
Pruebas unitarias para el reintento automatico con navegador real (HeadlessFetcher)
ante respuestas HTTP 403 en el cliente HTTP simple (Etapa D - B-23 / Decision D-03).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

from crawler.core.fetcher import HttpFetcher
from crawler.core.headless_fetcher import HeadlessFetcher, HeadlessFetchResult
from crawler.core.orchestrator import CrawlOrchestrator
from crawler.sources.base_adapter import BaseSourceAdapter


class WafSourceAdapter(BaseSourceAdapter):
    """Adaptador de prueba para simular fuente protegida por WAF/Cloudflare."""
    def is_url_excluded(self, url: str) -> bool:
        return False

    def classify_dataset(self, url: str, anchor_text: str = ""):
        return "boletines_financieros"


def test_auto_headless_retry_on_403_success(caplog):
    """Criterios 1 y 2: Un 403 en HTTP simple activa condicionalmente HeadlessFetcher y registra auditoria."""
    mock_headless = MagicMock(spec=HeadlessFetcher)
    html_rendered = "<html><head><title>WAF Bypassed</title></head><body><a href='/doc.pdf'>Documento</a></body></html>"
    mock_headless.fetch.return_value = (
        True,
        200,
        HeadlessFetchResult(html=html_rendered),
    )

    fetcher = HttpFetcher(
        honor_robots_txt=False,
        headless_fetcher=mock_headless,
        auto_headless_on_403=True,
    )

    mock_resp_403 = MagicMock(spec=requests.Response)
    mock_resp_403.status_code = 403
    mock_resp_403.apparent_encoding = "utf-8"

    with patch.object(fetcher.session, "get", return_value=mock_resp_403):
        with caplog.at_level("INFO"):
            ok, status, html = fetcher.fetch_html("https://portal-protegido.gob.bo/informes")

    assert ok is True
    assert status == 200
    assert html == html_rendered
    mock_headless.fetch.assert_called_once_with("https://portal-protegido.gob.bo/informes")

    assert fetcher.is_resolved_via_headless("https://portal-protegido.gob.bo/informes") is True
    assert fetcher.last_fetch_resolved_via_headless is True
    assert "resuelta exitosamente" in caplog.text


def test_no_headless_retry_on_200_or_404_or_500():
    """Criterio 1: Playwright es costoso; NO debe activarse ante respuestas 200, 404 o 500."""
    mock_headless = MagicMock(spec=HeadlessFetcher)
    fetcher = HttpFetcher(
        honor_robots_txt=False,
        headless_fetcher=mock_headless,
        auto_headless_on_403=True,
    )

    mock_resp_200 = MagicMock(spec=requests.Response)
    mock_resp_200.status_code = 200
    mock_resp_200.text = "<html>OK</html>"
    mock_resp_200.apparent_encoding = "utf-8"

    with patch.object(fetcher.session, "get", return_value=mock_resp_200):
        ok, status, html = fetcher.fetch_html("https://portal.gob.bo/publico")
        assert ok is True
        assert status == 200
        mock_headless.fetch.assert_not_called()
        assert fetcher.is_resolved_via_headless("https://portal.gob.bo/publico") is False
        assert fetcher.last_fetch_resolved_via_headless is False

    mock_resp_404 = MagicMock(spec=requests.Response)
    mock_resp_404.status_code = 404
    mock_resp_404.apparent_encoding = "utf-8"

    with patch.object(fetcher.session, "get", return_value=mock_resp_404):
        ok, status, html = fetcher.fetch_html("https://portal.gob.bo/no-existe")
        assert ok is False
        assert status == 404
        mock_headless.fetch.assert_not_called()
        assert fetcher.is_resolved_via_headless("https://portal.gob.bo/no-existe") is False


def test_auto_headless_disabled_when_flag_false():
    """Si auto_headless_on_403 esta explicitamente desactivado, no se invoca headless ante 403."""
    mock_headless = MagicMock(spec=HeadlessFetcher)
    fetcher = HttpFetcher(
        honor_robots_txt=False,
        headless_fetcher=mock_headless,
        auto_headless_on_403=False,
    )

    mock_resp_403 = MagicMock(spec=requests.Response)
    mock_resp_403.status_code = 403
    mock_resp_403.apparent_encoding = "utf-8"

    with patch.object(fetcher.session, "get", return_value=mock_resp_403):
        ok, status, html = fetcher.fetch_html("https://portal-protegido.gob.bo/informes")

    assert ok is False
    assert status == 403
    assert html is None
    mock_headless.fetch.assert_not_called()
    assert fetcher.is_resolved_via_headless("https://portal-protegido.gob.bo/informes") is False


def test_validate_url_access_records_headless_resolution():
    """Criterio 2: validate_url_access reporta resolved_via_headless y browser_fallback_used."""
    mock_headless = MagicMock(spec=HeadlessFetcher)
    html_content = "<html><body><h1>Reporte</h1><a href='https://ejemplo.com/boletin.pdf'>Descargar PDF</a></body></html>"
    mock_headless.fetch.return_value = (
        True,
        200,
        HeadlessFetchResult(html=html_content),
    )

    fetcher = HttpFetcher(
        honor_robots_txt=False,
        headless_fetcher=mock_headless,
        auto_headless_on_403=True,
    )

    mock_head_resp = MagicMock(spec=requests.Response)
    mock_head_resp.status_code = 403
    mock_head_resp.headers = {}

    mock_get_resp = MagicMock(spec=requests.Response)
    mock_get_resp.status_code = 403
    mock_get_resp.apparent_encoding = "utf-8"

    with patch.object(fetcher.session, "head", return_value=mock_head_resp), \
         patch.object(fetcher.session, "get", return_value=mock_get_resp):
        res = fetcher.validate_url_access("https://ejemplo.com/waf_page")

    assert res["reachable_http"] is True
    assert res["status_code"] == 200
    assert res.get("browser_fallback_used") is True
    assert res.get("resolved_via_headless") is True
    assert res["document_links_found"] >= 1


def test_orchestrator_pipeline_recovers_403_source_via_headless(tmp_path: Path):
    """Criterio 3: Una fuente que bloquea por 403 pasa a extraer documentos y queda auditada."""
    cfg_file = tmp_path / "source_waf.yaml"
    db_file = str(tmp_path / "inventory.db").replace("\\", "/")
    cfg_file.write_text(
        f"""
source:
  id: waf_source
  name: "Fuente Protegida WAF"
  base_url: "https://waf-source.gob.bo"
  allowed_domains: ["waf-source.gob.bo"]
crawl:
  seeds:
    - "https://waf-source.gob.bo/publicaciones"
  max_depth: 1
  max_pages: 5
  strategy: bfs
  use_playwright: false
  allowed_extensions: [pdf]
audit:
  enabled: true
  db_path: "{db_file}"
""",
        encoding="utf-8",
    )

    adapter = WafSourceAdapter(cfg_file)
    orchestrator = CrawlOrchestrator(adapter, output_dir=tmp_path / "output")

    mock_headless = MagicMock(spec=HeadlessFetcher)
    waf_html = (
        "<html><head><title>Publicaciones</title></head><body>"
        "<a href='https://waf-source.gob.bo/docs/boletin_2026_01.pdf'>Boletin Enero 2026</a>"
        "</body></html>"
    )
    mock_headless.fetch.return_value = (
        True,
        200,
        HeadlessFetchResult(html=waf_html),
    )
    orchestrator.fetcher.headless_fetcher = mock_headless

    mock_resp_403 = MagicMock(spec=requests.Response)
    mock_resp_403.status_code = 403
    mock_resp_403.apparent_encoding = "utf-8"

    with patch.object(orchestrator.fetcher.session, "get", return_value=mock_resp_403):
        source_map = orchestrator.run()

    assert len(source_map.datasets) == 1
    dataset = source_map.datasets[0]
    assert dataset.id == "boletines_financieros"
    assert len(dataset.resources) == 1

    resource = dataset.resources[0]
    assert resource.canonical_url == "https://waf-source.gob.bo/docs/boletin_2026_01.pdf"

    assert resource.metadata.resolved_via_headless is True
    assert "resuelto_via_headless" in resource.evidence.extraction_methods
