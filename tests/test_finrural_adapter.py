"""
Pruebas unitarias para el adaptador de fuente FinruralAdapter.
"""

from pathlib import Path
from crawler.sources.finrural_adapter import FinruralAdapter


def test_finrural_adapter():
    adapter = FinruralAdapter()

    # 1. Comprobar fuente e id
    assert adapter.source_id == "finrural"
    assert adapter.source_name == "FINRURAL"
    assert adapter.base_url == "https://www.finrural.org.bo"

    # 2. Comprobar exclusión de URLs no deseadas
    assert adapter.is_url_excluded("https://www.finrural.org.bo/historia/") is True
    assert adapter.is_url_excluded("https://www.finrural.org.bo/mision-y-vision/") is True
    assert adapter.is_url_excluded("https://www.finrural.org.bo/reporte-financiero-mensual/") is False

    # 3. Comprobar clasificación de dataset
    ds_mensual = adapter.classify_dataset("https://www.finrural.org.bo/reporte-financiero-mensual-instituciones-financieras-de-desarrollo/")
    assert ds_mensual == "reporte_financiero_mensual"

    ds_historico = adapter.classify_dataset("https://www.finrural.org.bo/archivo-historico/")
    assert ds_historico == "archivo_historico"

    # 4. Comprobar coincidencia de patrón de archivo
    match_res = adapter.match_filename_pattern("https://www.finrural.org.bo/archivos/info_financiera/2025/financiera_05_2025.pdf")
    assert match_res is not None
    assert match_res["month"] == "05"
    assert match_res["year"] == "2025"
