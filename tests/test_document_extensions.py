"""
Pruebas para la enmienda a D-14: Soporte de hojas de cálculo abiertas (.ods) y macros (.xlsm) (Bloque B-46).
Verifica:
1. BaseSourceAdapter incluye .ods y .xlsm por defecto.
2. DiscoveryEngine clasifica .ods y .xlsm como enlaces de descarga.
3. El comparador de benchmark y medición de Fase 2 computan .ods y .xlsm en sus métricas.
"""

from pathlib import Path
import sqlite3
import pytest
from unittest.mock import MagicMock

from crawler.sources.base_adapter import BaseSourceAdapter
from crawler.sources.generic_adapter import GenericSourceAdapter
from crawler.core.discovery import DiscoveryEngine
from crawler.core.fetcher import HttpFetcher
from scripts.comparador_benchmark import contar_documentos_db
from scripts.medir_objetivos_fase2 import DOCUMENT_EXTENSIONS


def test_base_adapter_default_allowed_extensions_includes_ods_and_xlsm():
    # Creamos un adapter con un archivo temporal mínimo
    config_path = Path("config/source_bcb.yaml")
    adapter = GenericSourceAdapter(config_path)
    allowed = set(adapter.allowed_extensions)
    assert "ods" in allowed, "ods debe estar en allowed_extensions del BCB"
    assert "xlsm" in allowed, "xlsm debe estar en allowed_extensions del BCB"
    assert "pdf" in allowed
    assert "xlsx" in allowed


def test_discovery_engine_classifies_ods_and_xlsm_as_downloads():
    adapter = GenericSourceAdapter(Path("config/source_bcb.yaml"))
    fetcher = MagicMock(spec=HttpFetcher)
    discovery = DiscoveryEngine(fetcher, adapter)

    # 1. Enlace .ods directo
    is_dl, ext = discovery._is_download_link("https://www.bcb.gob.bo/webdocs/estadisticas/boletin_2025.ods", "Boletín ODS")
    assert is_dl is True
    assert ext == "ods"

    # 2. Enlace .xlsm directo
    is_dl, ext = discovery._is_download_link("https://www.bcb.gob.bo/webdocs/reportes/modelo_financiero.xlsm", "Modelo XLSM")
    assert is_dl is True
    assert ext == "xlsm"


def test_comparador_benchmark_counts_ods_and_xlsm(tmp_path):
    db_path = tmp_path / "inventory.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE resource_audit_log (
            canonical_url TEXT,
            status TEXT,
            file_size_bytes INTEGER,
            content_sha256 TEXT
        )
    """)
    records = [
        ("https://www.bcb.gob.bo/docs/boletin.pdf", "PROCESADO_EXITOSAMENTE", 1024, "a" * 64),
        ("https://www.bcb.gob.bo/docs/cifras.ods", "PROCESADO_EXITOSAMENTE", 2048, "b" * 64),
        ("https://www.bcb.gob.bo/docs/macros.xlsm", "PROCESADO_EXITOSAMENTE", 4096, "c" * 64),
        ("https://www.bcb.gob.bo/index.html", "PROCESADO_EXITOSAMENTE", 512, "d" * 64),  # No documental
    ]
    cur.executemany("INSERT INTO resource_audit_log VALUES (?, ?, ?, ?)", records)
    conn.commit()
    conn.close()

    total_d14 = contar_documentos_db(db_path, solo_d13=False)
    assert total_d14 == 3, f"Debe contar pdf, ods y xlsm (esperado 3, obtenido {total_d14})"

    total_d13 = contar_documentos_db(db_path, solo_d13=True)
    assert total_d13 == 3, f"Debe contar los 3 con hash y bytes válidos"


def test_medir_objetivos_extensions_includes_ods_and_xlsm():
    assert ".ods" in DOCUMENT_EXTENSIONS, ".ods debe estar en DOCUMENT_EXTENSIONS"
    assert ".xlsm" in DOCUMENT_EXTENSIONS, ".xlsm debe estar en DOCUMENT_EXTENSIONS"
