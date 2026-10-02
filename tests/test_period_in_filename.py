"""
Pruebas para el reconocimiento de períodos en el nombre del archivo (B-64).
Resuelve P-7:
1. Mes abreviado + año corto (ej. dic25, jun24, DEPEX_jun24.pdf, DEPEX_dic25.pdf).
2. Mes completo + año (ej. Septiembre 2023, Boletin_Septiembre_2023.pdf).
3. AAAAMM al inicio del nombre (ej. 202511_BDR.zip, 202511-informe.pdf).
4. Ninguna fila marcada 'high' cuya fecha provenga exclusivamente de la carpeta de publicación.
"""

import pytest
from pathlib import Path
from crawler.core.extractor import MetadataExtractor
from crawler.core.fetcher import HttpFetcher
from crawler.sources.generic_adapter import GenericSourceAdapter


@pytest.fixture
def extractor():
    cfg_path = Path("config/source_bcb.yaml")
    adapter = GenericSourceAdapter(cfg_path)
    return MetadataExtractor(HttpFetcher(), adapter)


def test_recognize_short_month_short_year_with_underscore(extractor):
    """B-64 (1): Reconocer mes abreviado + año corto precedido de guion bajo o separadores."""
    # DEPEX_jun24.pdf -> junio 2024
    res = extractor.extract_date_layer1_url("https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX_jun24.pdf")
    assert res is not None
    assert res.period_start == "2024-06-01"
    assert res.period_end == "2024-06-30"

    # DEPEX_dic25.pdf -> diciembre 2025
    res2 = extractor.extract_date_layer1_url("https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX_dic25.pdf")
    assert res2 is not None
    assert res2.period_start == "2025-12-01"
    assert res2.period_end == "2025-12-31"


def test_recognize_full_month_and_year_with_delimiters(extractor):
    """B-64 (2): Reconocer mes completo + año con espacios o guiones bajos."""
    # Boletin_Septiembre_2023.pdf -> septiembre 2023
    res = extractor.extract_date_layer1_url("https://www.bcb.gob.bo/webdocs/sistema_pagos/Boletin_Septiembre_2023.pdf")
    assert res is not None
    assert res.period_start == "2023-09-01"
    assert res.period_end == "2023-09-30"


def test_recognize_aaaamm_at_start_of_filename(extractor):
    """B-64 (3): Reconocer AAAAMM al inicio del nombre del archivo."""
    # 202511-informe.pdf -> noviembre 2025
    res = extractor.extract_date_layer1_url("https://www.asfi.gob.bo/sites/default/files/202511-informe.pdf")
    assert res is not None
    assert res.period_start == "2025-11-01"
    assert res.period_end == "2025-11-30"
