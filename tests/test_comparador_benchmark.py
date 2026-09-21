"""
tests/test_comparador_benchmark.py
==================================
Pruebas unitarias y de integración para scripts/comparador_benchmark.py (B-39).
"""

import json
from pathlib import Path
import sqlite3
import pytest

from scripts.comparador_benchmark import (
    PORTALES_BENCHMARK_MAP,
    BASELINE_20260919,
    cargar_benchmark,
    contar_documentos_db,
    generar_comparativa,
    formatear_markdown,
    verificar_reproducibilidad,
)


def test_cargar_benchmark_mock(tmp_path):
    mock_data = [
        {"code": "senamhi", "douglas_resources": 0, "rolando_archivos": 0, "mio_resources": 0},
        {"code": "asfi", "douglas_resources": 0, "rolando_archivos": 139, "mio_resources": 53},
        {"code": "asfi_bcb", "douglas_resources": 13, "rolando_archivos": 524, "mio_resources": 103},
        {"code": "asfi_finrural", "douglas_resources": 0, "rolando_archivos": 1606, "mio_resources": 53},
        {"code": "asfi_valores", "douglas_resources": 0, "rolando_archivos": 153, "mio_resources": 53},
    ]
    p = tmp_path / "bench.json"
    p.write_text(json.dumps(mock_data), encoding="utf-8")

    bench = cargar_benchmark(p)
    assert "senamhi" in bench
    assert bench["senamhi"]["douglas"] == 0
    assert bench["senamhi"]["rolando"] == 0
    assert bench["senamhi"]["nosotros_sep"] == 0

    assert "asfi" in bench
    assert bench["asfi"]["douglas"] == 13
    assert bench["asfi"]["rolando"] == 2422
    assert bench["asfi"]["nosotros_sep"] == 103


def test_contar_documentos_db_criterio_d14(tmp_path):
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
    # 2 PDF validos
    cur.execute("INSERT INTO resource_audit_log VALUES ('1', 'http://a.com/doc.pdf', 'PROCESADO_EXITOSAMENTE', 1000)")
    cur.execute("INSERT INTO resource_audit_log VALUES ('2', 'http://a.com/data.xlsx', 'RECUPERADO_VIA_CONTINGENCIA', 2000)")
    # 1 HTML sin extension (D-14 debe excluirlo)
    cur.execute("INSERT INTO resource_audit_log VALUES ('3', 'http://a.com/informacion-financiera-2/', 'PROCESADO_EXITOSAMENTE', 500)")
    # 1 PDF con error
    cur.execute("INSERT INTO resource_audit_log VALUES ('4', 'http://a.com/err.pdf', 'ERROR', 0)")
    conn.commit()
    conn.close()

    count = contar_documentos_db(db_file)
    assert count == 2


def test_verificar_reproducibilidad_fallo():
    bad_rows = [
        {"portal": "senamhi", "douglas": 0, "rolando": 0, "nosotros_sep": 0, "nosotros_baseline": 798, "nosotros_actual": 500},
    ]
    valido, errores = verificar_reproducibilidad(bad_rows)
    assert not valido
    assert len(errores) > 0


def test_integracion_reproducibilidad_real():
    output_dir = Path("output")
    bench_file = Path("Elecciones De Crawler por URL/merged_final.json")

    if not bench_file.exists() or not output_dir.exists():
        pytest.skip("Archivos de repositorio no disponibles para prueba de integracion")

    rows = generar_comparativa(output_dir, bench_file)
    valido, errores = verificar_reproducibilidad(rows)
    assert valido, f"Fallo de reproducibilidad: {errores}"

    # Validar que los 22 portales estan presentes
    assert len(rows) == 22
    assert set(r["portal"] for r in rows) == set(PORTALES_BENCHMARK_MAP.keys())

    # Validar totales consolidados
    tot_d = sum(r["douglas"] for r in rows)
    tot_r = sum(r["rolando"] for r in rows)
    tot_b = sum(r["nosotros_baseline"] for r in rows)
    tot_a = sum(r["nosotros_actual"] for r in rows)

    assert tot_d == 70
    assert tot_r == 5403
    assert tot_b == 1864
    assert tot_a >= 5400  # Con la calibracion de Fase 2 superamos a Rolando (actual 5411)
