"""
Pruebas para el Escalón 4 sobre el motor CDX de Wayback Machine (B-63).
Verifica:
1. query_cdx_snapshots en wayback_engine consulta la API CDX con timeout >= 15 y cache.
2. Escalón 4 en RecoveryLadder opera sin condicionales cableados por portal/dataset (P-4).
3. Marca el recurso recuperado como procedente del archivo histórico.
4. Caso negativo cuando CDX no retorna snapshots o no coinciden con el período.
"""

from unittest.mock import MagicMock, patch
import pytest
from crawler.core import wayback_engine
from crawler.core.recovery_ladder import RecoveryLadder, RecoveryRung, RecoveredPeriod


class DummyCdxResp:
    def __init__(self, rows=None, status_code=200):
        self.status_code = status_code
        self._rows = rows or [
            ["original", "timestamp", "statuscode", "mimetype"],
            ["https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun24.pdf", "20251223160024", "200", "application/pdf"],
            ["https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic24.pdf", "20260115120000", "200", "application/pdf"],
        ]

    def json(self):
        return self._rows

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def test_wayback_engine_query_cdx_snapshots(monkeypatch):
    """Verifica que wayback_engine consulte CDX con timeout >= 15 y devuelva snapshots estructurados."""
    called_args = {}

    def mock_get(url, params=None, timeout=None):
        called_args["url"] = url
        called_args["params"] = params
        called_args["timeout"] = timeout
        return DummyCdxResp()

    monkeypatch.setattr(wayback_engine.requests, "get", mock_get)

    snapshots = wayback_engine.query_cdx_snapshots(
        "www.bcb.gob.bo/webdocs/informes_deudaexterna/*", timeout=15, cache_ttl=0
    )

    assert called_args["timeout"] >= 15
    assert "cdx" in called_args["url"]
    assert called_args["params"]["filter"] == "statuscode:200"
    assert len(snapshots) == 2
    snap = snapshots[0]
    assert snap["original"] == "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun24.pdf"
    assert snap["timestamp"] == "20251223160024"
    assert "web.archive.org/web/20251223160024" in snap["snapshot_url"]


def test_rung_4_generic_no_hardcoding(monkeypatch):
    """Verifica que el Escalón 4 use el motor CDX para cualquier dataset sin condicionales cableados."""
    ladder = RecoveryLadder()

    # Simulamos snapshots CDX para ine/auditoria_interna (dataset sin hardcoding previo)
    mock_snapshots = [
        {
            "original": "https://www.ine.gob.bo/index.php/descarga/auditoria_interna_2016.pdf",
            "timestamp": "20170510120000",
            "statuscode": "200",
            "mimetype": "application/pdf",
            "snapshot_url": "https://web.archive.org/web/20170510120000/https://www.ine.gob.bo/index.php/descarga/auditoria_interna_2016.pdf",
        }
    ]

    monkeypatch.setattr(ladder, "_get_dataset_cdx_snapshots", lambda portal, ds_id: mock_snapshots)
    monkeypatch.setattr(ladder, "fetch_and_verify", lambda url: (10240, "sha256dummy"))
    monkeypatch.setattr(ladder, "_verify_institution_content", lambda portal, content: True)
    monkeypatch.setattr(ladder, "_check_quality_gates", lambda p, d, per, u, sha, r: (True, ""))

    rec = ladder._try_rung_4_wayback_archive(
        portal="ine",
        dataset_id="auditoria_interna",
        period="2016",
        periodicity="anual",
    )

    assert rec is not None
    assert rec.recovery_rung == RecoveryRung.RUNG_4_WAYBACK_ARCHIVE
    assert rec.metadata.get("is_historical_archive") is True
    assert "web.archive.org" in rec.url
    assert rec.period == "2016"


def test_rung_4_negative_case_when_no_match(monkeypatch):
    """Verifica que el Escalón 4 devuelva None cuando no hay snapshots para el período."""
    ladder = RecoveryLadder()

    mock_snapshots = [
        {
            "original": "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun24.pdf",
            "timestamp": "20251223160024",
            "statuscode": "200",
            "mimetype": "application/pdf",
            "snapshot_url": "https://web.archive.org/web/20251223160024/DEPEX%20jun24.pdf",
        }
    ]

    monkeypatch.setattr(ladder, "_get_dataset_cdx_snapshots", lambda portal, ds_id: mock_snapshots)

    # Buscamos un período que no está en los snapshots
    rec = ladder._try_rung_4_wayback_archive(
        portal="bcb",
        dataset_id="deuda_externa",
        period="2022-S2",
        periodicity="semestral",
    )

    assert rec is None


def test_get_dataset_cdx_pattern_inference():
    """Verifica que el patrón de consulta CDX se infiera correctamente sin condicionales cableados."""
    ladder = RecoveryLadder()

    # bcb/deuda_externa desde inventory.db
    pat_bcb = ladder._get_dataset_cdx_pattern("bcb", "deuda_externa")
    assert "bcb.gob.bo" in pat_bcb
    assert pat_bcb.endswith("/*")

    # asfi/poa_seguimiento desde inventory.db
    pat_asfi = ladder._get_dataset_cdx_pattern("asfi", "poa_seguimiento")
    assert "asfi.gob.bo" in pat_asfi
    assert pat_asfi.endswith("/*")


def test_snapshot_matches_period_all_periodicities():
    """Verifica el filtrado de snapshots por período a través de anual, semestral, trimestral y mensual."""
    ladder = RecoveryLadder()

    # Anual
    snap_anual = {"original": "https://www.ine.gob.bo/descarga/cuadro-2015.xlsx"}
    assert ladder._snapshot_matches_period(snap_anual, "2015", "anual") is True
    assert ladder._snapshot_matches_period(snap_anual, "2016", "anual") is False

    # Semestral
    snap_sem1 = {"original": "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun24.pdf"}
    snap_sem2 = {"original": "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic24.pdf"}
    assert ladder._snapshot_matches_period(snap_sem1, "2024-S1", "semestral") is True
    assert ladder._snapshot_matches_period(snap_sem1, "2024-S2", "semestral") is False
    assert ladder._snapshot_matches_period(snap_sem2, "2024-S2", "semestral") is True

    # Trimestral
    snap_q1 = {"original": "https://www.asfi.gob.bo/files/Seguimiento%20al%20POA%20primer%20trimestre%202026.pdf"}
    snap_q2 = {"original": "https://www.asfi.gob.bo/files/Seguimiento%20al%20POA%20segundo%20trimestre%202026.pdf"}
    assert ladder._snapshot_matches_period(snap_q1, "2026-Q1", "trimestral") is True
    assert ladder._snapshot_matches_period(snap_q1, "2026-Q2", "trimestral") is False
    assert ladder._snapshot_matches_period(snap_q2, "2026-Q2", "trimestral") is True

    # Mensual
    snap_m11 = {"original": "https://www.asfi.gob.bo/files/Balance%20General%20nov%202025.pdf"}
    assert ladder._snapshot_matches_period(snap_m11, "2025-11", "mensual") is True
    assert ladder._snapshot_matches_period(snap_m11, "2025-12", "mensual") is False
