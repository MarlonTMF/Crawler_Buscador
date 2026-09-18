from crawler.core.url_resolver import (
    GENERIC_INSTITUTION_WORDS,
    _clean_html_to_text,
    _content_verify,
    _is_spa_shell,
    _tokenize_institution_name,
    resolve_dead_domain,
)


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class FakeFetcher:
    """Simula HttpFetcher para probar resolve_dead_domain sin red real."""

    def __init__(self, verdict, generate_content_response=None, reachable_urls=None):
        self._verdict = verdict
        self._generate_content_response = generate_content_response
        self._reachable_urls = reachable_urls or set()

    def _ask_gemini_for_url_verdict(self, url, failed_candidates=None):
        return self._verdict

    def _generate_gemini_content(self, prompt):
        return self._generate_content_response

    def probe_url_variant(self, candidate):
        reachable = candidate in self._reachable_urls
        return {"url": candidate, "reachable": reachable, "status": 200 if reachable else 0}

    def _generate_url_variants(self, url):
        # Variante mínima: solo agrega/quita "www." para simular el motor real.
        if url.startswith("https://www."):
            return [url, "https://" + url[len("https://www."):]]
        return [url, "https://www." + url[len("https://"):]]


def test_tokenize_institution_name_strips_accents_and_generic_words_stay():
    tokens = _tokenize_institution_name("Cámara de Exportadores de Cochabamba", "CADEXCO")
    assert "cochabamba" in tokens
    assert "exportadores" in tokens
    assert "de" not in tokens  # muy corto, se filtra por longitud


def test_generic_words_are_flagged_for_filtering():
    tokens = [t for t in _tokenize_institution_name("Cámara de Exportadores de Cochabamba", "CADEXCO")
              if t not in GENERIC_INSTITUTION_WORDS]
    # "camara" y "exportadores" son genéricos (cualquier cámara los usa); lo
    # distintivo de ESTA institución es su acrónimo y la ciudad.
    assert tokens == ["cadexco", "cochabamba"]
    assert "camara" not in tokens
    assert "exportadores" not in tokens


def test_content_verify_rejects_wrong_city_same_acronym_family():
    # Caso real: cadex.org responde 200 pero es la Cámara de Santa Cruz, no Cochabamba.
    html = "<html><body>Cadex - Cámara de Exportadores de Santa Cruz</body></html>"
    keywords = ["cochabamba"]
    assert _content_verify(html, keywords) == []


def test_content_verify_accepts_matching_institution():
    html = "<html><body>NAABOL - Navegación Aérea y Aeropuertos Bolivianos</body></html>"
    matched = _content_verify(html, ["naabol", "aeropuertos"])
    assert "naabol" in matched


def test_is_spa_shell_detects_angular_shell():
    assert _is_spa_shell('<html><body><app-root></app-root></body></html>')
    assert not _is_spa_shell("<html><body>" + "contenido real " * 100 + "</body></html>")


def test_clean_html_to_text_strips_scripts_and_accents():
    html = "<html><body><script>evil()</script>Información</body></html>"
    text = _clean_html_to_text(html)
    assert "evil" not in text
    assert "informacion" in text


def test_resolve_dead_domain_recovers_via_mechanical_variant(monkeypatch):
    # Gemini sugiere una URL que no existe (".gob.bo"); el motor de variantes
    # encuentra la real (".org.bo") -- el caso FAM real que motivó este pipeline.
    verdict = {
        "status": "moved", "best_url": "https://fam.gob.bo/",
        "reason": "Migró a dominio gubernamental.", "alternatives": [],
    }
    fetcher = FakeFetcher(verdict, reachable_urls={"https://fam.gob.bo/", "https://www.fam.gob.bo/"})
    # Ajustamos el motor de variantes fake para que devuelva también la URL real:
    def variants(url):
        return [url, "https://fam.org.bo/"]
    fetcher._generate_url_variants = variants
    fetcher.probe_url_variant = lambda c: {"url": c, "reachable": c == "https://fam.org.bo/", "status": 200 if c == "https://fam.org.bo/" else 0}

    def fake_get(url, timeout=None, headers=None):
        assert url == "https://fam.org.bo/"
        return FakeResponse("<html><body>Federación de Asociaciones Municipales</body></html>")

    monkeypatch.setattr("crawler.core.url_resolver.requests.get", fake_get)

    result = resolve_dead_domain(fetcher, "FAM", "Federación de Asociaciones Municipales de Bolivia", "https://www.fam.bo")

    assert result["resolution"]["status"] == "resolved"
    assert result["resolution"]["resolved_url"] == "https://fam.org.bo/"
    assert result["ai_queries"][0]["response"] == verdict  # respuesta cruda de la IA queda registrada


def test_resolve_dead_domain_marks_dissolved_when_no_successor(monkeypatch):
    verdict = {"status": "not_found", "best_url": None, "reason": "Cesó operaciones.", "alternatives": []}
    successor_json = '{"successor_name": null, "successor_url": null, "reason": "Sin sucesor claro."}'
    fetcher = FakeFetcher(verdict, generate_content_response=successor_json)

    result = resolve_dead_domain(fetcher, "BOLCEREALES", "Bolcereales", "https://www.bolsadecereales.org.bo")

    assert result["resolution"]["status"] == "dissolved_no_successor"
    assert result["resolution"]["resolved_url"] is None
    assert any(q["kind"] == "successor_query" for q in result["ai_queries"])
