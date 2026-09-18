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
