"""
Pruebas para B-52: Periodicidad declarada y tolerancia por dataset en ASFI, BCB e INE.
Verifica que todos los datasets tengan periodicidad y tolerancia válidas,
contrastadas contra los datos observados en inventory.db (Regla D-06).
"""

import pytest
import sqlite3
import yaml
from pathlib import Path
from crawler.core.extractor import MetadataExtractor
from crawler.core.fetcher import HttpFetcher
from crawler.core.control_db import ControlDatabase
from crawler.sources.generic_adapter import GenericSourceAdapter

VALID_PERIODICITIES = {
    "diaria",
    "semanal",
    "mensual",
    "trimestral",
    "semestral",
    "anual",
    "eventual",
}


@pytest.mark.parametrize("portal", ["asfi", "bcb", "ine"])
def test_b52_all_datasets_have_periodicity_and_tolerance(portal):
    """Criterio de aceptación B-52: Todos los datasets deben tener periodicidad y tolerancia declaradas."""
    cfg_path = Path(f"config/source_{portal}.yaml")
    assert cfg_path.exists(), f"No existe archivo de configuración: {cfg_path}"

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    rules = cfg.get("classification", {}).get("dataset_rules", [])
    assert len(rules) > 0, f"No hay dataset_rules en {portal}"

    for r in rules:
        ds_id = r.get("id")
        periodicity = r.get("periodicity")
        tolerance = r.get("tolerance")

        assert periodicity is not None, f"Dataset '{ds_id}' en {portal} no tiene 'periodicity' declarada"
        assert periodicity in VALID_PERIODICITIES, (
            f"Dataset '{ds_id}' en {portal} tiene periodicidad inválida '{periodicity}'. "
            f"Debe ser una de: {sorted(VALID_PERIODICITIES)}"
        )
        assert tolerance is not None, f"Dataset '{ds_id}' en {portal} no tiene 'tolerance' declarada"
        assert isinstance(tolerance, int) and tolerance >= 0, (
            f"Dataset '{ds_id}' en {portal} tiene tolerancia inválida: {tolerance} (debe ser int >= 0)"
        )


def test_b52_periodicity_contrasted_against_observed_data():
    """Contrasta la periodicidad declarada contra la evidencia observada en inventory.db."""
    for portal in ["asfi", "bcb", "ine"]:
        cfg_path = Path(f"config/source_{portal}.yaml")
        db_path = Path(f"output/{portal}/inventory.db")
        if not db_path.exists():
            pytest.skip(f"No existe base de datos: {db_path}")

        adapter = GenericSourceAdapter(cfg_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        for rule in adapter.dataset_rules:
            ds_id = rule.get("id")
            periodicity = rule.get("periodicity")
            rows = conn.execute(
                "SELECT period_start, period_end FROM resource_audit_log WHERE dataset_id = ?",
                (ds_id,)
            ).fetchall()

            # Si está declarado mensual, debe tener evidencia de meses observados si tiene suficientes docs
            if periodicity == "mensual" and len(rows) >= 10:
                monthly_docs = [
                    r for r in rows
                    if r["period_start"] and r["period_end"]
                    and r["period_start"][:7] == r["period_end"][:7]
                    and r["period_start"][-2:] == "01"
                ]
                assert len(monthly_docs) > 0, (
                    f"Dataset '{ds_id}' declarado mensual en {portal} no tiene ningún documento con período mensual"
                )


def test_b52_subsanacion_o1_separador_doble_mes():
    """Subsanación O-1 (de B-51): Nombres de archivo con separadores dobles deben extraer el mes y no caer a anual."""
    adapter = GenericSourceAdapter(Path("config/source_asfi.yaml"))
    extractor = MetadataExtractor(HttpFetcher(), adapter)

    # Caso 1: Marzo__2026 con doble guion bajo
    res1 = extractor.extract_date_layer1_url(
        "https://www.asfi.gob.bo/sites/default/files/2026-05/Boletin%20Trimestral%20-%20Marzo__2026.zip#Marzo__2026.xlsx"
    )
    assert res1 is not None
    assert res1.period_start == "2026-03-01"
    assert res1.period_end == "2026-03-31"

    # Caso 2: Diciembre__2024 con doble guion bajo
    res2 = extractor.extract_date_layer1_url(
        "https://www.asfi.gob.bo/sites/default/files/2025-01/bolet%C3%ADn%20-%20diciembre__2024.xlsx"
    )
    assert res2 is not None
    assert res2.period_start == "2024-12-01"
    assert res2.period_end == "2024-12-31"


def test_b52_subsanacion_o2_persistencia_date_method(tmp_path):
    """Subsanación O-2 (de B-51): resource_audit_log debe persistir date_method."""
    db_file = tmp_path / "test_inventory.db"
    db = ControlDatabase(db_file)
    db.initialize()

    cursor = db.conn.execute("PRAGMA table_info(resource_audit_log)")
    cols = [r[1] for r in cursor.fetchall()]
    assert "date_method" in cols, "Columna 'date_method' no encontrada en resource_audit_log"
