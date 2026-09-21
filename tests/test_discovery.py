"""Regression test: mailto:/tel: links must never be queued as crawlable pages.

Se detectó en vivo (2026-09-17, corrida real contra FINRURAL) que
DiscoveryEngine encolaba enlaces mailto:/tel: como si fueran paginas HTTP:
_is_allowed_domain devolvia True para ellos porque urlparse no les asigna
netloc, y el chequeo `not domain` los dejaba pasar. Cada uno le costaba al
crawler 3 reintentos con backoff (~9s) sin aportar ningun documento,
consumiendo presupuesto real de max_pages.
"""

from types import SimpleNamespace

from crawler.core.discovery import DiscoveryEngine


def _make_engine():
    adapter = SimpleNamespace(
        config={"crawl": {}},
        allowed_domains=["www.finrural.org.bo"],
        seeds=[],
        is_url_excluded=lambda u: False,
        classify_dataset=lambda u, a: "test_dataset",
    )
    # DiscoveryEngine.__init__ solo necesita fetcher para guardarlo; no se usa
    # en los metodos bajo prueba.
    return DiscoveryEngine(fetcher=None, adapter=adapter)


def test_mailto_link_is_not_allowed_domain():
    engine = _make_engine()
    assert engine._is_allowed_domain("mailto:correspondencia@finrural.org.bo") is False


def test_tel_link_is_not_allowed_domain():
    engine = _make_engine()
    assert engine._is_allowed_domain("tel:44411110") is False


def test_javascript_link_is_not_allowed_domain():
    engine = _make_engine()
    assert engine._is_allowed_domain("javascript:void(0)") is False


def test_real_http_link_on_allowed_domain_still_passes():
    engine = _make_engine()
    assert engine._is_allowed_domain("https://www.finrural.org.bo/archivo-historico/") is True


def test_relative_url_with_empty_netloc_still_passes():
    # Comportamiento previo que no debe romperse: un valor sin esquema ni
    # dominio (ya deberia venir absoluto por urljoin, pero por si acaso)
    # sigue tratandose como permitido, solo los esquemas no-HTTP se excluyen.
    engine = _make_engine()
    assert engine._is_allowed_domain("/archivo-historico/") is True


def test_sha_sidecar_is_rejected_even_under_archivos():
    """Regresión B-32: sidecars .sha no deben clasificarse como documento descargable."""
    engine = _make_engine()
    engine.adapter.allowed_extensions = ["pdf", "xlsx", "xls", "csv", "zip"]
    url = "https://www.finrural.org.bo/archivos/info_financiera/2016/financiera_01_2016-pdf.sha"
    is_doc, ext = engine._is_download_link(url, "Descargar checksum")
    assert is_doc is False
    assert ext == ""


def test_pdf_document_passes_under_archivos():
    engine = _make_engine()
    engine.adapter.allowed_extensions = ["pdf", "xlsx", "xls", "csv", "zip"]
    url = "https://www.finrural.org.bo/archivos/info_financiera/2016/financiera_01_2016.pdf"
    is_doc, ext = engine._is_download_link(url, "Reporte financiero")
    assert is_doc is True
    assert ext == "pdf"


def test_extract_pagination_links_rel_next_and_params():
    from bs4 import BeautifulSoup
    engine = _make_engine()
    engine.adapter.allowed_domains = ["www.bcb.gob.bo", "asofinbolivia.com"]
    engine.adapter.allowed_extensions = ["pdf", "xlsx"]

    html = """
    <html>
        <head>
            <link rel="next" href="https://www.bcb.gob.bo/?q=reporte-estadistico&page=2" />
        </head>
        <body>
            <ul class="pagination">
                <li><a href="?q=reporte-estadistico&page=1">1</a></li>
                <li><a href="?q=reporte-estadistico&page=2">2</a></li>
                <li><a href="?q=reporte-estadistico&page=3">Siguiente »</a></li>
            </ul>
            <div class="nav-links">
                <a class="page-numbers" href="https://asofinbolivia.com/index.php/category/boletin_financiero/page/2/">2</a>
            </div>
            <a href="/docs/reporte.pdf">Descargar PDF</a>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    links = engine._extract_pagination_links(soup, "https://www.bcb.gob.bo/?q=reporte-estadistico")

    assert "https://www.bcb.gob.bo/?page=2&q=reporte-estadistico" in links or "https://www.bcb.gob.bo/?q=reporte-estadistico&page=2" in links
    assert any("page/2" in u for u in links)
    assert not any("reporte.pdf" in u for u in links)


def test_priority_queue_exploration_order():
    """Verifica que enlaces con mayor score se visitan antes que los de menor score."""
    from unittest.mock import MagicMock
    engine = _make_engine()
    engine.adapter.config = {"crawl": {"use_sitemaps": False, "strategy": "priority"}}
    engine.strategy = "priority"
    engine.adapter.allowed_domains = ["example.com"]
    engine.adapter.allowed_extensions = ["pdf"]
    engine.adapter.seeds = ["https://example.com/start"]
    engine.max_pages = 3
    engine.max_depth = 2

    # Mock fetcher
    visited_order = []
    html_start = """
    <html>
        <body>
            <a href="/institucional/contacto">Ubicacion y telefonos</a>
            <a href="/publicaciones/anual">Memorias y Boletines Anuales</a>
        </body>
    </html>
    """

    def mock_fetch(url):
        visited_order.append(url)
        if url == "https://example.com/start":
            return True, 200, html_start
        return True, 200, "<html><body>Vacio</body></html>"

    engine.fetcher = MagicMock()
    engine.fetcher.fetch_html = mock_fetch

    engine.discover_from_seeds()
    assert visited_order[0] == "https://example.com/start"
    # La página con palabras clave de publicaciones ("boletines", "memorias") debe visitarse ANTES que /contacto
    assert visited_order[1] == "https://example.com/publicaciones/anual"



