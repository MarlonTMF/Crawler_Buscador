"""
tests/test_inheritance_evaluator.py
===================================
Batería de pruebas unitarias para InheritanceEvaluator (B-55).
Cubre estrictamente los 6 casos de prueba (P-1, P-2, N-1, N-2, N-3, N-4)
aprobados en el acta de decisión de diseño docs/auditorias/B-55_decision_diseno.md.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
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
        assert "identidad" in proposal.motivo_rechazo.lower() or "respaldo legal" in proposal.motivo_rechazo.lower()


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
        destino_entidad="Autoridad de Supervisión del Sistema Financiero",
        destino_url="https://www.asfi.gob.bo/docs/boletin_2009.pdf",
        modelo_cita_legal_sugerida="Decreto Supremo 29894 Disposicion Transitoria Primera",
    )

    # El PDF descargado habla de estadísticas pero NO menciona la cita legal alucinada
    pdf_content = b"%PDF-1.4 Boletin Estadistico del Sistema Financiero Activos y Cartera"
    with patch.object(evaluator, "fetch_url_content", return_value=(200, pdf_content, "c" * 64)):
        proposal = evaluator.evaluate_candidate(candidate)
        assert proposal.status in (ProposalStatus.RECHAZADA, ProposalStatus.EVIDENCIA_INCOMPLETA)
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
    Caso positivo con evidencia descargada auténtica: mención de la extinta SBEF,
    tipo documental D-14 (.pdf / .xlsx), e identidad de ASFI.
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
        assert proposal.compuerta_2_legal.status == GateResult.VERDADERA
        assert proposal.compuerta_2_legal.evidence is not None
        assert proposal.compuerta_2_legal.evidence.evidence_url == candidate.destino_url
        assert proposal.compuerta_2_legal.evidence.content_sha256 == "e" * 64
        assert "ex-superintendencia de bancos" in proposal.compuerta_2_legal.evidence.snippet.lower()
        assert proposal.compuerta_3_estructura.status == GateResult.VERDADERA
        assert proposal.compuerta_4_identidad_destino.status == GateResult.VERDADERA


def test_inheritance_evaluator_p1_catalog_records_evaluation(tmp_path):
    """
    P-1: Carga y evaluación de herencias pre-catalogadas (SPVS-ASFI, SPVS-APS).
    Verifica que el evaluador tome candidatos del catálogo o cola sin crashear y produzca propuestas estructuradas.
    """
    evaluator = InheritanceEvaluator(output_dir=tmp_path)
    candidates = evaluator.load_candidates_from_catalog()
    assert len(candidates) >= 2  # SPVS-APS y SPVS-ASFI al menos

    with patch.object(evaluator, "fetch_url_content", return_value=(200, b"%PDF-1.4 APS Autoridad de Fiscalizacion y Control de Pensiones y Seguros SPVS Ley 065", "f" * 64)):
        proposals = evaluator.evaluate_all(candidates)
        assert len(proposals) == len(candidates)
        json_path = tmp_path / "propuestas_herencia.json"
        evaluator.save_proposals(proposals, json_path)
        assert json_path.exists()
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert "propuestas" in saved
        assert len(saved["propuestas"]) == len(candidates)
