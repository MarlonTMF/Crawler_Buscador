"""
src/crawler/core/internal_reconciler.py
=======================================
Motor de conciliación y cotejo de catálogo entre el crawler externo y el catálogo interno.
Implementa las condiciones C-1 a C-10 y la Decisión D-19 (B-57).

Principios clave:
1. Clave de cotejo en 3 pasadas (C-1):
   - Pasada 1: Identidad primaria por URL canónica normalizada.
   - Comparación de contenido (hash) y período sobre emparejados.
   - Pasada 2: Detección de URL_CAMBIADA por hash idéntico en URLs no emparejadas.
   - Pasada 3: SOLO_EXTERNO y SOLO_INTERNO para el remanente.
2. Formato canónico de period_label y validador estricto sin centinelas (C-4).
3. Compuerta de confianza (C-5): DISCORDANCIA_PERIODO exige confianza >= medium en ambos lados.
4. Umbral de clave no validada (C-3): < 10% de coincidencia en el lado menor marca CLAVE_NO_VALIDADA.
5. Invariante de totalidad probada por aserción (C-10).
"""

from __future__ import annotations

import calendar
from datetime import date
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from crawler.core.canonicalizer import Canonicalizer

logger = logging.getLogger(__name__)

# Categorías cerradas según C-10 / D-19
CATEGORIAS_VALIDAS: List[str] = [
    "CONFIRMADO",
    "SOLO_EXTERNO",
    "SOLO_INTERNO",
    "DISCORDANCIA_PERIODO",
    "DISCORDANCIA_CONTENIDO",
    "URL_CAMBIADA",
    "INDETERMINADO_POR_DATO_AUSENTE",
    "INDETERMINADO_POR_CONFIANZA",
    "CLAVE_NO_VALIDADA",
]

# Expresión regular para validar period_label canónico (C-4)
# Solo admite: YYYY-MM-DD (diaria), YYYY-MM (mensual), YYYY-Qn (trimestral), YYYY-Sn (semestral), YYYY (anual)
PERIOD_LABEL_REGEX = re.compile(
    r"^(\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4}-Q[1-4]|\d{4}-S[1-2]|\d{4})$"
)


def is_valid_period_label(label: Optional[str]) -> bool:
    """Valida si una etiqueta de período cumple con el formato canónico estricto (C-4)."""
    if not label or not isinstance(label, str):
        return False
    return bool(PERIOD_LABEL_REGEX.match(label.strip()))


