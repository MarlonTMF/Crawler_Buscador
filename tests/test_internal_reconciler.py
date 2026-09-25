"""
tests/test_internal_reconciler.py
=================================
Batería de pruebas exigible para B-57 (C-1 a C-10, Decisión D-19).

Casos exigidos por la sección 5 del acta de decisión:
- P-1: Misma URL, mismo hash, mismo período -> CONFIRMADO
- P-2: URL solo en el interno -> SOLO_INTERNO
- P-3: URL solo nuestra -> SOLO_EXTERNO
- P-4: Misma URL, period_label distinto, ambos high -> DISCORDANCIA_PERIODO
- N-1: Misma URL, hash distinto -> DISCORDANCIA_CONTENIDO (1 sola fila, no partida) [C-1]
- N-2: Misma URL, período distinto, un lado con confianza low -> INDETERMINADO_POR_CONFIANZA [C-5]
- N-3: Mismo hash, URL distinta -> URL_CAMBIADA [C-1 pasada 2]
- N-4: period_start=2021-01-01, period_end=2025-12-31 -> period_label None, RANGO_MULTIANUAL [C-4]
- N-5: Lado interno sin campo de hash -> INDETERMINADO_POR_DATO_AUSENTE, 0 DISCORDANCIA_CONTENIDO [C-2]
- N-6: Entrada con URL vacía, null y duplicada -> invariante C-10 se cumple [C-10]
- Extra C-4: Validador canónico de las 7 granularidades de period_label (diaria, mensual, trimestral, semestral, anual, multianual, sin período).
"""

import pytest
from crawler.core.canonicalizer import Canonicalizer
from crawler.core.internal_reconciler import (
    InternalReconciler,
    build_period_label,
    is_valid_period_label,
    CATEGORIAS_VALIDAS,
)


def test_c4_period_label_generator_and_validator():
    """Valida las 7 formas de period_label bajo la regla C-4 de D-19."""
    # 1. Diaria: YYYY-MM-DD
    lbl, reason = build_period_label("2026-05-15", "2026-05-15")
    assert lbl == "2026-05-15"
    assert reason is None
    assert is_valid_period_label(lbl)

    # 2. Mensual: YYYY-MM
    lbl, reason = build_period_label("2026-05-01", "2026-05-31")
    assert lbl == "2026-05"
    assert reason is None
    assert is_valid_period_label(lbl)

    # 3. Trimestral: YYYY-Q1 .. YYYY-Q4
    lbl, reason = build_period_label("2026-01-01", "2026-03-31")
    assert lbl == "2026-Q1"
    assert is_valid_period_label(lbl)

    lbl, reason = build_period_label("2026-10-01", "2026-12-31")
    assert lbl == "2026-Q4"
    assert is_valid_period_label(lbl)

    # 4. Semestral: YYYY-S1 / YYYY-S2
    lbl, reason = build_period_label("2026-01-01", "2026-06-30")
    assert lbl == "2026-S1"
    assert is_valid_period_label(lbl)

    lbl, reason = build_period_label("2026-07-01", "2026-12-31")
    assert lbl == "2026-S2"
    assert is_valid_period_label(lbl)

    # 5. Anual: YYYY
    lbl, reason = build_period_label("2026-01-01", "2026-12-31")
    assert lbl == "2026"
    assert is_valid_period_label(lbl)

    # 6. Rango multianual: debe devolver None y razón RANGO_MULTIANUAL (NUNCA centinela)
    lbl, reason = build_period_label("2021-01-01", "2025-12-31")
    assert lbl is None
    assert reason == "RANGO_MULTIANUAL"

    # 7. Sin período resuelto: debe devolver None y razón SIN_PERIODO (NUNCA centinela)
    lbl, reason = build_period_label(None, None)
    assert lbl is None
    assert reason == "SIN_PERIODO"

    # Prohibición de centinelas: no deben validar
    assert not is_valid_period_label("SIN_PERIODO")
    assert not is_valid_period_label("unknown")
    assert not is_valid_period_label("")


