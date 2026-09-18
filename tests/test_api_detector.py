from crawler.core.api_detector import (
    ApiSiteReport,
    merge_reports,
    scan_html_for_api_links,
    scan_js_bundles_for_api_calls,
    scan_network_traffic_for_apis,
    _is_same_site,
    _looks_like_api_response,
    _looks_like_api_url,
    _looks_like_doc_response,
)


def test_is_same_site_ignores_www_but_rejects_third_party():
    assert _is_same_site("https://www.finrural.org.bo/wp-json", "https://finrural.org.bo")
    assert not _is_same_site("https://player.vimeo.com/api/player.js", "https://www.finrural.org.bo")
    assert not _is_same_site("https://openknowledge.worldbank.org/server/api", "https://www.doingbusiness.org")


def test_scan_html_for_api_links_ignores_third_party_endpoints():
    html = '<a href="https://player.vimeo.com/api/player.js">Video</a>'
    result = scan_html_for_api_links(html, "https://example.org")
    assert result["endpoints"] == []


def test_looks_like_api_url_detects_common_patterns():
    assert _looks_like_api_url("https://example.org/api/v1/institutions")
    assert _looks_like_api_url("https://example.org/wp-json/wp/v2/posts")
    assert _looks_like_api_url("https://example.org/data.json")
    assert not _looks_like_api_url("https://example.org/reportes/informe-anual.pdf")


def test_looks_like_api_response_uses_content_type_or_body():
    assert _looks_like_api_response("application/json; charset=utf-8", "")
    assert _looks_like_api_response(None, '{"ok": true}')
    assert _looks_like_api_response(None, "[1, 2, 3]")
    assert not _looks_like_api_response("text/html", "<html></html>")


def test_looks_like_doc_response_flags_swagger_and_openapi():
    assert _looks_like_doc_response("text/html", "<title>Swagger UI</title>")
    assert _looks_like_doc_response("application/json", '{"openapi": "3.0.0"}')
    assert not _looks_like_doc_response("text/html", "<html>Bienvenidos a la institución</html>")


def test_scan_html_for_api_links_separates_endpoints_and_docs():
    html = """
    <a href="/api/v1/data">Ver datos</a>
    <a href="/swagger.json">Documentacion de API</a>
    <a href="/reportes/informe.pdf">Informe anual</a>
    """
    result = scan_html_for_api_links(html, "https://example.org")
    endpoint_urls = [e["url"] for e in result["endpoints"]]
    doc_urls = [d["url"] for d in result["documentation"]]
    assert "https://example.org/api/v1/data" in endpoint_urls
    assert "https://example.org/swagger.json" in doc_urls
    assert "https://example.org/reportes/informe.pdf" not in endpoint_urls + doc_urls


def test_scan_network_traffic_for_apis_filters_json_and_api_like_urls():
    responses = [
        {"url": "https://example.org/style.css", "status": 200, "content_type": "text/css"},
        {"url": "https://example.org/api/institutions", "status": 200, "content_type": "application/json"},
        {"url": "https://example.org/img/logo.png", "status": 200, "content_type": "image/png"},
    ]
    result = scan_network_traffic_for_apis(responses)
    urls = [e["url"] for e in result["endpoints"]]
    assert "https://example.org/api/institutions" in urls
    assert "https://example.org/style.css" not in urls
    assert "https://example.org/img/logo.png" not in urls


def test_looks_like_doc_response_ignores_soft_404_html():
    # Bug real que se corrigió: antes cualquier status 200 contaba como "documentación",
    # lo que generaba falsos positivos en sitios que devuelven la portada para toda ruta.
    assert not _looks_like_doc_response("text/html", "<html><body>Bienvenidos a la institución</body></html>")


class _FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class _FakeSession:
    """Simula requests.Session para probar scan_js_bundles_for_api_calls sin red."""

    def __init__(self, scripts: dict):
        self.scripts = scripts
        self.headers: dict = {}

    def get(self, url, timeout=None):
        return self.scripts[url]


def test_scan_js_bundles_finds_fetch_and_axios_calls_but_ignores_templates():
    html = '<script src="/static/main.abc123.js"></script>'
    js_code = (
        'fetch("/api/v1/instituciones").then(r => r.json());'
        'axios.get(`/api/reportes`);'
        'const url = `${PATH_PREFIX}/${lang}/data.json`;'  # placeholder sin resolver: debe ignorarse
    )
    session = _FakeSession({"https://example.org/static/main.abc123.js": _FakeResponse(js_code)})
    result = scan_js_bundles_for_api_calls(html, "https://example.org", session=session)
    urls = [e["url"] for e in result["endpoints"]]
    assert "https://example.org/api/v1/instituciones" in urls
    assert "https://example.org/api/reportes" in urls
    assert not any("${" in u for u in urls)


def test_merge_reports_deduplicates_by_url():
    report = ApiSiteReport(base_url="https://example.org")
    extra_one = {
        "endpoints": [{"url": "https://example.org/api/v1", "status": 200, "content_type": "application/json", "source": "link"}],
        "documentation": [{"url": "https://example.org/swagger.json", "source": "link", "title": "Swagger"}],
    }
    extra_two = {
        "endpoints": [{"url": "https://example.org/api/v1", "status": 200, "content_type": "application/json", "source": "network"}],
        "documentation": [],
    }
    merged = merge_reports(report, extra_one, extra_two)
    assert len(merged.endpoints) == 1
    assert merged.has_api is True
    assert merged.has_documentation is True