def build_period_label(
    period_start: Optional[str],
    period_end: Optional[str],
    periodicity: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Traduce (period_start, period_end) a una etiqueta canónica period_label bajo C-4.

    Reglas:
    1. Se emite etiqueta solo si el par coincide exactamente con un cubo canónico.
    2. Rango multianual o período no canónico omite el campo (devuelve None con motivo).
    3. PROHIBIDO todo valor centinela ('SIN_PERIODO', 'unknown', ''). El retorno es None.

    Returns:
        (period_label, omission_reason)
    """
    if not period_start or not period_end:
        return None, "SIN_PERIODO"

    s_str = period_start.strip()
    e_str = period_end.strip()

    try:
        s_date = date.fromisoformat(s_str[:10])
        e_date = date.fromisoformat(e_str[:10])
    except (ValueError, TypeError):
        return None, "FORMATO_INVALIDO"

    if s_date > e_date:
        return None, "FECHAS_INVALIDAS"

    # Multianual
    if e_date.year > s_date.year:
        return None, "RANGO_MULTIANUAL"

    year = s_date.year

    # 1. Diaria: s_date == e_date
    if s_date == e_date:
        return s_date.isoformat(), None

    # 2. Anual: 01-01 a 12-31 del mismo año
    if s_date.month == 1 and s_date.day == 1 and e_date.month == 12 and e_date.day == 31:
        return str(year), None

    # 3. Mensual: primer y último día del mismo mes
    last_day_month = calendar.monthrange(year, s_date.month)[1]
    if (
        s_date.month == e_date.month
        and s_date.day == 1
        and e_date.day == last_day_month
    ):
        return f"{year:04d}-{s_date.month:02d}", None

    # 4. Trimestral
    quarter_cubes = [
        (1, 1, 3, 31, "Q1"),
        (4, 1, 6, 30, "Q2"),
        (7, 1, 9, 30, "Q3"),
        (10, 1, 12, 31, "Q4"),
    ]
    for sm, sd, em, ed, q_name in quarter_cubes:
        if (
            s_date.month == sm
            and s_date.day == sd
            and e_date.month == em
            and e_date.day == ed
        ):
            return f"{year}-{q_name}", None

    # 5. Semestral
    semester_cubes = [
        (1, 1, 6, 30, "S1"),
        (7, 1, 12, 31, "S2"),
    ]
    for sm, sd, em, ed, s_name in semester_cubes:
        if (
            s_date.month == sm
            and s_date.day == sd
            and e_date.month == em
            and e_date.day == ed
        ):
            return f"{year}-{s_name}", None

    return None, "CUBO_NO_CANONICO"


class InternalReconciler:
    """Conciliador de catálogos en 3 pasadas (C-1 a C-10)."""

    def __init__(self):
        self.portal_status: Dict[str, str] = {}
        self.total_entities_classified: int = 0
        self.duplicate_urls_ext: int = 0
        self.duplicate_urls_int: int = 0
        self._hook_before_assert = None

    def reconcile(
        self,
        portal: str,
        external_items: List[Dict[str, Any]],
        internal_items: List[Dict[str, Any]],
        min_match_rate: float = 0.10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Ejecuta la reconciliación entre la lista externa y la interna para un portal.
        """
        results: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in CATEGORIAS_VALIDAS}
        self.duplicate_urls_ext = 0
        self.duplicate_urls_int = 0
        self.total_entities_classified = 0

        # Preparar registros con URLs canónicas usando una sola normalización (C-7)
        ext_records = []
        for idx, it in enumerate(external_items):
            raw_u = it.get("url") or it.get("canonical_url") or it.get("download_url") or ""
            c_u = Canonicalizer.canonicalize(raw_u) if raw_u else ""
            raw_p = it.get("period_label")
            # C-4 / H-3: Validador estricto sin centinelas
            valid_p = str(raw_p).strip() if (raw_p and is_valid_period_label(str(raw_p))) else None

            ext_records.append({
                "rec_id": f"ext_{idx}",
                "url": c_u or raw_u or f"ext_unknown_{idx}",
                "canon_url": c_u,
                "content_hash": it.get("content_hash") or it.get("content_sha256") or None,
                "period_label": valid_p,
                "confidence": (it.get("confidence") or it.get("date_confidence_score") or "unknown").lower(),
                "data": it,
            })

        int_records = []
        for idx, it in enumerate(internal_items):
            raw_u = it.get("url") or it.get("url_descarga") or it.get("canonical_url") or ""
            c_u = Canonicalizer.canonicalize(raw_u) if raw_u else ""
            # H-3: NUNCA derivar período de fecha_actualizacion (es fecha de crawl/publicación, no de cobertura)
            raw_p = it.get("period_label")
            valid_p = str(raw_p).strip() if (raw_p and is_valid_period_label(str(raw_p))) else None

            int_records.append({
                "rec_id": f"int_{idx}",
                "url": c_u or raw_u or f"int_unknown_{idx}",
                "canon_url": c_u,
                "content_hash": it.get("content_hash") or it.get("sha256") or None,
                "period_label": valid_p,
                "confidence": (it.get("confidence") or it.get("date_confidence_score") or "unknown").lower(),
                "data": it,
            })

        # Indexar registros por canon_url y auditar duplicados antes de C-3 (H-5)
        ext_by_url: Dict[str, List[Dict[str, Any]]] = {}
        for r in ext_records:
            if r["canon_url"]:
                ext_by_url.setdefault(r["canon_url"], []).append(r)

        int_by_url: Dict[str, List[Dict[str, Any]]] = {}
        for r in int_records:
            if r["canon_url"]:
                int_by_url.setdefault(r["canon_url"], []).append(r)

        self.duplicate_urls_ext = sum(len(l) - 1 for l in ext_by_url.values() if len(l) > 1)
        self.duplicate_urls_int = sum(len(l) - 1 for l in int_by_url.values() if len(l) > 1)

        # Evaluar tasa de coincidencia (C-3)
        valid_ext_urls = {r["canon_url"] for r in ext_records if r["canon_url"]}
        valid_int_urls = {r["canon_url"] for r in int_records if r["canon_url"]}
        common_urls = valid_ext_urls.intersection(valid_int_urls)
        unkeyed_ext = sum(1 for r in ext_records if not r["canon_url"])
        unkeyed_int = sum(1 for r in int_records if not r["canon_url"])

        smaller_side = min(len(valid_ext_urls), len(valid_int_urls)) if (valid_ext_urls and valid_int_urls) else 0
        match_rate = len(common_urls) / smaller_side if smaller_side > 0 else 0.0

        # Si match_rate < min_match_rate y tenemos datos en ambos lados, se declara CLAVE_NO_VALIDADA (C-3)
        if smaller_side > 0 and match_rate < min_match_rate:
            self.portal_status[portal] = "CLAVE_NO_VALIDADA"
            # Agrupar entidades en CLAVE_NO_VALIDADA preservando totalidad (C-10)
            seen_canon: Set[str] = set()
            all_entities = []

            # Entidades compartidas por URL
            for cu in common_urls:
                seen_canon.add(cu)
                all_entities.append({"url": cu, "reason": "COINCIDENCIA_BAJO_UMBRAL", "portal": portal})

            for r in ext_records:
                if not r["canon_url"] or r["canon_url"] not in seen_canon:
                    all_entities.append({"url": r["url"], "origin": "externo", "portal": portal})
                    if r["canon_url"]:
                        seen_canon.add(r["canon_url"])

            for r in int_records:
                if not r["canon_url"] or r["canon_url"] not in seen_canon:
                    all_entities.append({"url": r["url"], "origin": "interno", "portal": portal})
                    if r["canon_url"]:
                        seen_canon.add(r["canon_url"])

            results["CLAVE_NO_VALIDADA"] = all_entities
            self.total_entities_classified = len(all_entities)
            # H-2: Aserción contra el tamaño real de la unión calculada independientemente
            expected_union_c3 = len(valid_ext_urls | valid_int_urls) + unkeyed_ext + unkeyed_int
            assert len(all_entities) == expected_union_c3, (
                f"C-10 invariante violada en CLAVE_NO_VALIDADA: clasificados {len(all_entities)} != unión {expected_union_c3}"
            )
            return results

        self.portal_status[portal] = "VALIDADA"

        matched_ext_ids: Set[str] = set()
        matched_int_ids: Set[str] = set()

        # PASADA 1: Identidad primaria por URL canónica normalizada (C-1)
        for canon_url in common_urls:
            ext_list = ext_by_url[canon_url]
            int_list = int_by_url[canon_url]

            # Tomar el primer par representativo para la URL
            ext_r = ext_list[0]
            int_r = int_list[0]

            for e in ext_list:
                matched_ext_ids.add(e["rec_id"])
            for i in int_list:
                matched_int_ids.add(i["rec_id"])

            ext_h = ext_r["content_hash"]
            int_h = int_r["content_hash"]
            ext_p = ext_r["period_label"]
            int_p = int_r["period_label"]
            ext_conf = ext_r["confidence"]
            int_conf = int_r["confidence"]

            # Comparación 1: Content Hash
            if ext_h is not None and int_h is not None:
                if ext_h != int_h:
                    results["DISCORDANCIA_CONTENIDO"].append({
                        "url": canon_url,
                        "ext_hash": ext_h,
                        "int_hash": int_h,
                        "period_label": ext_p,
                    })
                    continue

            # Si hashes son iguales o al menos uno es None, evaluamos período
            # ¿Tienen período ambos?
            if ext_p is not None and int_p is not None:
                if ext_p != int_p:
                    # Compuerta de confianza (C-5): requiere >= medium en ambos lados
                    high_med = {"high", "medium"}
                    if ext_conf in high_med and int_conf in high_med:
                        results["DISCORDANCIA_PERIODO"].append({
                            "url": canon_url,
                            "ext_period": ext_p,
                            "int_period": int_p,
                            "ext_confidence": ext_conf,
                            "int_confidence": int_conf,
                        })
                    else:
                        results["INDETERMINADO_POR_CONFIANZA"].append({
                            "url": canon_url,
                            "ext_period": ext_p,
                            "int_period": int_p,
                            "ext_confidence": ext_conf,
                            "int_confidence": int_conf,
                            "reason": "CONFIANZA_INSUFICIENTE_PARA_DISCORDANCIA",
                        })
                    continue
            elif (ext_p is None and int_p is not None) or (ext_p is not None and int_p is None):
                results["INDETERMINADO_POR_DATO_AUSENTE"].append({
                    "url": canon_url,
                    "dimension": "period_label",
                    "ext_period": ext_p,
                    "int_period": int_p,
                })
                continue

            # Si llegamos aquí, períodos coinciden (o ambos ausentes)
            # Verificar si falta hash (C-2 / N-5)
            if (ext_h is None and int_h is not None) or (ext_h is not None and int_h is None) or (ext_h is None and int_h is None):
                results["INDETERMINADO_POR_DATO_AUSENTE"].append({
                    "url": canon_url,
                    "dimension": "content_hash",
                    "ext_hash": ext_h,
                    "int_hash": int_h,
                })
                continue

            # Si todo coincide
            results["CONFIRMADO"].append({
                "url": canon_url,
                "content_hash": ext_h,
                "period_label": ext_p,
            })

        # PASADA 2: Segunda pasada por hash idéntico en no emparejados (C-1 / N-3)
        unmatched_ext = [r for r in ext_records if r["rec_id"] not in matched_ext_ids]
        unmatched_int = [r for r in int_records if r["rec_id"] not in matched_int_ids]

        int_by_hash: Dict[str, List[Dict[str, Any]]] = {}
        for r in unmatched_int:
            if r["content_hash"]:
                int_by_hash.setdefault(r["content_hash"], []).append(r)

        pass2_ext_matched: Set[str] = set()
        pass2_int_matched: Set[str] = set()

        for ext_r in unmatched_ext:
            h = ext_r["content_hash"]
            if h and h in int_by_hash and int_by_hash[h]:
                # Empareja por hash con URL distinta
                int_r = int_by_hash[h].pop(0)
                pass2_ext_matched.add(ext_r["rec_id"])
                pass2_int_matched.add(int_r["rec_id"])
                results["URL_CAMBIADA"].append({
                    "content_hash": h,
                    "ext_url": ext_r["url"],
                    "int_url": int_r["url"],
                    "period_label": ext_r["period_label"],
                })

        # PASADA 3: Remanente no emparejado (C-10)
        # Agrupar por canon_url para no duplicar filas duplicadas si las hubiera
        remaining_ext = [r for r in unmatched_ext if r["rec_id"] not in pass2_ext_matched]
        remaining_int = [r for r in unmatched_int if r["rec_id"] not in pass2_int_matched]

        seen_rem_ext: Set[str] = set()
        for r in remaining_ext:
            k = r["canon_url"] or r["rec_id"]
            if k not in seen_rem_ext:
                seen_rem_ext.add(k)
                results["SOLO_EXTERNO"].append({
                    "url": r["url"],
                    "content_hash": r["content_hash"],
                    "period_label": r["period_label"],
                })

        seen_rem_int: Set[str] = set()
        for r in remaining_int:
            k = r["canon_url"] or r["rec_id"]
            if k not in seen_rem_int:
                seen_rem_int.add(k)
                results["SOLO_INTERNO"].append({
                    "url": r["url"],
                    "content_hash": r["content_hash"],
                    "period_label": r["period_label"],
                })

        # Hook para pruebas de control negativo sobre la aserción (H-2)
        if self._hook_before_assert is not None:
            self._hook_before_assert(results)

        # Invariante C-10 (H-2): Totalidad probada contra el tamaño real de la unión de entidades
        # Unión independiente = URLs únicas de ambos lados - pares colapsados en URL_CAMBIADA + registros sin URL
        expected_union = (
            len(valid_ext_urls | valid_int_urls)
            - len(results["URL_CAMBIADA"])
            + unkeyed_ext
            + unkeyed_int
        )
        total_classified = sum(len(items) for items in results.values())
        self.total_entities_classified = total_classified
        assert total_classified == expected_union, (
            f"C-10 invariante violada: total clasificado {total_classified} != unión calculada {expected_union}"
        )

        return results