def test_p1_confirmado():
    """P-1: Misma URL, mismo hash, mismo período en ambos lados -> CONFIRMADO."""
    ext = [{
        "url": "https://www.asfi.gob.bo/docs/rep_2026_01.pdf",
        "content_hash": "hash_abc_123",
        "period_label": "2026-01",
        "confidence": "high",
    }]
    intern = [{
        "url": "https://www.asfi.gob.bo/docs/rep_2026_01.pdf",
        "content_hash": "hash_abc_123",
        "period_label": "2026-01",
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    assert len(res["CONFIRMADO"]) == 1
    assert res["CONFIRMADO"][0]["url"] == "https://www.asfi.gob.bo/docs/rep_2026_01.pdf"
    assert len(res["SOLO_EXTERNO"]) == 0
    assert len(res["SOLO_INTERNO"]) == 0


def test_p2_solo_interno():
    """P-2: URL solo en el interno -> SOLO_INTERNO."""
    ext = []
    intern = [{
        "url": "https://www.asfi.gob.bo/node/498",
        "content_hash": None,
        "period_label": None,
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    assert len(res["SOLO_INTERNO"]) == 1
    assert res["SOLO_INTERNO"][0]["url"] == "https://www.asfi.gob.bo/node/498"
    assert len(res["SOLO_EXTERNO"]) == 0


def test_p3_solo_externo():
    """P-3: URL solo nuestra -> SOLO_EXTERNO."""
    ext = [{
        "url": "https://www.asfi.gob.bo/archivos/boletin_nuevo.pdf",
        "content_hash": "hash_xyz",
        "period_label": "2026-02",
        "confidence": "high",
    }]
    intern = []

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    assert len(res["SOLO_EXTERNO"]) == 1
    assert res["SOLO_EXTERNO"][0]["url"] == "https://www.asfi.gob.bo/archivos/boletin_nuevo.pdf"
    assert len(res["SOLO_INTERNO"]) == 0


def test_p4_discordancia_periodo():
    """P-4: Misma URL, period_label distinto, ambos con confianza high -> DISCORDANCIA_PERIODO."""
    ext = [{
        "url": "https://www.asfi.gob.bo/docs/doc_a.pdf",
        "content_hash": "hash_comun",
        "period_label": "2025",
        "confidence": "high",
    }]
    intern = [{
        "url": "https://www.asfi.gob.bo/docs/doc_a.pdf",
        "content_hash": "hash_comun",
        "period_label": "2026",
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    assert len(res["DISCORDANCIA_PERIODO"]) == 1
    assert res["DISCORDANCIA_PERIODO"][0]["url"] == "https://www.asfi.gob.bo/docs/doc_a.pdf"
    assert len(res["CONFIRMADO"]) == 0


def test_n1_hash_distinto_produce_discordancia_contenido_no_duplicado():
    """N-1: Misma URL, hash distinto -> DISCORDANCIA_CONTENIDO (1 sola fila, no partida en SOLO_EXTERNO + SOLO_INTERNO)."""
    ext = [{
        "url": "https://www.asfi.gob.bo/docs/estadistica.xlsx",
        "content_hash": "hash_v1_externo",
        "period_label": "2026-03",
        "confidence": "high",
    }]
    intern = [{
        "url": "https://www.asfi.gob.bo/docs/estadistica.xlsx",
        "content_hash": "hash_v2_interno",
        "period_label": "2026-03",
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    # C-1 crucial: NO debe partirse en SOLO_EXTERNO y SOLO_INTERNO
    assert len(res["DISCORDANCIA_CONTENIDO"]) == 1
    assert len(res["SOLO_EXTERNO"]) == 0
    assert len(res["SOLO_INTERNO"]) == 0
    assert res["DISCORDANCIA_CONTENIDO"][0]["url"] == "https://www.asfi.gob.bo/docs/estadistica.xlsx"


def test_n2_periodo_distinto_con_confianza_low_es_indeterminado():
    """N-2: Misma URL, período distinto, un lado con confianza low -> INDETERMINADO_POR_CONFIANZA (C-5)."""
    ext = [{
        "url": "https://www.bcb.gob.bo/webdocs/pub_2024.pdf",
        "content_hash": "hash_igual",
        "period_label": "2024",
        "confidence": "low",  # url_year_fallback
    }]
    intern = [{
        "url": "https://www.bcb.gob.bo/webdocs/pub_2024.pdf",
        "content_hash": "hash_igual",
        "period_label": "2025",
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="bcb", external_items=ext, internal_items=intern, min_match_rate=0.0)

    assert len(res["DISCORDANCIA_PERIODO"]) == 0
    assert len(res["INDETERMINADO_POR_CONFIANZA"]) == 1
    assert res["INDETERMINADO_POR_CONFIANZA"][0]["url"] == "https://www.bcb.gob.bo/webdocs/pub_2024.pdf"


def test_n3_url_cambiada_por_segunda_pasada_de_hash():
    """N-3: Mismo hash, URL distinta -> URL_CAMBIADA (segunda pasada C-1)."""
    ext = [{
        "url": "https://www.asfi.gob.bo/portal_nuevo/archivo_42.pdf",
        "content_hash": "hash_invariable_42",
        "period_label": "2026",
        "confidence": "high",
    }]
    intern = [{
        "url": "https://www.asfi.gob.bo/portal_antiguo/archivo_42.pdf",
        "content_hash": "hash_invariable_42",
        "period_label": "2026",
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern, min_match_rate=0.0)

    assert len(res["URL_CAMBIADA"]) == 1
    assert res["URL_CAMBIADA"][0]["content_hash"] == "hash_invariable_42"
    assert len(res["SOLO_EXTERNO"]) == 0
    assert len(res["SOLO_INTERNO"]) == 0


def test_n4_rango_multianual_omite_etiqueta():
    """N-4: period_start=2021-01-01, period_end=2025-12-31 -> period_label es None, razón RANGO_MULTIANUAL (nunca '2021')."""
    lbl, reason = build_period_label("2021-01-01", "2025-12-31")
    assert lbl is None
    assert reason == "RANGO_MULTIANUAL"
    assert lbl != "2021"


def test_n5_lado_interno_sin_hash_declara_indeterminado():
    """N-5: Lado interno sin campo de hash -> INDETERMINADO_POR_DATO_AUSENTE, 0 DISCORDANCIA_CONTENIDO (C-2)."""
    ext = [{
        "url": "https://www.asfi.gob.bo/docs/doc_1.pdf",
        "content_hash": "hash_conocido_123",
        "period_label": "2026-01",
        "confidence": "high",
    }]
    intern = [{
        "url": "https://www.asfi.gob.bo/docs/doc_1.pdf",
        "content_hash": None,  # Ausente en Rolando
        "period_label": "2026-01",
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    assert len(res["DISCORDANCIA_CONTENIDO"]) == 0
    assert len(res["INDETERMINADO_POR_DATO_AUSENTE"]) == 1
    assert res["INDETERMINADO_POR_DATO_AUSENTE"][0]["dimension"] == "content_hash"


def test_n6_totalidad_e_invariante_con_nulos_y_duplicados():
    """N-6: Entrada con URL vacía, nula y duplicada -> invariante C-10 se cumple sin pérdida silenciosa."""
    ext = [
        {"url": "https://www.asfi.gob.bo/doc1.pdf", "content_hash": "h1", "period_label": "2026"},
        {"url": "https://www.asfi.gob.bo/doc1.pdf", "content_hash": "h1", "period_label": "2026"},  # duplicada
        {"url": "", "content_hash": "h2", "period_label": "2026"},  # url vacía
        {"url": None, "content_hash": "h3", "period_label": "2026"},  # url nula
    ]
    intern = [
        {"url": "https://www.asfi.gob.bo/doc1.pdf", "content_hash": "h1", "period_label": "2026"},
        {"url": "https://www.asfi.gob.bo/doc2.pdf", "content_hash": "h4", "period_label": "2026"},
        {"url": "", "content_hash": "h5", "period_label": "2026"},
    ]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern)

    # La aserción de C-10 debe cumplirse internamente sin lanzar AssertionError
    # y la suma de todas las categorías debe ser igual al total de entidades reportadas
    total_clasificado = sum(len(items) for items in res.values())
    assert total_clasificado == reconciler.total_entities_classified
    assert reconciler.total_entities_classified > 0


def test_c3_umbral_match_rate_clave_no_validada():
    """C-3: Si match rate es < 10% del lado menor, se declara CLAVE_NO_VALIDADA."""
    # 1 coincidencia de 100
    ext = [{"url": f"https://www.bcb.gob.bo/doc_{i}.pdf", "content_hash": f"h_ext_{i}"} for i in range(100)]
    intern = [{"url": f"https://www.bcb.gob.bo/doc_{i}.xlsx", "content_hash": f"h_int_{i}"} for i in range(1, 100)]
    # Solo doc_0 coincide
    intern.append({"url": "https://www.bcb.gob.bo/doc_0.pdf", "content_hash": "h_ext_0"})

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="bcb", external_items=ext, internal_items=intern, min_match_rate=0.10)

    # Debe clasificarse bajo CLAVE_NO_VALIDADA y no reportar brecha
    assert len(res["CLAVE_NO_VALIDADA"]) > 0
    assert reconciler.portal_status["bcb"] == "CLAVE_NO_VALIDADA"
    assert len(res["SOLO_INTERNO"]) == 0
    assert len(res["SOLO_EXTERNO"]) == 0


def test_c10_assertion_catches_dropped_entity():
    """H-2: Verifica que la aserción de C-10 no es una tautología y detecta la pérdida de una fila."""
    ext = [{"url": "https://www.asfi.gob.bo/doc1.pdf", "content_hash": "h1"}]
    intern = [{"url": "https://www.asfi.gob.bo/doc2.pdf", "content_hash": "h2"}]

    reconciler = InternalReconciler()
    # Inyectar un hook que simula la supresión de una fila en la pasada 3
    reconciler._hook_before_assert = lambda res: res["SOLO_INTERNO"].pop()

    with pytest.raises(AssertionError, match="C-10 invariante violada"):
        reconciler.reconcile(portal="asfi", external_items=ext, internal_items=intern, min_match_rate=0.0)


def test_h3_centinela_no_disponible_rechazado():
    """H-3: 'No disponible' es rechazado y clasifica en INDETERMINADO_POR_DATO_AUSENTE, nunca INDETERMINADO_POR_CONFIANZA."""
    ext = [{
        "url": "https://www.ine.gob.bo/doc1.pdf",
        "content_hash": None,
        "period_label": "2020",
        "confidence": "high",
    }]
    intern = [{
        "url": "https://www.ine.gob.bo/doc1.pdf",
        "content_hash": None,
        "period_label": "No disponible",  # Centinela que debe ser rechazado como ausente
        "confidence": "high",
    }]

    reconciler = InternalReconciler()
    res = reconciler.reconcile(portal="ine", external_items=ext, internal_items=intern, min_match_rate=0.0)

    assert len(res["INDETERMINADO_POR_CONFIANZA"]) == 0
    assert len(res["INDETERMINADO_POR_DATO_AUSENTE"]) == 1
    assert res["INDETERMINADO_POR_DATO_AUSENTE"][0]["dimension"] == "period_label"


def test_h5_duplicate_counters_reset_and_computed_before_c3():
    """H-5: Los contadores de duplicados se calculan antes de C-3 y no arrastran estado entre portales."""
    reconciler = InternalReconciler()

    # Portal 1 con duplicados (ej. ASFI)
    ext1 = [
        {"url": "https://asfi.gob.bo/doc.pdf"},
        {"url": "https://asfi.gob.bo/doc.pdf"},  # duplicado
    ]
    int1 = [
        {"url": "https://asfi.gob.bo/doc.pdf"},
        {"url": "https://asfi.gob.bo/doc.pdf"},  # duplicado
        {"url": "https://asfi.gob.bo/doc.pdf"},  # duplicado
    ]
    reconciler.reconcile(portal="asfi", external_items=ext1, internal_items=int1, min_match_rate=0.0)
    assert reconciler.duplicate_urls_ext == 1
    assert reconciler.duplicate_urls_int == 2

    # Portal 2 sin duplicados que cae en C-3 (ej. BCB)
    ext2 = [{"url": "https://bcb.gob.bo/pub1.pdf"}]
    int2 = [{"url": "https://bcb.gob.bo/otra.xlsx"}]
    # min_match_rate=0.5 -> match 0.0 < 0.5 -> cae en CLAVE_NO_VALIDADA
    reconciler.reconcile(portal="bcb", external_items=ext2, internal_items=int2, min_match_rate=0.5)
    assert reconciler.duplicate_urls_ext == 0, "No debe arrastrar duplicate_urls_ext de ASFI a BCB"
    assert reconciler.duplicate_urls_int == 0, "No debe arrastrar duplicate_urls_int de ASFI a BCB"
    assert reconciler.portal_status["bcb"] == "CLAVE_NO_VALIDADA"


