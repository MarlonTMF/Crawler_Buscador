"""
El mapa exportado al prospector interno respeta el contrato ResourceCandidate
sin introducir datos dudosos.

1. period_label solo se emite con confianza alta o media. Las fechas de baja
   confianza salen de carpetas de publicación (cuándo se publicó, no de qué
   período habla) y el DuckDBDiffEngine del interno concilia por período cuando
   un recurso no trae huella de contenido.
2. Una fuente sin inventory.db es un error, no un motivo para exportar otra.
3. Las URLs que la revalidación clasificó como ELIMINADA salen con
   change_status REMOVED, estado que el contrato ya prevé.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from crawler.core.bridge_exporter import BridgeExporter


def _crear_inventario(path: Path, filas):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE resource_audit_log (
        resource_id TEXT, source_id TEXT, dataset_id TEXT, canonical_url TEXT, download_url TEXT,
        status TEXT, content_sha256 TEXT, file_size_bytes INTEGER, period_start TEXT, period_end TEXT,
        date_confidence_score TEXT, error_code TEXT, error_stackTrace TEXT, execution_timestamp TEXT)""")
    conn.executemany("INSERT INTO resource_audit_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", filas)
    conn.commit()
    conn.close()


def _fila(rid, url, p_start, p_end, conf):
    return (rid, "bcb", "ds", url, url, "PROCESADO_EXITOSAMENTE", "a" * 64, 100,
            p_start, p_end, conf, None, None, "2026-10-01T00:00:00")


@pytest.fixture
def bcb(tmp_path):
    db = tmp_path / "output" / "bcb" / "inventory.db"
    _crear_inventario(db, [
        _fila("r-alta", "https://www.bcb.gob.bo/a/2025.pdf", "2025-01-01", "2025-12-31", "high"),
        _fila("r-media", "https://www.bcb.gob.bo/b/jun24.pdf", "2024-01-01", "2024-06-30", "medium"),
        _fila("r-baja", "https://www.bcb.gob.bo/publicaciones/2019/05/17/x.pdf", "2019-05-17", "2019-05-17", "low"),
        _fila("r-borrada", "https://www.bcb.gob.bo/c/viejo.pdf", "2023-01-01", "2023-12-31", "high"),
    ])
    return tmp_path, db


def _recursos(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["resource_key"]: r for r in data["datasets"][0]["resources"]}


def test_period_label_solo_con_confianza_alta_o_media(bcb, tmp_path):
    base, db = bcb
    out = BridgeExporter(output_dir=tmp_path / "bridge").export_from_inventory("bcb", db_path=db)
    r = _recursos(out)
    assert r["r-alta"]["period_label"] is not None
    assert r["r-media"]["period_label"] is not None
    assert r["r-baja"]["period_label"] is None


def test_fuente_sin_inventario_es_error_y_no_exporta_otra(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _crear_inventario(tmp_path / "output" / "finrural" / "inventory.db",
                      [_fila("f1", "https://finrural.org.bo/x.pdf", None, None, "high")])
    with pytest.raises(FileNotFoundError):
        BridgeExporter(output_dir=tmp_path / "bridge").export_from_inventory("ine")


def test_urls_eliminadas_en_la_revalidacion_salen_como_removed(bcb, tmp_path):
    base, db = bcb
    reval = tmp_path / "revalidacion_bcb.json"
    reval.write_text(json.dumps({"results": [
        {"url": "https://www.bcb.gob.bo/c/viejo.pdf", "status": "ELIMINADA"},
        {"url": "https://www.bcb.gob.bo/a/2025.pdf", "status": "VIGENTE"},
    ]}), encoding="utf-8")
    out = BridgeExporter(output_dir=tmp_path / "bridge").export_from_inventory(
        "bcb", db_path=db, revalidation_path=reval)
    r = _recursos(out)
    assert r["r-borrada"]["change_status"] == "REMOVED"
    assert r["r-alta"]["change_status"] == "UNCHANGED"
