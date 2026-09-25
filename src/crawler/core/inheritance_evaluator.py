"""
crawler/core/inheritance_evaluator.py
=====================================
Evaluador de herencia institucional entre entidades públicas (B-55 / Decisión D-18).

Evalúa si una serie estadística migró válidamente a otra entidad o dominio mediante
cuatro compuertas copulativas de evidencia descargada, acatando C-1 a C-7:
1. Continuidad temporal (falsador).
2. Respaldo legal o mención explícita del predecesor (con procedencia de bytes C-1).
3. Identidad estructural sobre documentos D-14 (nunca páginas HTML).
4. Identidad institucional del destino bajo D-01 (con descarte de domain parking).

Ninguna herencia se admite de forma automática (D-18 §1).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import unicodedata
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class ProposalStatus(str, Enum):
    PROPUESTA = "PROPUESTA"
    EVIDENCIA_INCOMPLETA = "EVIDENCIA_INCOMPLETA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"


class GateResult(str, Enum):
    VERDADERA = "VERDADERA"
    FALSA = "FALSA"
    INDETERMINADO = "INDETERMINADO"


@dataclass
class DownloadedEvidence:
    """Evidencia respaldada estrictamente por bytes reales descargados (C-1)."""
    evidence_url: str
    http_status: int
    content_sha256: str
    fetched_at: str
    snippet: str
    matched_pattern: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GateEvaluation:
    status: GateResult
    detalle: str
    evidence: Optional[DownloadedEvidence] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "status": self.status.value,
            "detalle": self.detalle,
            "evidence": self.evidence.to_dict() if self.evidence else None,
        }
        return d


@dataclass
class InheritanceCandidate:
    origen_entidad: str
    origen_portal: str
    origen_dataset: str
    destino_entidad: str
    destino_url: str
    ultimo_periodo_origen: Optional[str] = None
    primer_periodo_destino: Optional[str] = None
    origen_agente: bool = False
    modelo_cita_legal_sugerida: Optional[str] = None


@dataclass
class InheritanceProposal:
    origen_entidad: str
    origen_portal: str
    origen_dataset: str
    ultimo_periodo_origen: Optional[str]
    destino_entidad: str
    destino_url: str
    compuerta_1_continuidad: GateEvaluation
    compuerta_2_legal: GateEvaluation
    compuerta_3_estructura: GateEvaluation
    compuerta_4_identidad_destino: GateEvaluation
    origen_agente: bool
    status: ProposalStatus
    evaluado_en: str
    motivo_rechazo: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origen_entidad": self.origen_entidad,
            "origen_portal": self.origen_portal,
            "origen_dataset": self.origen_dataset,
            "ultimo_periodo_origen": self.ultimo_periodo_origen,
            "destino_entidad": self.destino_entidad,
            "destino_url": self.destino_url,
            "origen_agente": self.origen_agente,
            "status": self.status.value,
            "motivo_rechazo": self.motivo_rechazo,
            "evaluado_en": self.evaluado_en,
            "compuertas": {
                "compuerta_1_continuidad": self.compuerta_1_continuidad.to_dict(),
                "compuerta_2_legal": self.compuerta_2_legal.to_dict(),
                "compuerta_3_estructura": self.compuerta_3_estructura.to_dict(),
                "compuerta_4_identidad_destino": self.compuerta_4_identidad_destino.to_dict(),
            },
        }


class InheritanceEvaluator:
    """Evaluador de propuestas de herencia institucional con rigor probatorio D-18."""

    DOCUMENTARY_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".zip", ".rar", ".csv", ".ods", ".xlsm"}
    PARKING_PATTERNS = [
        re.compile(r"<!--\s*Send the parked domain's origin as the referrer\s*-->", re.IGNORECASE),
        re.compile(r"buy this domain", re.IGNORECASE),
        re.compile(r"domain may be for sale", re.IGNORECASE),
        re.compile(r"parked domain", re.IGNORECASE),
        re.compile(r"sedoparking", re.IGNORECASE),
    ]

    def __init__(
        self,
        output_dir: Path = Path("docs/entregas"),
        config_dir: Path = Path("config"),
        timeout: float = 8.0,
    ):
        self.output_dir = output_dir
        self.config_dir = config_dir
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "DataX-InheritanceEvaluator/1.0 (+http://datax.org)"
        })

    def fetch_url_content(self, url: str) -> Tuple[int, bytes, str]:
        """Descarga el recurso destino con cálculo de hash SHA-256."""
        try:
            r = self._session.get(url, timeout=self.timeout, verify=False, allow_redirects=True)
            content = r.content or b""
            sha256 = hashlib.sha256(content).hexdigest()
            return r.status_code, content, sha256
        except Exception as e:
            logger.debug("Error descargando %s: %s", url, e)
            return 0, b"", ""

    def evaluate_candidate(self, candidate: InheritanceCandidate) -> InheritanceProposal:
        """
        Evalúa un candidato de herencia contra las cuatro compuertas de evidencia D-18.
        """
        status_code, content, sha256 = self.fetch_url_content(candidate.destino_url)
        fetched_at = datetime.now(timezone.utc).isoformat()
        sample_text = content[:262144].decode("latin-1", errors="ignore")
        clean_text = "".join(c for c in unicodedata.normalize("NFKD", sample_text) if not unicodedata.combining(c)).lower()

        # ---------------------------------------------------------
        # Compuerta 4: Identidad del destino bajo D-01 (C-3)
        # ---------------------------------------------------------
        c4_status = GateResult.VERDADERA
        c4_detalle = "Identidad institucional del destino verificada."
        for pattern in self.PARKING_PATTERNS:
            if pattern.search(sample_text):
                c4_status = GateResult.FALSA
                c4_detalle = "Violación D-01 / C-3: Detectado patrón de domain parking en el destino."
                break

        if c4_status == GateResult.VERDADERA:
            # Verificar presencia de palabras clave de la entidad sucesora
            dest_norm = candidate.destino_entidad.lower()
            dest_terms = [t for t in re.split(r"[\s,\.-]+", dest_norm) if len(t) > 3 and t not in ("banco", "nacional", "autoridad", "general", "bolivia")]
            if not dest_terms:
                dest_terms = [dest_norm]
            has_dest_identity = any(re.search(rf"\b{re.escape(t)}\b", clean_text) for t in dest_terms)
            if not has_dest_identity and not any(re.search(rf"\b{re.escape(t)}\b", candidate.destino_url.lower()) for t in dest_terms):
                c4_status = GateResult.FALSA
                c4_detalle = f"Violación D-01 / C-3: El destino no acredita identidad institucional de '{candidate.destino_entidad}'."

        gate_4 = GateEvaluation(status=c4_status, detalle=c4_detalle)

        # ---------------------------------------------------------
        # Compuerta 3: Identidad estructural sobre documentos D-14 (C-4)
        # ---------------------------------------------------------
        path_lower = urlparse(candidate.destino_url).path.lower()
        is_html = (
            content.lstrip()[:1024].lower().startswith(b"<!doctype html")
            or b"<html" in content[:2048].lower()
            or path_lower.endswith(".html")
            or path_lower.endswith(".htm")
            or path_lower.endswith("/")
        )

        has_doc_ext = any(path_lower.endswith(ext) for ext in self.DOCUMENTARY_EXTENSIONS)

        if is_html or not has_doc_ext:
            c3_status = GateResult.FALSA
            c3_detalle = "Violación D-14 / C-4: El destino es una página HTML o carece de formato documental permitido (.pdf, .xlsx, .zip, etc.)."
        else:
            c3_status = GateResult.VERDADERA
            c3_detalle = f"Formato documental D-14 verificado ({Path(path_lower).suffix})."

        gate_3 = GateEvaluation(status=c3_status, detalle=c3_detalle)

        # ---------------------------------------------------------
        # Compuerta 2: Respaldo legal o mención explícita del predecesor (C-1)
        # ---------------------------------------------------------
        # Términos del predecesor
        orig_norm = candidate.origen_entidad.lower()
        orig_portal = candidate.origen_portal.lower()

        legal_patterns = [
            rf"\bex[-\s]?{re.escape(orig_portal)}\b",
            rf"\b{re.escape(orig_portal)}\b",
            rf"\bex[-\s]?superintendencia\b",
            rf"\bsuperintendencia de bancos\b",
            rf"\bsbef\b",
            rf"\bspvs\b",
            rf"\bsuptrans\b",
            r"\bley\s*(?:n[°ºo]?\s*)?(?:393|365|065|1732)",
            r"\bdecreto\s*supremo\s*(?:n[°ºo]?\s*)?(?:29894|0071|071)",
            r"\bdisposicion\s*transitoria\b",
        ]

        found_evidence = None
        c2_status = GateResult.FALSA
        c2_detalle = "No hay respaldo legal o mención explícita del predecesor en el contenido descargado."

        # C-1: Si el modelo sugirió una cita alucinada que no está en el contenido
        if candidate.modelo_cita_legal_sugerida:
            model_kw = candidate.modelo_cita_legal_sugerida.lower().split()
            matched_words = sum(1 for w in model_kw if len(w) > 3 and w in clean_text)
            if matched_words < len([w for w in model_kw if len(w) > 3]) * 0.7:
                logger.info("Cita legal sugerida por modelo no encontrada en bytes descargados: %s", candidate.modelo_cita_legal_sugerida)

        for pat_str in legal_patterns:
            m = re.search(pat_str, clean_text)
            if m:
                start = max(0, m.start() - 60)
                end = min(len(sample_text), m.end() + 60)
                snippet = sample_text[start:end].strip().replace("\n", " ")

                found_evidence = DownloadedEvidence(
                    evidence_url=candidate.destino_url,
                    http_status=status_code,
                    content_sha256=sha256,
                    fetched_at=fetched_at,
                    snippet=snippet,
                    matched_pattern=pat_str,
                )
                c2_status = GateResult.VERDADERA
                c2_detalle = f"Mención legal o de predecesor verificada en bytes descargados con patrón '{pat_str}'."
                break

        gate_2 = GateEvaluation(status=c2_status, detalle=c2_detalle, evidence=found_evidence)

        # ---------------------------------------------------------
        # Compuerta 1: Continuidad temporal (falsador / C-2)
        # ---------------------------------------------------------
        if candidate.ultimo_periodo_origen and candidate.primer_periodo_destino:
            # Evaluar coherencia de orden cronológico
            if candidate.ultimo_periodo_origen > candidate.primer_periodo_destino:
                c1_status = GateResult.FALSA
                c1_detalle = f"Falsador temporal: El destino arranca en {candidate.primer_periodo_destino}, previo al cierre de origen en {candidate.ultimo_periodo_origen}."
            else:
                c1_status = GateResult.VERDADERA
                c1_detalle = f"Continuidad temporal corroborada: origen cesa en {candidate.ultimo_periodo_origen}, destino inicia en {candidate.primer_periodo_destino}."
        else:
            c1_status = GateResult.INDETERMINADO
            c1_detalle = "Período no determinado en ambos lados (insumo unknown o ausente)."

        gate_1 = GateEvaluation(status=c1_status, detalle=c1_detalle)

        # ---------------------------------------------------------
        # Dictamen final de la propuesta
        # ---------------------------------------------------------
        motivo_rechazo = None
        if gate_4.status == GateResult.FALSA:
            status = ProposalStatus.RECHAZADA
            motivo_rechazo = f"Compuerta 4 Fallida: {gate_4.detalle}"
        elif gate_3.status == GateResult.FALSA:
            status = ProposalStatus.RECHAZADA
            motivo_rechazo = f"Compuerta 3 Fallida: {gate_3.detalle}"
        elif gate_2.status == GateResult.FALSA:
            status = ProposalStatus.RECHAZADA
            motivo_rechazo = f"Compuerta 2 Fallida: {gate_2.detalle}"
        elif gate_1.status == GateResult.FALSA:
            status = ProposalStatus.RECHAZADA
            motivo_rechazo = f"Compuerta 1 Fallida: {gate_1.detalle}"
        elif gate_1.status == GateResult.INDETERMINADO:
            status = ProposalStatus.EVIDENCIA_INCOMPLETA
            motivo_rechazo = "Compuerta 1 indeterminada por falta de período confiable."
        else:
            status = ProposalStatus.PROPUESTA

        return InheritanceProposal(
            origen_entidad=candidate.origen_entidad,
            origen_portal=candidate.origen_portal,
            origen_dataset=candidate.origen_dataset,
            ultimo_periodo_origen=candidate.ultimo_periodo_origen,
            destino_entidad=candidate.destino_entidad,
            destino_url=candidate.destino_url,
            compuerta_1_continuidad=gate_1,
            compuerta_2_legal=gate_2,
            compuerta_3_estructura=gate_3,
            compuerta_4_identidad_destino=gate_4,
            origen_agente=candidate.origen_agente,
            status=status,
            evaluado_en=fetched_at,
            motivo_rechazo=motivo_rechazo,
        )

    def load_candidates_from_catalog(self) -> List[InheritanceCandidate]:
        """Carga casos históricos de herencia desde el catálogo maestro o semillas institucionales."""
        candidates = []
        cat_path = Path("output/excel_urls_diagnostic.json")
        if cat_path.exists():
            try:
                data = json.loads(cat_path.read_text(encoding="utf-8"))
                for row in data:
                    src = row.get("Fuente", "")
                    if "SPVS" in src or "SUPTRANS" in src:
                        dest_url = row.get("Final_Url") or row.get("URL_Original") or ""
                        dest_ent = (
                            "Autoridad de Fiscalización y Control de Pensiones y Seguros"
                            if "APS" in src
                            else (
                                "Autoridad de Regulación y Fiscalización de Telecomunicaciones y Transportes"
                                if "SUPTRANS" in src
                                else "Autoridad de Supervisión del Sistema Financiero"
                            )
                        )
                        candidates.append(
                            InheritanceCandidate(
                                origen_entidad=src,
                                origen_portal=src.lower().replace("-", "_"),
                                origen_dataset="series_historicas",
                                destino_entidad=dest_ent,
                                destino_url=dest_url,
                            )
                        )
            except Exception as e:
                logger.debug("Error leyendo catálogo: %s", e)

        # Semillas canónicas si catálogo no existe o no tiene entradas completas
        if not candidates:
            candidates.append(
                InheritanceCandidate(
                    origen_entidad="Superintendencia de Pensiones, Valores y Seguros (SPVS)",
                    origen_portal="spvs",
                    origen_dataset="valores_seguros",
                    destino_entidad="Autoridad de Supervisión del Sistema Financiero (ASFI)",
                    destino_url="https://www.asfi.gob.bo/docs/spvs_historico.pdf",
                )
            )
            candidates.append(
                InheritanceCandidate(
                    origen_entidad="Superintendencia de Pensiones, Valores y Seguros (SPVS)",
                    origen_portal="spvs",
                    origen_dataset="pensiones",
                    destino_entidad="Autoridad de Fiscalización y Control de Pensiones y Seguros (APS)",
                    destino_url="https://www.aps.gob.bo/docs/spvs_pensiones.pdf",
                )
            )

        return candidates

    def evaluate_all(self, candidates: List[InheritanceCandidate]) -> List[InheritanceProposal]:
        """Evalúa una lista de candidatos y retorna sus propuestas."""
        return [self.evaluate_candidate(c) for c in candidates]

    def save_proposals(self, proposals: List[InheritanceProposal], output_file: Optional[Path] = None):
        """Persiste las propuestas evaluadas en JSON sin tocar inventory.db ni configs (C-5)."""
        target = output_file or (self.output_dir / "propuestas_herencia.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        out = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "criterio": "D-18 (Herencia de series con evidencia descargada obligatoria)",
            "total_evaluadas": len(proposals),
            "resumen_estados": {
                "PROPUESTA": sum(1 for p in proposals if p.status == ProposalStatus.PROPUESTA),
                "EVIDENCIA_INCOMPLETA": sum(1 for p in proposals if p.status == ProposalStatus.EVIDENCIA_INCOMPLETA),
                "RECHAZADA": sum(1 for p in proposals if p.status == ProposalStatus.RECHAZADA),
                "ACEPTADA": 0,  # Requiere revisión humana por D-18
            },
            "propuestas": [p.to_dict() for p in proposals],
        }
        target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Propuestas de herencia guardadas en: %s", target)
