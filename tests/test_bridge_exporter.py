"""
Pruebas unitarias para BridgeExporter (Integración directa con prospector_interno y DuckDB).
"""

from pathlib import Path
import sqlite3
import json
import pytest
import duckdb

from crawler.core.bridge_exporter import BridgeExporter


@pytest.fixture
def mock_inventory_db(tmp_path: Path) -> Path:
    """Crea una base de datos SQLite con esquema resource_audit_log para pruebas."""
    db_file = tmp_path / "mock_inventory.db"
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
            content_sha256 TEXT,
            file_size_bytes INTEGER,
            period_start TEXT,
            period_end TEXT,
            date_confidence_score TEXT,
            error_code TEXT,
            error_stackTrace TEXT,
            execution_timestamp TEXT
        )
    """)
    # Insertar 2 recursos exitosos y 1 recuperado por contingencia
    cur.executemany("""
        INSERT INTO resource_audit_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            "finrural:test:doc1:pdf", "finrural", "boletines",
            "https://finrural.org.bo/doc1.pdf", "https://finrural.org.bo/doc1.pdf",
            "PROCESADO_EXITOSAMENTE", "sha256_mock_1", 1024,
            "2024-01-01", "2024-01-31", "high", None, None, "2026-09-25T10:00:00"
        ),
        (
            "finrural:test:doc2:xlsx", "finrural", "estadisticas",
            "https://finrural.org.bo/doc2.xlsx", "https://finrural.org.bo/doc2.xlsx",
            "PROCESADO_EXITOSAMENTE", "sha256_mock_2", 2048,
            "2024-02-01", "2024-02-28", "high", None, None, "2026-09-25T10:00:00"
        ),
        (
            "finrural:test:doc3:pdf", "finrural", "historico",
            "http://spvs.gov.bo/doc3.pdf", "https://asfi.gob.bo/doc3.pdf",
            "RECUPERADO_VIA_CONTINGENCIA", "sha256_mock_3", 4096,
            None, None, "unknown", None, None, "2026-09-25T10:00:00"
        ),
        (
            "finrural:test:doc_err:pdf", "finrural", "fallidos",
            "https://finrural.org.bo/error.pdf", None,
            "ERROR", None, 0, None, None, "unknown", "404", "Not Found", "2026-09-25T10:00:00"
        ),
    ])
    conn.commit()
    conn.close()
    return db_file


def test_export_from_inventory(mock_inventory_db: Path, tmp_path: Path):
    out_file = tmp_path / "bridge_map.json"
    exporter = BridgeExporter(output_dir=tmp_path)

    res = exporter.export_from_inventory(
        source_id="finrural",
        db_path=mock_inventory_db,
        output_path=out_file,
    )

    assert res.exists()
    with open(res, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["source"]["id"] == "finrural"
    assert "run_id" in data["run"]
    assert len(data["datasets"]) == 1
    # 3 registros válidos (ignora ERROR)
    assert len(data["datasets"][0]["resources"]) == 3

    # Verificar que el recuperado tiene status NEW
    recup = next(r for r in data["datasets"][0]["resources"] if r["resource_key"] == "finrural:test:doc3:pdf")
    assert recup["change_status"] == "NEW"
    assert recup["file_extension"] == ".pdf"
    assert recup["content_length_bytes"] == 4096


def test_duckdb_compatibility(mock_inventory_db: Path, tmp_path: Path):
    out_file = tmp_path / "bridge_duckdb.json"
    exporter = BridgeExporter(output_dir=tmp_path)
    exporter.export_from_inventory(
        source_id="finrural",
        db_path=mock_inventory_db,
        output_path=out_file,
    )

    # Ejecutar la consulta exacta que ejecuta DuckDBDiffEngine
    con = duckdb.connect(":memory:")
    posix_path = out_file.resolve().as_posix()
    q = f"""
        SELECT
            source.id AS source_id,
            run.run_id AS run_id,
            unnest(datasets[1].resources) AS r
        FROM read_json_auto('{posix_path}')
    """
    rows = con.execute(q).fetchall()
    assert len(rows) == 3
    source_id, run_id, r = rows[0]
    assert source_id == "finrural"
    assert "resource_key" in r
    assert "url" in r
    assert "file_extension" in r
    assert "content_type" in r


def test_export_from_diagnostic(tmp_path: Path):
    diag_file = tmp_path / "sample_diag.json"
    sample_data = [
        {
            "Fuente": "FINRURAL",
            "crawler_source": "finrural",
            "Document_Evidence": {
                "samples": [
                    {"url": "https://finrural.org.bo/boletin1.pdf", "title": "Boletin 1"},
                    {"url": "https://finrural.org.bo/boletin2.xlsx", "title": "Boletin 2"}
                ]
            }
        }
    ]
    diag_file.write_text(json.dumps(sample_data), encoding="utf-8")

    out_file = tmp_path / "diag_bridge.json"
    exporter = BridgeExporter(output_dir=tmp_path)
    res = exporter.export_from_diagnostic(diagnostic_path=diag_file, output_path=out_file, source_filter="finrural")

    assert res.exists()
    with open(res, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["datasets"][0]["resources"]) == 2
