"""
tests/test_inheritance_evaluator.py
===================================
Batería de pruebas unitarias para InheritanceEvaluator (B-55 / D-18).
Cubre estrictamente:
- Los 6 casos de prueba (P-1, P-2, N-1, N-2, N-3, N-4) del acta de diseño.
- Los 4 casos de prueba de sondeo (S1, S2, S3, S4) formulados en la auditoría B-55.
"""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from crawler.core.inheritance_evaluator import (
    InheritanceCandidate,
    InheritanceEvaluator,
    InheritanceProposal,
    ProposalStatus,
    GateResult,
)


def test_inheritance_evaluator_n1_trivial_rejection():
    """
    N-1: BCB Deuda Externa -> BCP.
    Control negativo trivial: el candidato no tiene continuidad, ni respaldo legal,
    ni coincidencia estructural. Debe ser estrictamente RECHAZADA.
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Banco Central de Bolivia",
        origen_portal="bcb",
        origen_dataset="deuda_externa",
        ultimo_periodo_origen="2023-S2",
        destino_entidad="Banco de Crédito de Bolivia",
        destino_url="https://www.bcp.com.bo/informes/deuda.pdf",
    )

    with patch.object(evaluator, "fetch_url_content", return_value=(200, b"Contenido banco comercial privado", "a" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.RECHAZADA
        assert proposal.compuerta_4_identidad_destino.status == GateResult.FALSA
        assert "institucional" in proposal.motivo_rechazo.lower() or "dominio" in proposal.motivo_rechazo.lower()


def test_inheritance_evaluator_n2_almost_match_html_page_rejected():
    """
    N-2: Casi acierto. Página HTML de asfi.gob.bo que sí menciona 'ex-Superintendencia de Bancos'.
    Debe ser RECHAZADA por la Compuerta 3 (C-4 / D-14) al tratarse de una página HTML y no un documento.
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin_estadistico",
        ultimo_periodo_origen="2009-02",
        destino_entidad="Autoridad de Supervisión del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/noticias/nota_ex_sbef.html",
    )

    html_content = b"<!DOCTYPE html><html><body>Informacion sobre la ex-Superintendencia de Bancos y Entidades Financieras</body></html>"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, html_content, "b" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.RECHAZADA
        assert proposal.compuerta_3_estructura.status == GateResult.FALSA
        assert "D-14" in proposal.compuerta_3_estructura.detalle or "HTML" in proposal.compuerta_3_estructura.detalle


def test_inheritance_evaluator_n3_hallucinated_legal_citation_rejected_by_provenance():
    """
    N-3: Cita legal que solo existe en la respuesta del modelo (LLM) y no aparece
    en el cuerpo descargado del destino.
    Debe ser RECHAZADA por procedencia (C-1): la evidencia debe salir de bytes reales.
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin_estadistico",
        ultimo_periodo_origen="2009-02",
        primer_periodo_destino="2009-03",
        destino_entidad="Autoridad de Supervisión del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/docs/boletin_2009.pdf",
        modelo_cita_legal_sugerida="Decreto Supremo 29894 Disposicion Transitoria Primera",
    )

    # El PDF descargado habla de estadísticas pero NO menciona la cita legal alucinada ni el predecesor
    pdf_content = b"%PDF-1.4 ASFI Boletin Estadistico del Sistema Financiero Activos y Cartera"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, pdf_content, "c" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        # Endurecido estrictamente a RECHAZADA (H-5)
        assert proposal.status == ProposalStatus.RECHAZADA
        assert proposal.compuerta_2_legal.status == GateResult.FALSA
        assert proposal.compuerta_2_legal.evidence is None


def test_inheritance_evaluator_n4_domain_parking_pattern_rejected():
    """
    N-4: Destino que responde 200 pero contiene marcas de domain parking (caso sicsantacruz.com).
    Debe ser RECHAZADA por la Compuerta 4 (C-3): falla identidad del destino.
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Entidad Extinta",
        origen_portal="extinta",
        origen_dataset="serie_historica",
        ultimo_periodo_origen="2010",
        destino_entidad="Entidad Sucesora Ficticia",
        destino_url="https://www.sicsantacruz.com/estadisticas.pdf",
    )

    parking_content = b"<html><head><!-- Send the parked domain's origin as the referrer --></head><body>Buy this domain</body></html>"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, parking_content, "d" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.RECHAZADA
        assert proposal.compuerta_4_identidad_destino.status == GateResult.FALSA
        assert "parking" in proposal.compuerta_4_identidad_destino.detalle.lower()


