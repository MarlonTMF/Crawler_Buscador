"""
tests/test_reporte_cobertura.py
===============================
Suite de pruebas unitarias para scripts/reporte_cobertura.py (B-26).

Verifica la medición reproducible de Track A y Track B según la Decisión D-04,
tanto contra datos sintéticos aislados (mocks) como contra el repositorio real.
"""

import json
from pathlib import Path
import sqlite3
import pytest

from scripts.reporte_cobertura import (
    calcular_track_a,
    calcular_track_b,
    formatear_reporte_texto,
    formatear_reporte_markdown,
    main,
)


def test_calcular_track_a_catalogo_inexistente(tmp_path):
    falso_catalogo = tmp_path / "inexistente.json"
    with pytest.raises(FileNotFoundError):
        calcular_track_a(falso_catalogo)


def test_calcular_track_a_con_datos_mock(tmp_path):
    mock_catalog = [
        {"Fuente": "F1", "HTTP_Status": "200", "crawler_source": "f1"},
        {"Fuente": "F2", "HTTP_Status": "200", "crawler_source": "f1"},
        {"Fuente": "F3", "HTTP_Status": "403_CLOUDFLARE_BLOCKED", "Error_Detail": "Requiere Headless"},
        {"Fuente": "F4", "HTTP_Status": "410", "Error_Detail": "Extinta"},
    ]
    cat_file = tmp_path / "mock_catalog.json"
    cat_file.write_text(json.dumps(mock_catalog), encoding="utf-8")

    res = calcular_track_a(cat_file)
    assert res["total_registros"] == 4
    assert res["http_200_simple"] == 2
    assert res["headless_requerido"] == 1
    assert res["verificadas_accesibles"] == 3
    assert res["pct_verificadas_accesibles"] == 75.0
    assert res["exclusiones_documentadas"] == 1
    assert res["total_clasificado"] == 4
    assert res["pct_total_clasificado"] == 100.0
    assert res["entradas_con_crawler_source"] == 2
    assert res["fuentes_unicas_en_catalogo"] == 1
    assert len(res["detalle_no_200"]) == 2


