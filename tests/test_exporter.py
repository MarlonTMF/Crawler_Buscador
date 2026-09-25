"""
Pruebas unitarias para la exportación multi-formato (Estandarizado, Árbol BCB, IA Compacto).
"""

import json
import pytest
from pathlib import Path
from crawler.core.models import (
    SourceInfo, CrawlRunInfo, ResourceMetadata, ResourceEvidence,
    ResourceItem, DatasetItem, ExternalSourceMap
)
from crawler.core.exporter import MultiFormatExporter


def test_multi_format_export(tmp_path: Path):
    source_map = ExternalSourceMap(
        schema_version="1.0.0",
        source=SourceInfo(
            id="finrural",
            name="FINRURAL",
            base_url="https://www.finrural.org.bo"
        ),
        crawl_run=CrawlRunInfo(
            id="crawl_test_456",
            started_at="2026-08-10T11:00:00Z",
            finished_at="2026-08-10T11:00:05Z",
            status="success"
        ),
        datasets=[
            DatasetItem(
                id="reporte_financiero_mensual",
                name="Reporte Financiero Mensual",
                source_url="https://www.finrural.org.bo/reporte-financiero-mensual/",
                periodicity="monthly",
                resources=[
                    ResourceItem(
                        id="finrural:reporte_financiero_mensual:2026-01:pdf",
                        title="Información Financiera Enero 2026",
                        url_origin="https://www.finrural.org.bo/reporte-financiero-mensual/",
                        download_url="https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf",
                        canonical_url="https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf",
                        file_type="pdf",
                        period_start="2026-01-01",
                        period_end="2026-01-31",
                        retrieved_at="2026-08-10T11:00:05Z",
                        metadata=ResourceMetadata(
                            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                            date_extraction_method="url_pattern",
                            date_confidence="high"
                        )
                    )
                ]
            )
        ]
    )

    exporter = MultiFormatExporter(output_dir=tmp_path)

    # 1. Exportar Estándar
    std_file = exporter.export_standard(source_map, "test_std.json")
    assert std_file.exists()
    with open(std_file, "r", encoding="utf-8") as f:
        std_data = json.load(f)
    assert std_data["schema_version"] == "1.0.0"

    # 2. Exportar Árbol Jerárquico BCB
    tree_file = exporter.export_tree_format(source_map, "test_tree.json")
    assert tree_file.exists()
    with open(tree_file, "r", encoding="utf-8") as f:
        tree_data = json.load(f)

    # Verificar jerarquía de 5 niveles y sufijo .csv
    assert "FINRURAL" in tree_data
    assert "Reporte_Financiero_Mensual" in tree_data["FINRURAL"]
    assert "Gestion_2026" in tree_data["FINRURAL"]["Reporte_Financiero_Mensual"]
    leaf_entry = tree_data["FINRURAL"]["Reporte_Financiero_Mensual"]["Gestion_2026"]["REPORTE_MENSUAL"]
    csv_key = list(leaf_entry.keys())[0]
    assert csv_key.endswith(".csv")
    assert leaf_entry[csv_key]["url_descarga"] == "https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf"
    assert leaf_entry[csv_key]["descripcion"] == "Información Financiera Enero 2026"

    # 3. Exportar IA Compacto
    compact_file = exporter.export_compact_ai(source_map, "test_compact.json")
    assert compact_file.exists()
    with open(compact_file, "r", encoding="utf-8") as f:
        compact_data = json.load(f)
    assert isinstance(compact_data, list)
    assert len(compact_data) == 1
    assert compact_data[0]["resource_id"] == "finrural:reporte_financiero_mensual:2026-01:pdf"


def test_export_resource_candidates(tmp_path: Path):
    """Prueba unitaria para export_resource_candidates (B-57 / D-19 / C-4 / C-8)."""
    import sqlite3
    db_path = tmp_path / "inventory.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE resource_audit_log (
            canonical_url TEXT PRIMARY KEY,
            download_url TEXT,
            content_sha256 TEXT,
            file_size_bytes INTEGER,
            period_start TEXT,
            period_end TEXT,
            date_confidence_score TEXT,
            status TEXT
        )
    """)
    cur.execute("""
        INSERT INTO resource_audit_log VALUES (
            'https://www.asfi.gob.bo/docs/rep_2026_01.pdf',
            'https://www.asfi.gob.bo/docs/rep_2026_01.pdf',
            'sha256_mock_123',
            1048576,
            '2026-01-01',
            '2026-01-31',
            'high',
            'PROCESADO_EXITOSAMENTE'
        )
    """)
    cur.execute("""
        INSERT INTO resource_audit_log VALUES (
            'https://www.asfi.gob.bo/docs/multi_2021_2025.pdf',
            'https://www.asfi.gob.bo/docs/multi_2021_2025.pdf',
            NULL,
            0,
            '2021-01-01',
            '2025-12-31',
            'low',
            'PROCESADO_EXITOSAMENTE'
        )
    """)
    conn.commit()
    conn.close()

    exporter = MultiFormatExporter(output_dir=tmp_path)
    out_file = exporter.export_resource_candidates(source_id="asfi", db_path=db_path)

    assert out_file.exists()
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_records"] == 2
    assert data["verification_summary"]["VERIFICADO_CON_HASH"] == 1
    assert data["verification_summary"]["CATALOGADO_SIN_BYTES"] == 1
    assert data["period_summary"]["CON_ETIQUETA_CANONICA"] == 1
    assert data["period_summary"]["SIN_ETIQUETA"] == 1
    assert data["period_summary"]["motivos_omision"]["RANGO_MULTIANUAL"] == 1

    cands = data["candidates"]
    assert cands[0]["period_label"] == "2026-01"
    assert cands[0]["verification_status"] == "VERIFICADO_CON_HASH"
    assert cands[1]["period_label"] is None  # C-4: Prohibido centinela
    assert cands[1]["verification_status"] == "CATALOGADO_SIN_BYTES"

