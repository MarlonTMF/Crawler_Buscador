"""
Pruebas unitarias para la canonicalización de URLs y generación de resource_keys.
"""

from pathlib import Path
from crawler.sources.finrural_adapter import FinruralAdapter
from crawler.core.canonicalizer import Canonicalizer


def test_url_canonicalization_and_resource_key():
    adapter = FinruralAdapter()
    canonicalizer = Canonicalizer(adapter)

    # 1. Probar remoción de query params como x16877 y utm_source
    raw_url = "https://www.finrural.org.bo/archivos/info_financiera/2025/financiera_05_2025.pdf?x16877&utm_source=test#section"
    canonical_url = canonicalizer.canonicalize_url(raw_url)

    assert canonical_url == "https://www.finrural.org.bo/archivos/info_financiera/2025/financiera_05_2025.pdf"

    # 2. Probar generación de resource_key estable con período
    key_with_period = canonicalizer.generate_resource_key(
        source_id="finrural",
        dataset_id="reporte_financiero_mensual",
        period_end="2025-05-31",
        file_type="pdf",
        canonical_url=canonical_url
    )

    assert key_with_period == "finrural:reporte_financiero_mensual:2025-05:pdf"

    # 3. Probar generación de resource_key fallback sin período
    key_no_period = canonicalizer.generate_resource_key(
        source_id="finrural",
        dataset_id="reporte_financiero_mensual",
        period_end=None,
        file_type="pdf",
        canonical_url=canonical_url
    )

    assert key_no_period == "finrural:reporte_financiero_mensual:financiera_05_2025:pdf"
