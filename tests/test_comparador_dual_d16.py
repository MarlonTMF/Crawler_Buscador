"""
tests/test_comparador_dual_d16.py
==================================
Pruebas unitarias para la métrica dual del comparador bajo Decisión D-16 (B-48).
Verifica:
1. Deduplicación canónica de parámetros espurios de tracking/caché (?x16877, utm_*, etc.).
2. Unificación de contenedores redundantes (.pdf/.zip con idéntico stem).
3. Conteo de documentos únicos en base SQLite.
4. Generación de tabla comparativa dual D-16 (bruto vs único).
5. Desinflado verificado del caso FINRURAL (reversión de la falsa derrota).
"""

import json
from pathlib import Path
import sqlite3
import pytest

from scripts.diff_brecha_rolando import deduplicar_recursos_d16
from scripts.comparador_benchmark import (
    contar_documentos_unicos_d16,
    formatear_markdown,
    generar_comparativa,
)


def test_deduplicar_recursos_d16_tracking_params():
    urls = [
        "https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf",
        "https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf?x16877=",
        "https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf?utm_source=twitter&utm_medium=cpc",
        "https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf?fbclid=IwAR123",
        "https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf?gclid=XYZ789",
    ]
    unicos = deduplicar_recursos_d16(urls)
    assert len(unicos) == 1


def test_deduplicar_recursos_d16_redundant_containers():
    urls = [
        "https://www.finrural.org.bo/archivos/info_financiera/2023/financiera_05_2023.pdf",
        "https://www.finrural.org.bo/archivos/info_financiera/2023/financiera_05_2023.zip",
        "https://www.finrural.org.bo/archivos/info_financiera/2023/financiera_05_2023.pdf?x16877=",
        "https://www.finrural.org.bo/archivos/info_financiera/2023/financiera_06_2023.pdf",
    ]
    unicos = deduplicar_recursos_d16(urls)
    # financiera_05 (en pdf, zip y con tracking) es 1 documento, y financiera_06 es otro -> total 2
    assert len(unicos) == 2


def test_contar_documentos_unicos_d16_sqlite(tmp_path):
    db_file = tmp_path / "inventory.db"
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE resource_audit_log (
            resource_id TEXT PRIMARY KEY,
            canonical_url TEXT,
            status TEXT,
            file_size_bytes INTEGER
        )
    """)
    # Tripla redundante para un mismo archivo
    cur.execute("INSERT INTO resource_audit_log VALUES ('1', 'https://a.com/docs/reporte_01.pdf', 'PROCESADO_EXITOSAMENTE', 1000)")
    cur.execute("INSERT INTO resource_audit_log VALUES ('2', 'https://a.com/docs/reporte_01.zip', 'PROCESADO_EXITOSAMENTE', 950)")
    cur.execute("INSERT INTO resource_audit_log VALUES ('3', 'https://a.com/docs/reporte_01.pdf?x16877=', 'RECUPERADO_VIA_CONTINGENCIA', 1000)")
    
    # Otro archivo distinto
    cur.execute("INSERT INTO resource_audit_log VALUES ('4', 'https://a.com/docs/reporte_02.xlsx', 'PROCESADO_EXITOSAMENTE', 2500)")
    
    # HTML sin extensión (debe excluirse por D-14)
    cur.execute("INSERT INTO resource_audit_log VALUES ('5', 'https://a.com/seccion/indices/', 'PROCESADO_EXITOSAMENTE', 400)")

    # Archivo con error (debe excluirse por status)
    cur.execute("INSERT INTO resource_audit_log VALUES ('6', 'https://a.com/docs/reporte_03.pdf', 'ERROR', 0)")

    conn.commit()
    conn.close()

    count_unicos = contar_documentos_unicos_d16(db_file)
    # reporte_01 (1) + reporte_02 (1) = 2 documentos únicos
    assert count_unicos == 2


def test_formatear_markdown_dual_d16():
    mock_rows = [
        {
            "portal": "finrural",
            "douglas": 0,
            "rolando": 562,
            "rolando_d16": 240,
            "nosotros_sep": 5,
            "nosotros_baseline": 129,
            "nosotros_actual": 241,
            "nosotros_d13": 240,
            "nosotros_d16": 241,
            "delta_vs_baseline": 112,
            "delta_d16": 1,
            "gana_a_rolando_actual": False,
            "gana_a_rolando_d16": True,
        },
        {
            "portal": "mefp",
            "douglas": 0,
            "rolando": 7,
            "rolando_d16": 12,
            "nosotros_sep": 0,
            "nosotros_baseline": 0,
            "nosotros_actual": 56,
            "nosotros_d13": 56,
            "nosotros_d16": 55,
            "delta_vs_baseline": 56,
            "delta_d16": 43,
            "gana_a_rolando_actual": True,
            "gana_a_rolando_d16": True,
        }
    ]

    md_dual = formatear_markdown(mock_rows, dual_d16=True)
    assert "Rolando Bruto" in md_dual
    assert "Rolando (D-16)" in md_dual
    assert "Nosotros (D-16)" in md_dual
    assert "Δ Único D-16" in md_dual
    assert "GANADO (+1)" in md_dual
    assert "GANADO (+43)" in md_dual


def test_finrural_desinflado_real_d16():
    finrural_json = Path("Elecciones De Crawler por URL/Rolando/extracted/output/finrural_indicadores.json")
    if not finrural_json.exists():
        pytest.skip("Dump de Rolando finrural no disponible")

    from scripts.diff_brecha_rolando import extraer_recursos_rolando
    recursos = extraer_recursos_rolando(finrural_json)
    urls = [r["url_descarga"] for r in recursos if "url_descarga" in r]
    
    total_bruto = len(urls)
    assert total_bruto == 583, f"Esperadas 583 URLs en dump bruto de Rolando, obtenidas {total_bruto}"

    unicos_d16 = deduplicar_recursos_d16(urls)
    assert len(unicos_d16) == 240, f"Esperados 240 únicos bajo D-16 para Rolando, obtenidos {len(unicos_d16)}"
