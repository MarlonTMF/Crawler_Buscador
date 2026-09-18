"""
tests/test_correr_lote.py
=========================
Pruebas unitarias para scripts/correr_lote.py (Etapa C / B-13).
"""

import sqlite3
from pathlib import Path
import pytest

from scripts.correr_lote import (
    resolve_source_configs,
    inspect_inventory_db,
    generate_markdown_report,
)


def test_resolve_source_configs(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    (cfg_dir / "source_finrural.yaml").write_text("source: {id: finrural}", encoding="utf-8")
    (cfg_dir / "source_bbv.yaml").write_text("source: {id: bbv}", encoding="utf-8")

    # 1. Resolver por nombre
    resolved = resolve_source_configs(["finrural", "bbv"], cfg_dir)
    assert len(resolved) == 2
    assert resolved[0][0] == "finrural"
    assert resolved[0][1] == cfg_dir / "source_finrural.yaml"
    assert resolved[1][0] == "bbv"
    assert resolved[1][1] == cfg_dir / "source_bbv.yaml"

    # 2. Fuente no existente
    resolved_none = resolve_source_configs(["inexistente"], cfg_dir)
    assert len(resolved_none) == 1
    assert resolved_none[0][1] is None

    # 3. 'all'
    resolved_all = resolve_source_configs(["all"], cfg_dir)
    assert len(resolved_all) == 2
    ids = {r[0] for r in resolved_all}
    assert ids == {"finrural", "bbv"}


def test_inspect_inventory_db(tmp_path: Path):
    db_path = tmp_path / "inventory.db"

    # No existe
    res_none = inspect_inventory_db(db_path)
    assert res_none["exists"] is False
    assert res_none["total_records"] == 0

    # Crear tabla y cargar registros sintéticos
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE resource_audit_log (
            resource_id TEXT PRIMARY KEY,
            source_id TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            download_url TEXT,
            status TEXT,
            error_code TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO resource_audit_log VALUES ('r1', 'finrural', 'ds1', 'https://ex.com/doc.pdf', 'https://ex.com/doc.pdf', 'PROCESADO_EXITOSAMENTE', NULL)"
    )
    conn.execute(
        "INSERT INTO resource_audit_log VALUES ('r2', 'finrural', 'ds1', 'https://ex.com/data.xlsx', 'https://ex.com/data.xlsx', 'PROCESADO_EXITOSAMENTE', NULL)"
    )
    conn.execute(
        "INSERT INTO resource_audit_log VALUES ('r3', 'finrural', 'ds2', 'https://ex.com/err.pdf', 'https://ex.com/err.pdf', 'ERROR', 'HTTP_404')"
    )
    conn.commit()
    conn.close()

    metrics = inspect_inventory_db(db_path)
    assert metrics["exists"] is True
    assert metrics["total_records"] == 3
    assert metrics["status_counts"]["PROCESADO_EXITOSAMENTE"] == 2
    assert metrics["status_counts"]["ERROR"] == 1
    assert metrics["error_counts"]["HTTP_404"] == 1
    assert metrics["extension_counts"][".pdf"] == 2
    assert metrics["extension_counts"][".xlsx"] == 1
    assert metrics["dataset_counts"]["ds1"] == 2
    assert metrics["dataset_counts"]["ds2"] == 1


def test_generate_markdown_report(tmp_path: Path):
    batch_meta = {
        "started_at": "2026-09-18T10:00:00Z",
        "finished_at": "2026-09-18T10:05:00Z",
        "total_duration_seconds": 300.0,
        "log_file_relative": "output/reportes_lotes/lote_test.log",
    }
    results = [
        {
            "source_id": "finrural",
            "institution": "FINRURAL",
            "base_url": "https://www.finrural.org.bo",
            "config_path": "config/source_finrural.yaml",
            "adapter_class": "FinruralAdapter",
            "adapter_name": "FINRURAL",
            "use_playwright": False,
            "success": True,
            "duration_seconds": 120.0,
            "resources_processed": 180,
            "resources_error": 0,
            "inventory_db_path": "output/finrural/inventory.db",
            "map_json_path": "output/finrural/mapa_finrural.json",
            "db_metrics": {
                "total_records": 180,
                "status_counts": {"PROCESADO_EXITOSAMENTE": 180},
                "error_counts": {},
                "extension_counts": {".pdf": 150, ".xlsx": 30},
                "dataset_counts": {"reporte_financiero_mensual": 180},
            },
        }
    ]

    report_path = tmp_path / "reporte.md"
    report_text = generate_markdown_report(batch_meta, results, report_path)

    assert report_path.exists()
    assert "# Reporte de Ejecución por Lotes" in report_text
    assert "finrural" in report_text
    assert "180" in report_text
    assert "✅ APROBADO (Criterio cumplido)" in report_text