def test_inheritance_evaluator_p2_sbef_to_asfi_positive_with_verified_evidence():
    """
    P-2: SBEF -> ASFI.
    Caso positivo simulado con contenido documental auténtico en bytes:
    mención de la extinta SBEF, norma de transferencia, tipo documental D-14 (.pdf / .xlsx),
    campos de serie (cartera, mora, depósitos) e identidad de ASFI.
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin_mensual",
        ultimo_periodo_origen="2009-02",
        primer_periodo_destino="2009-03",
        destino_entidad="Autoridad de Supervisión del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/sites/default/files/boletines/Boletin_Historico_SBEF_2009.pdf",
    )

    doc_content = (
        b"%PDF-1.4\n"
        b"Autoridad de Supervision del Sistema Financiero - ASFI\n"
        b"Boletines Historicos de la ex-Superintendencia de Bancos y Entidades Financieras (SBEF)\n"
        b"En cumplimiento del Decreto Supremo 29894 y Ley 393\n"
        b"Cartera Bruta, Mora y Depositos 2009\n"
    )

    with patch.object(evaluator, "fetch_url_content", return_value=(200, doc_content, "e" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.PROPUESTA
        assert proposal.compuerta_1_continuidad.status == GateResult.VERDADERA
        assert proposal.compuerta_2_legal.status == GateResult.VERDADERA
        assert proposal.compuerta_2_legal.evidence is not None
        assert proposal.compuerta_2_legal.evidence.evidence_url == candidate.destino_url
        assert proposal.compuerta_2_legal.evidence.content_sha256 == "e" * 64
        assert "ex-superintendencia de bancos" in proposal.compuerta_2_legal.evidence.snippet.lower()
        assert proposal.compuerta_3_estructura.status == GateResult.VERDADERA
        assert proposal.compuerta_3_estructura.evidence is not None
        assert proposal.compuerta_4_identidad_destino.status == GateResult.VERDADERA
        assert proposal.compuerta_4_identidad_destino.evidence is not None


def test_inheritance_evaluator_p1_catalog_records_evaluation(tmp_path):
    """
    P-1: Carga y evaluación de herencias pre-catalogadas (SPVS-ASFI, SPVS-APS).
    Verifica que el evaluador tome candidatos del catálogo o cola sin crashear y produzca propuestas estructuradas.
    """
    evaluator = InheritanceEvaluator(output_dir=tmp_path)
    candidates = evaluator.load_candidates_from_catalog()
    assert len(candidates) >= 2

    mock_content = b"%PDF-1.4 APS Autoridad de Fiscalizacion y Control de Pensiones y Seguros SPVS Ley 065 Cartera pensiones y cotizaciones"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, mock_content, "f" * 64)):
        proposals = evaluator.evaluate_all(candidates)
        assert len(proposals) == len(candidates)
        json_path = tmp_path / "propuestas_herencia.json"
        evaluator.save_proposals(proposals, json_path)
        assert json_path.exists()
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert "propuestas" in saved
        assert len(saved["propuestas"]) == len(candidates)


# ==============================================================================
# Casos de sondeo §6 de la auditoría B-55
# ==============================================================================

def test_inheritance_evaluator_s1_foreign_domain_rejected():
    """
    S1: Candidato con destino en otro ministerio (deportes.gob.bo) y palabra genérica.
    Debe ser estrictamente RECHAZADA por no pertenecer al dominio oficial de ASFI
    y porque la sigla 'spvs' no respalda legalmente a 'sbef' (H-1, H-7).
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin",
        destino_entidad="Autoridad de Supervision del Sistema Financiero",
        destino_url="https://www.deportes.gob.bo/x/archivo.pdf",
        ultimo_periodo_origen="2009-02",
        primer_periodo_destino="2009-03",
    )
    content = b"%PDF-1.4 sistema de campeonatos deportivos. Referencia historica a la spvs."
    with patch.object(evaluator, "fetch_url_content", return_value=(200, content, "1" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.RECHAZADA
        assert proposal.compuerta_4_identidad_destino.status == GateResult.FALSA
        assert "no pertenece al dominio oficial" in proposal.compuerta_4_identidad_destino.detalle


def test_inheritance_evaluator_s2_transition_overlap_accepted():
    """
    S2: Solapamiento explicable de transición (origen cesa 2009-03, destino inicia 2009-01).
    Bajo C-2, un solapamiento breve durante la transición institucional debe ser VERDADERA.
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin",
        destino_entidad="Autoridad de Supervision del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/b.pdf",
        ultimo_periodo_origen="2009-03",
        primer_periodo_destino="2009-01",
    )
    content = b"%PDF-1.4 Autoridad de Supervision del Sistema Financiero ex-SBEF Ley 393 Cartera y mora"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, content, "2" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.compuerta_1_continuidad.status == GateResult.VERDADERA
        assert proposal.status == ProposalStatus.PROPUESTA


def test_inheritance_evaluator_s3_network_failure_returns_download_error_status():
    """
    S3: Fallo de red (HTTP 0 / contenido vacío).
    Debe retornar ERROR_DESCARGA para no confundir fallo de conexión con rechazo de fondo (H-8).
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin",
        destino_entidad="Autoridad de Supervision del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/b.pdf",
    )
    with patch.object(evaluator, "fetch_url_content", return_value=(0, b"", "")):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.ERROR_DESCARGA
        assert "fallo de descarga" in proposal.motivo_rechazo.lower()


def test_inheritance_evaluator_s4_document_without_structural_series_fields_rejected():
    """
    S4: Documento PDF que carece de cualquier campo o estructura de serie estadística (cartera, mora, activo...).
    Debe ser RECHAZADA por la Compuerta 3 (C-4 / H-2).
    """
    evaluator = InheritanceEvaluator()
    candidate = InheritanceCandidate(
        origen_entidad="Superintendencia de Bancos y Entidades Financieras",
        origen_portal="sbef",
        origen_dataset="boletin",
        destino_entidad="Autoridad de Supervision del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/vacio.pdf",
        ultimo_periodo_origen="2009-02",
        primer_periodo_destino="2009-03",
    )
    content = b"%PDF-1.4 sbef sistema asfi"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, content, "4" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status == ProposalStatus.RECHAZADA
        assert proposal.compuerta_3_estructura.status == GateResult.FALSA
        assert "no contiene estructura ni campos de serie" in proposal.compuerta_3_estructura.detalle.lower()
