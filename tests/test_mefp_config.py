"""
Pruebas de verificación para la configuración y resolución de MEFP (Bloque B-45 / Fase 3).
Verifica:
1. Carga correcta de config/source_mefp.yaml en GenericSourceAdapter con verify_ssl=False.
2. Inclusión de 200.75.171.4 y media.economiayfinanzas.gob.bo en allowed_domains bajo D-01.
3. Respeto de verify_ssl=False en HttpFetcher y AsyncFetcher.
4. Clasificación semántica de datasets de deuda pública, recaudaciones aduaneras y boletines.
5. Descubrimiento de recursos documentales en HTML simulado de MEFP sin exclusión por dominio.
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock

from crawler.sources.generic_adapter import GenericSourceAdapter
from crawler.core.fetcher import HttpFetcher
from crawler.core.async_fetcher import AsyncFetcher
from crawler.core.discovery import DiscoveryEngine


def test_mefp_adapter_configuration():
    config_path = Path("config/source_mefp.yaml")
    assert config_path.exists(), "config/source_mefp.yaml debe existir"

    adapter = GenericSourceAdapter(config_path)

    # 1. verify_ssl debe ser False para MEFP por la cadena de certificados intermedia no verificable
    assert adapter.verify_ssl is False, "MEFP debe tener verify_ssl=False"

    # 2. allowed_domains bajo D-01 debe incluir dominios y la IP del servidor ministerial
    allowed = set(adapter.allowed_domains)
    assert "200.75.171.4" in allowed, "200.75.171.4 debe estar en allowed_domains"
    assert "media.economiayfinanzas.gob.bo" in allowed, "media.economiayfinanzas.gob.bo debe estar en allowed_domains"
    assert "www.economiayfinanzas.gob.bo" in allowed, "www.economiayfinanzas.gob.bo debe estar en allowed_domains"
    assert "economiayfinanzas.gob.bo" in allowed, "economiayfinanzas.gob.bo debe estar en allowed_domains"

    # 3. Semillas clave de MEFP deben estar presentes
    seeds = adapter.seeds
    assert any("deuda_cronogramas_pagos_eta_up" in s for s in seeds), "Semilla de deuda pública ETA/UP debe estar en seeds"
    assert any("recaudaciones-aduaneras-capitulos" in s for s in seeds), "Semilla de aduanas debe estar en seeds"
    assert any("boletines" in s for s in seeds), "Semilla de boletines debe estar en seeds"


def test_http_fetcher_verify_ssl_false():
    fetcher_insecure = HttpFetcher(verify_ssl=False)
    assert fetcher_insecure.session.verify is False
    assert fetcher_insecure.verify_ssl is False

    fetcher_secure = HttpFetcher(verify_ssl=True)
    assert fetcher_secure.session.verify is True
    assert fetcher_secure.verify_ssl is True


def test_async_fetcher_verify_ssl_flag():
    async_insecure = AsyncFetcher(verify_ssl=False)
    assert async_insecure.verify_ssl is False

    async_secure = AsyncFetcher(verify_ssl=True)
    assert async_secure.verify_ssl is True


def test_mefp_dataset_classification():
    adapter = GenericSourceAdapter(Path("config/source_mefp.yaml"))

    # Deuda Pública
    url_deuda = "https://economiayfinanzas.gob.bo/sites/default/files/2025-02/Deuda_P%C3%BAblica_con_Cron__de_las_ETA_y_UP_2023_0.xlsx"
    assert adapter.classify_dataset(url_deuda, "Deuda Pública ETA y UP") == "deuda_publica"

    # Recaudaciones Aduaneras
    url_aduanas = "https://economiayfinanzas.gob.bo/sites/default/files/2025-09/recaudaci%C3%B3n_aduanera_por_capitulo.xlsx"
    assert adapter.classify_dataset(url_aduanas, "Recaudación Aduanera") == "recaudaciones_aduaneras"

    # Boletines
    url_boletin = "https://www.economiayfinanzas.gob.bo/sites/default/files/2026-09/Bolet%C3%ADn%20Estad%C3%ADstico%20primer%20trimestre%202026.pdf"
    assert adapter.classify_dataset(url_boletin, "Boletín Estadístico") == "boletines_estadisticos"


def test_discovery_domain_allowlist_for_mefp_ip_and_subdomains():
    adapter = GenericSourceAdapter(Path("config/source_mefp.yaml"))
    fetcher = MagicMock(spec=HttpFetcher)
    discovery = DiscoveryEngine(fetcher, adapter)

    # Las URLs que Rolando y nosotros encontramos deben ser permitidas por _is_allowed_domain
    assert discovery._is_allowed_domain("https://200.75.171.4/sites/default/files/2025-02/Deuda_2023.xlsx") is True
    assert discovery._is_allowed_domain("https://media.economiayfinanzas.gob.bo/boletines") is True
    assert discovery._is_allowed_domain("https://www.economiayfinanzas.gob.bo/index.php/viceministerios/vtcp") is True
    assert discovery._is_allowed_domain("https://economiayfinanzas.gob.bo/sites/default/files/doc.xlsx") is True

    # Dominios externos no autorizados deben rechazarse
    assert discovery._is_allowed_domain("https://external-hack.com/doc.xlsx") is False
    assert discovery._is_allowed_domain("https://google.com") is False


def test_discovery_extracts_mefp_xlsx_documents():
    adapter = GenericSourceAdapter(Path("config/source_mefp.yaml"))
    fetcher = MagicMock(spec=HttpFetcher)

    html_debt_page = """
    <html>
      <body>
        <h1>Deuda Pública Subnacional y Universidades</h1>
        <div class="content">
          <a href="https://200.75.171.4/sites/default/files/2025-02/Deuda_P%C3%BAblica_con_Cron__de_las_ETA_y_UP_2023_0.xlsx">
            Deuda Pública con Cronogramas de Pagos de las ETA y UP 2023
          </a>
          <a href="https://economiayfinanzas.gob.bo/sites/default/files/2022-09/Deuda_P%C3%BAblica_con_Cron__de_las_ETA_y_UP_2018.xlsx">
            Deuda Pública 2018
          </a>
          <a href="https://media.economiayfinanzas.gob.bo/boletines">Enlace a boletines</a>
        </div>
      </body>
    </html>
    """
    fetcher.fetch_html.return_value = (True, 200, html_debt_page)

    discovery = DiscoveryEngine(fetcher, adapter)
    seed = "https://www.economiayfinanzas.gob.bo/index.php/viceministerios/vtcp/deuda_cronogramas_pagos_eta_up_ultima_gestion"
    adapter.config["crawl"]["seeds"] = [seed]
    adapter.config["crawl"]["use_wayback"] = False
    adapter.config["crawl"]["use_sitemaps"] = False
    candidates = discovery.discover_from_seeds()

    # Se deben descubrir los 2 candidatos XLSX
    urls_candidatos = [c.url for c in candidates]
    assert any("200.75.171.4" in u and "2023_0.xlsx" in u for u in urls_candidatos)
    assert any("economiayfinanzas.gob.bo" in u and "2018.xlsx" in u for u in urls_candidatos)
