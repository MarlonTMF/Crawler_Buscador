"""
Pruebas para B-51: Clasificación de datasets y extracción de fechas de INE.
Verifica que ningún dataset concentre > 40% y que las fechas reales se resuelvan.
"""

import sqlite3
from pathlib import Path
from crawler.core.extractor import MetadataExtractor
from crawler.core.fetcher import HttpFetcher
from crawler.sources.generic_adapter import GenericSourceAdapter


def test_b51_ine_dataset_concentration_under_40():
    """Criterio de aceptación B-51: Ningún dataset de INE concentra más del 40% de las filas."""
    adapter = GenericSourceAdapter(Path("config/source_ine.yaml"))
    db_path = Path("output/ine/inventory.db")
    if not db_path.exists():
        import pytest
        pytest.skip("falta output/ine/inventory.db")

    con = sqlite3.connect(db_path)
    urls = [r[0] for r in con.execute("SELECT canonical_url FROM resource_audit_log").fetchall()]
    total = len(urls)
    assert total > 0

    counts = {}
    for u in urls:
        ds_id = adapter.classify_dataset(u)
        counts[ds_id] = counts.get(ds_id, 0) + 1

    for ds_id, count in counts.items():
        pct = (count / total) * 100
        assert pct <= 40.0, f"Dataset '{ds_id}' concentra {pct:.1f}% ({count}/{total}), superando el 40% permitido"


def test_b51_ine_date_patterns():
    """Verifica resolución de patrones de fecha de INE y subsanación de O-1 y O-2 de B-50."""
    adapter = GenericSourceAdapter(Path("config/source_ine.yaml"))
    extractor = MetadataExtractor(HttpFetcher(), adapter)

    # 1. Rango 8 dígitos AAAA-AAAA pegados (ej. 19902014)
    res1 = extractor.extract_date_layer1_url(
        "https://www.ine.gob.bo/index.php/descarga/405/matrices/44573/matriz-de-19902014.xlsx"
    )
    assert res1 is not None
    assert res1.period_start == "1990-01-01"
    assert res1.period_end == "2014-12-31"

    # 2. Carpeta con año en INE (ej. /informes-auditoria-interna-2021/)
    res2 = extractor.extract_date_layer1_url(
        "https://www.ine.gob.bo/index.php/descarga/611/informes-auditoria-interna-2021/54040/resumen.pdf"
    )
    assert res2 is not None
    assert res2.published_at == "2021-01-01"

    # 3. O-1: Mes con espacio o guión (ej. "Bancos Múltiples 04_2026.pdf")
    res3 = extractor.extract_date_layer1_url(
        "https://www.asfi.gob.bo/sites/default/files/2026-05/Bancos%20M%C3%BAltiples%2004_2026.pdf"
    )
    assert res3 is not None
    assert res3.period_start == "2026-04-01"
    assert res3.period_end == "2026-04-30"

    # 4. O-1: "DD de mes de AAAA"
    res4 = extractor.extract_date_layer1_url(
        "https://www.asfi.gob.bo/sites/default/files/2025-07/Decreto%20Supremo%20N%C2%B0%204247%20de%20fecha%2028%20de%20mayo%20de%202020.pdf"
    )
    assert res4 is not None
    assert res4.period_start == "2020-05-28"

    # 5. O-2: Fallback de año suelto debe tener method 'url_year_fallback'
    res5 = extractor.extract_date_layer1_url(
        "https://www.bcb.gob.bo/webdocs/Otros/Cronograma_anual_de_publicaciones_2026.xlsx"
    )
    assert res5 is not None
    assert res5.period_start == "2026-01-01"
    assert res5.method == "url_year_fallback"
