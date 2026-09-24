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


@pytest.mark.parametrize("portal", ["asfi", "bcb", "ine"])
def test_b52_periodicity_contrasted_against_observed_data(portal):
    """Contrasta la periodicidad declarada contra la evidencia observada en inventory.db (C-3 y C-4)."""
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
            "SELECT canonical_url, period_start, period_end, published_at FROM resource_audit_log WHERE dataset_id = ?",
            (ds_id,)
        ).fetchall()

        if periodicity == "eventual":
            continue

        distinct_months = set()
        distinct_years = set()
        for r in rows:
            dt = r["period_start"] or r["published_at"]
            if dt:
                parts = dt.split("-")
                if len(parts) >= 1:
                    distinct_years.add(int(parts[0]))
                if len(parts) >= 2:
                    distinct_months.add(f"{parts[0]}-{parts[1]}")

        if periodicity == "mensual":
            # C-3: Un dataset mensual debe tener al menos 3 meses distintos observados
            assert len(distinct_months) >= 3, (
                f"Dataset '{ds_id}' en {portal} declarado 'mensual' tiene solo {len(distinct_months)} "
                f"meses distintos observados ({sorted(distinct_months)}). La declaración no coincide con lo observado."
            )
            # Y no puede ser una dispersión vacía en un lapso plurianual
            if distinct_years and (max(distinct_years) - min(distinct_years)) >= 2:
                total_span_months = (max(distinct_years) - min(distinct_years) + 1) * 12
                ratio = len(distinct_months) / total_span_months
                assert ratio >= 0.15, (
                    f"Dataset '{ds_id}' en {portal} declarado 'mensual' tiene solo {len(distinct_months)} "
                    f"meses en {total_span_months} meses de lapso ({ratio:.1%}). Debe declararse 'eventual'."
                )

        elif periodicity == "anual":
            if len(rows) >= 5:
                assert len(distinct_years) >= 2, (
                    f"Dataset '{ds_id}' en {portal} declarado 'anual' tiene menos de 2 años observados."
                )
            # C-2: Un dataset anual no puede ser un cajón de sastre de fallback heterogéneo
            rule_tokens = [t.lower() for t in rule.get("url_patterns", []) + rule.get("title_keywords", [])]
            if rule_tokens and len(rows) >= 30:
                matching_rows = [
                    r for r in rows
                    if any(tok in r["canonical_url"].lower() for tok in rule_tokens)
                ]
                match_ratio = len(matching_rows) / len(rows)
                assert match_ratio >= 0.40, (
                    f"Dataset '{ds_id}' en {portal} declarado 'anual' es el destino de un fallback heterogéneo: "
                    f"solo {len(matching_rows)}/{len(rows)} ({match_ratio:.1%}) coinciden con sus patrones. "
                    f"Debe declararse 'eventual'."
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