def test_calcular_track_b_con_db_mock(tmp_path):
    source_dir = tmp_path / "fuente_test"
    source_dir.mkdir()
    db_file = source_dir / "inventory.db"

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE resource_audit_log (
            resource_id TEXT PRIMARY KEY,
            source_id TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            download_url TEXT,
            status TEXT,
            file_size_bytes INTEGER
        )
    """)
    # Insertar 3 items: 2 con URLs unicas exitosas, 1 duplicado, 1 error
    cur.execute(
        "INSERT INTO resource_audit_log VALUES ('1', 'fuente_test', 'ds_1', 'http://a/1', 'http://a/1', 'PROCESADO_EXITOSAMENTE', 1024)"
    )
    cur.execute(
        "INSERT INTO resource_audit_log VALUES ('2', 'fuente_test', 'ds_1', 'http://a/1', 'http://a/1', 'PROCESADO_EXITOSAMENTE', 1024)"
    )
    cur.execute(
        "INSERT INTO resource_audit_log VALUES ('3', 'fuente_test', 'ds_2', 'http://a/2', 'http://a/2', 'PROCESADO_EXITOSAMENTE', 2048)"
    )
    cur.execute(
        "INSERT INTO resource_audit_log VALUES ('4', 'fuente_test', 'ds_2', 'http://a/3', 'http://a/3', 'FAILED_FETCH', 0)"
    )
    conn.commit()
    conn.close()

    res = calcular_track_b(tmp_path)
    assert res["total_fuentes_escaneadas"] == 1
    assert res["fuentes_onboardeadas_activas"] == 1
    assert res["filas_totales_db"] == 4
    assert res["recursos_unicos"] == 2
    assert res["total_datasets"] == 2
    assert res["total_bytes"] == 4096
    assert res["fuentes"][0]["pipeline_errors"] == 1


def test_calcular_track_a_con_catalogo_real():
    catalog_path = Path("output/excel_urls_diagnostic.json")
    assert catalog_path.exists(), "El catálogo maestro debe existir en output/"

    res = calcular_track_a(catalog_path)
    assert res["total_registros"] == 67
    assert res["http_200_simple"] == 62
    assert res["headless_requerido"] == 2
    assert res["verificadas_accesibles"] == 64
    assert res["pct_verificadas_accesibles"] == 95.52
    assert res["exclusiones_documentadas"] == 3
    assert res["pct_exclusiones_documentadas"] == 4.48
    assert res["total_clasificado"] == 67
    assert res["pct_total_clasificado"] == 100.0
    assert res["entradas_con_crawler_source"] == 33
    assert res["fuentes_unicas_en_catalogo"] == 26


def test_calcular_track_b_con_output_real():
    output_dir = Path("output")
    assert output_dir.exists(), "El directorio output/ debe existir"

    res = calcular_track_b(output_dir)
    assert res["fuentes_onboardeadas_activas"] >= 26
    assert res["recursos_unicos"] >= 2611
    assert res["filas_totales_db"] >= 2633
    assert res["total_datasets"] >= 59
    assert res["total_mb"] > 600.0


def test_formatear_reporte_texto_y_markdown():
    mock_track_a = {
        "total_registros": 67,
        "http_200_simple": 62,
        "pct_http_200_simple": 92.54,
        "headless_requerido": 2,
        "pct_headless_requerido": 2.99,
        "verificadas_accesibles": 64,
        "pct_verificadas_accesibles": 95.52,
        "exclusiones_documentadas": 3,
        "pct_exclusiones_documentadas": 4.48,
        "total_clasificado": 67,
        "pct_total_clasificado": 100.0,
        "entradas_con_crawler_source": 33,
        "pct_entradas_con_crawler_source": 49.25,
        "fuentes_unicas_en_catalogo": 26,
        "detalle_no_200": [
            {
                "fuente": "BCP",
                "status": "403_CLOUDFLARE_BLOCKED",
                "tipo": "ACCESIBLE_VIA_HEADLESS",
                "detalle": "WAF",
            }
        ],
    }
    mock_track_b = {
        "total_fuentes_escaneadas": 1,
        "fuentes_onboardeadas_activas": 1,
        "fuentes_sin_documentos": 0,
        "filas_totales_db": 10,
        "recursos_unicos": 10,
        "total_datasets": 1,
        "total_bytes": 1024,
        "total_mb": 0.0,
        "fuentes": [
            {
                "fuente": "test_source",
                "filas_totales": 10,
                "recursos_unicos": 10,
                "datasets_count": 1,
                "tamano_mb": 0.0,
                "estado": "OK",
            }
        ],
    }

    txt = formatear_reporte_texto(mock_track_a, mock_track_b, "2026-09-18 12:00:00")
    assert "TRACK A" in txt
    assert "TRACK B" in txt
    assert "D-04" in txt
    assert "95.52%" in txt

    md = formatear_reporte_markdown(mock_track_a, mock_track_b, "2026-09-18 12:00:00")
    assert "# Reporte Consolidado de Cobertura" in md
    assert "| **Verificadas y Accesibles** |" in md
    assert "| `test_source` |" in md


def test_cli_json_y_output_file(tmp_path):
    report_file = tmp_path / "cobertura.json"
    exit_code = main(["--format", "json", "--output", str(report_file)])
    assert exit_code == 0
    assert report_file.exists()

    data = json.load(open(report_file, "r", encoding="utf-8"))
    assert data["criterio"] == "D-04 (Track A y Track B medidos por separado)"
    assert data["track_a"]["verificadas_accesibles"] == 64
    assert data["track_b"]["recursos_unicos"] >= 2611


def test_cli_strict_exito_y_fallo(tmp_path):
    # 1. En entorno real debe salir 0
    exit_code_ok = main(["--strict"])
    assert exit_code_ok == 0

    # 2. Con catálogo insuficiente debe fallar
    mock_cat = [{"Fuente": "X", "HTTP_Status": "500"}]
    cat_file = tmp_path / "bad_catalog.json"
    cat_file.write_text(json.dumps(mock_cat), encoding="utf-8")

    exit_code_fail = main(["--catalog", str(cat_file), "--strict"])
    assert exit_code_fail == 1
