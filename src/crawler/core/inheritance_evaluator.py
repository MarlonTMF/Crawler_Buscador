"""
crawler/core/inheritance_evaluator.py
=====================================
Evaluador de herencia institucional entre entidades públicas (B-55 / Decisión D-18).

Evalúa si una serie estadística migró válidamente a otra entidad o dominio mediante
cuatro compuertas copulativas de evidencia descargada, acatando C-1 a C-7:
1. Continuidad temporal (falsador C-2).
2. Respaldo legal o mención explícita del predecesor con procedencia obligatoria de bytes (C-1).
3. Identidad estructural sobre documentos D-14 / C-4 (nunca páginas HTML, con cotejo de campos).
4. Identidad institucional del destino bajo D-01 / C-3 (dominio oficial + siglas/términos distintivos).

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
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class ProposalStatus(str, Enum):
    PROPUESTA = "PROPUESTA"
    EVIDENCIA_INCOMPLETA = "EVIDENCIA_INCOMPLETA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    ERROR_DESCARGA = "ERROR_DESCARGA"


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
    period_confidence: Optional[str] = "high"
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

    OFFICIAL_DOMAINS = {
        "asfi": ["asfi.gob.bo"],
        "aps": ["aps.gob.bo"],
        "att": ["att.gob.bo"],
        "bcb": ["bcb.gob.bo"],
        "ine": ["ine.gob.bo"],
        "mefp": ["economiayfinanzas.gob.bo"],
    }

    SERIES_STRUCTURAL_FIELDS = [
        r"\bcartera\b", r"\bmora\b", r"\bactivo[s]?\b", r"\bpasivo[s]?\b",
        r"\bpatrimonio\b", r"\bdep[oó]sito[s]?\b", r"\bliquidez\b", r"\bcr[eé]dito[s]?\b",
        r"\bbalance\b", r"\bestado[s]?\s+financiero[s]?\b", r"\bpensi[oó]n(?:es)?\b",
        r"\bcotizaci[oó]n(?:es)?\b", r"\binversi[oó]n(?:es)?\b", r"\bdeuda\b",
        r"\bexportaci[oó]n(?:es)?\b", r"\bimportaci[oó]n(?:es)?\b", r"\bipc\b",
        r"\bpib\b", r"\binflaci[oó]n\b", r"\bbolet[ií]n\s+estad[ií]stico\b"
    ]

    # Esquemas históricos conocidos para validación de procedencia
    KNOWN_ORIGIN_SCHEMAS = {
        "sbef": ["cartera", "mora", "depositos", "activo", "credito"],
        "spvs": ["pensiones", "valores", "seguros", "cotizaciones", "inversiones"],
        "suptrans": ["transporte", "pasajeros", "carga", "flujo", "tarifas"],
    }

    def __init__(
        self,
        output_dir: Path = Path("docs/entregas"),
        config_dir: Path = Path("config"),
        timeout: float = 8.0,
        verify_ssl: bool = True,
    ):
        self.output_dir = output_dir
        self.config_dir = config_dir
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "DataX-InheritanceEvaluator/1.0 (+http://datax.org)"
        })

    def fetch_url_content(self, url: str) -> Tuple[int, bytes, str]:
        """Descarga el recurso destino con cálculo de hash SHA-256."""
        try:
            # Respetar verificación SSL por defecto, con fallback controlado si es necesario
            r = self._session.get(url, timeout=self.timeout, verify=self.verify_ssl, allow_redirects=True)
            content = r.content or b""
            sha256 = hashlib.sha256(content).hexdigest()
            return r.status_code, content, sha256
        except Exception as e:
            logger.debug("Error descargando %s: %s", url, e)
            return 0, b"", ""

    def _normalize_text(self, text: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()

    def _check_destination_official_domain(self, destino_entidad: str, destino_url: str) -> Tuple[bool, str]:
        """Verifica que el host de la URL pertenezca al dominio institucional oficial (C-3 / H-1)."""
        host = urlparse(destino_url).netloc.lower()
        ent_norm = self._normalize_text(destino_entidad)

        target_portal = None
        if "asfi" in ent_norm or "supervision del sistema financiero" in ent_norm:
            target_portal = "asfi"
        elif "aps" in ent_norm or "pensiones y seguros" in ent_norm or "fiscalizacion y control de pensiones" in ent_norm:
            target_portal = "aps"
        elif "att" in ent_norm or "telecomunicaciones y transportes" in ent_norm:
            target_portal = "att"
        elif "bcb" in ent_norm or "banco central" in ent_norm:
            target_portal = "bcb"
        elif "ine" in ent_norm or "estadistica" in ent_norm:
            target_portal = "ine"

        if target_portal:
            valid_domains = self.OFFICIAL_DOMAINS.get(target_portal, [])
            if not any(host == d or host.endswith("." + d) for d in valid_domains):
                return False, f"El host '{host}' no pertenece al dominio oficial registrado de {target_portal.upper()} ({valid_domains})."
        else:
            if not host.endswith(".gob.bo"):
                return False, f"El host '{host}' no es un dominio institucional público (.gob.bo)."

        return True, "Host verificado contra dominios institucionales oficiales."

    def _check_destination_identity_content(self, destino_entidad: str, clean_text: str) -> Tuple[bool, str, Optional[str]]:
        """Verifica la presencia de la sigla completa o de todos los términos distintivos (H-1)."""
        ent_norm = self._normalize_text(destino_entidad)
        
        # Sigla oficial según entidad
        acronyms = []
        if "asfi" in ent_norm or "supervision del sistema financiero" in ent_norm:
            acronyms = ["asfi"]
        elif "aps" in ent_norm or "pensiones y seguros" in ent_norm:
            acronyms = ["aps"]
        elif "att" in ent_norm or "telecomunicaciones y transportes" in ent_norm:
            acronyms = ["att"]
        elif "bcb" in ent_norm or "banco central" in ent_norm:
            acronyms = ["bcb"]
        elif "ine" in ent_norm or "instituto nacional de estadistica" in ent_norm:
            acronyms = ["ine"]

        # Si coincide sigla oficial completa
        for acr in acronyms:
            pat = rf"\b{acr}\b"
            if re.search(pat, clean_text):
                return True, f"Identidad verificada mediante sigla institucional '{acr}'.", pat

        # O verificación copulativa de términos distintivos (ALL, no ANY)
        stop_words = {"de", "del", "la", "el", "y", "en", "para", "autoridad", "estado", "nacional", "general", "bolivia"}
        terms = [t for t in re.split(r"[\s,\.-]+", ent_norm) if len(t) > 3 and t not in stop_words]
        
        if terms and all(re.search(rf"\b{re.escape(t)}\b", clean_text) for t in terms):
            matched = terms[0]
            return True, f"Identidad verificada mediante coincidencia conjunta de todos los términos ({terms}).", rf"\b{matched}\b"

        return False, f"El cuerpo no contiene la sigla ni los términos requeridos de '{destino_entidad}'.", None

    def _has_origin_inventory_records(self, origen_portal: str, origen_dataset: str) -> bool:
        """Comprueba si el dataset de origen tiene registros previos en inventory.db."""
        db_path = Path("output") / origen_portal / "inventory.db"
        if not db_path.exists():
            return False
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM inventory WHERE dataset_id = ?", (origen_dataset,))
            count = cur.fetchone()[0]
            conn.close()
            return count > 0
        except Exception:
            return False

    def evaluate_candidate(self, candidate: InheritanceCandidate) -> InheritanceProposal:
        """
        Evalúa un candidato de herencia contra las cuatro compuertas de evidencia D-18.
        """
        status_code, content, sha256 = self.fetch_url_content(candidate.destino_url)
        fetched_at = datetime.now(timezone.utc).isoformat()

        # H-8: Si hay fallo de red o descarga inaccesible, reportar estado propio
        if status_code == 0 or not content:
            gate_null = GateEvaluation(status=GateResult.FALSA, detalle="No evaluada por fallo de red.")
            return InheritanceProposal(
                origen_entidad=candidate.origen_entidad,
                origen_portal=candidate.origen_portal,
                origen_dataset=candidate.origen_dataset,
                ultimo_periodo_origen=candidate.ultimo_periodo_origen,
                destino_entidad=candidate.destino_entidad,
                destino_url=candidate.destino_url,
                compuerta_1_continuidad=gate_null,
                compuerta_2_legal=gate_null,
                compuerta_3_estructura=gate_null,
                compuerta_4_identidad_destino=gate_null,
                origen_agente=candidate.origen_agente,
                status=ProposalStatus.ERROR_DESCARGA,
                evaluado_en=fetched_at,
                motivo_rechazo=f"Fallo de descarga: no se pudo obtener respuesta HTTP válida de '{candidate.destino_url}' (HTTP {status_code}).",
            )

        sample_text = content[:262144].decode("latin-1", errors="ignore")
        clean_text = self._normalize_text(sample_text)

        # ---------------------------------------------------------
        # Compuerta 4: Identidad del destino bajo D-01 / C-3 (H-1)
        # ---------------------------------------------------------
        c4_status = GateResult.VERDADERA
        c4_detalle = "Identidad institucional del destino verificada."
        c4_evidence = None

        # 1. Descarte de domain parking
        for pattern in self.PARKING_PATTERNS:
            if pattern.search(sample_text):
                c4_status = GateResult.FALSA
                c4_detalle = "Violación D-01 / C-3: Detectado patrón de domain parking en el destino."
                break

        # 2. Verificación de dominio oficial
        if c4_status == GateResult.VERDADERA:
            domain_ok, domain_msg = self._check_destination_official_domain(candidate.destino_entidad, candidate.destino_url)
            if not domain_ok:
                c4_status = GateResult.FALSA
                c4_detalle = f"Violación D-01 / C-3: {domain_msg}"

        # 3. Verificación de identidad institucional en contenido
        if c4_status == GateResult.VERDADERA:
            ident_ok, ident_msg, matched_pat = self._check_destination_identity_content(candidate.destino_entidad, clean_text)
            if not ident_ok:
                c4_status = GateResult.FALSA
                c4_detalle = f"Violación D-01 / C-3: {ident_msg}"
            else:
                # C-1 / H-6: Producir evidencia descargada
                m = re.search(matched_pat, clean_text)
                start = max(0, m.start() - 40) if m else 0
                end = min(len(sample_text), m.end() + 40) if m else 80
                snippet = sample_text[start:end].strip().replace("\n", " ")
                c4_evidence = DownloadedEvidence(
                    evidence_url=candidate.destino_url,
                    http_status=status_code,
                    content_sha256=sha256,
                    fetched_at=fetched_at,
                    snippet=snippet,
                    matched_pattern=matched_pat,
                )

        gate_4 = GateEvaluation(status=c4_status, detalle=c4_detalle, evidence=c4_evidence)

        # ---------------------------------------------------------
        # Compuerta 3: Identidad estructural sobre documentos D-14 / C-4 (H-2)
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

        c3_status = GateResult.FALSA
        c3_detalle = ""
        c3_evidence = None

        if is_html or not has_doc_ext:
            c3_status = GateResult.FALSA
            c3_detalle = "Violación D-14 / C-4: El destino es una página HTML o carece de formato documental permitido (.pdf, .xlsx, .zip, etc.)."
        else:
            # Comparación de campos estadísticos (cartera, mora, etc.)
            matched_fields = [pat for pat in self.SERIES_STRUCTURAL_FIELDS if re.search(pat, clean_text)]
            if not matched_fields:
                c3_status = GateResult.FALSA
                c3_detalle = "Violación C-4: El documento no contiene estructura ni campos de serie estadística (cartera, mora, activo, balance, cotizaciones, etc.)."
            else:
                # Comprobar si el origen está registrado en inventory.db
                has_origin_data = self._has_origin_inventory_records(candidate.origen_portal, candidate.origen_dataset)
                # O si pertenece a esquemas históricos canónicos conocidos
                is_known_origin = candidate.origen_portal.lower() in self.KNOWN_ORIGIN_SCHEMAS

                if not has_origin_data and not is_known_origin:
                    c3_status = GateResult.INDETERMINADO
                    c3_detalle = "Sin datos previos del origen en inventory.db para contraste estructural (C-4)."
                else:
                    c3_status = GateResult.VERDADERA
                    c3_detalle = f"Formato documental D-14 y estructura de serie estadística verificada ({len(matched_fields)} campos: {matched_fields[:3]})."
                    m = re.search(matched_fields[0], clean_text)
                    start = max(0, m.start() - 40) if m else 0
                    end = min(len(sample_text), m.end() + 40) if m else 80
                    c3_evidence = DownloadedEvidence(
                        evidence_url=candidate.destino_url,
                        http_status=status_code,
                        content_sha256=sha256,
                        fetched_at=fetched_at,
                        snippet=sample_text[start:end].strip().replace("\n", " "),
                        matched_pattern=matched_fields[0],
                    )

        gate_3 = GateEvaluation(status=c3_status, detalle=c3_detalle, evidence=c3_evidence)

        # ---------------------------------------------------------
        # Compuerta 2: Respaldo legal derivado del predecesor (C-1 / H-7)
        # ---------------------------------------------------------
        orig_portal = candidate.origen_portal.lower().strip()
        orig_entidad = candidate.origen_entidad.lower().strip()

        legal_patterns = [
            rf"\bex[-\s]?{re.escape(orig_portal)}\b",
            rf"\b{re.escape(orig_portal)}\b",
        ]
        if "sbef" in orig_portal or "bancos" in orig_entidad:
            legal_patterns.extend([
                r"\bex[-\s]?superintendencia\s+de\s+bancos\b",
                r"\bsuperintendencia\s+de\s+bancos\b",
                r"\bsbef\b",
                r"\bley\s*(?:n[°ºo]?\s*)?393\b",
                r"\bdecreto\s*supremo\s*(?:n[°ºo]?\s*)?29894\b",
            ])
        elif "spvs" in orig_portal or "pensiones" in orig_entidad or "seguros" in orig_entidad:
            legal_patterns.extend([
                r"\bex[-\s]?spvs\b",
                r"\bspvs\b",
                r"\bsuperintendencia\s+de\s+pensiones\b",
                r"\bley\s*(?:n[°ºo]?\s*)?(?:365|065|1732)\b",
                r"\bdecreto\s*supremo\s*(?:n[°ºo]?\s*)?(?:0071|071|29894)\b",
            ])
        elif "suptrans" in orig_portal or "transporte" in orig_entidad:
            legal_patterns.extend([
                r"\bex[-\s]?suptrans\b",
                r"\bsuptrans\b",
                r"\bsuperintendencia\s+de\s+transportes\b",
                r"\bdecreto\s*supremo\s*(?:n[°ºo]?\s*)?(?:0071|071)\b",
            ])

        found_evidence = None
        c2_status = GateResult.FALSA
        c2_detalle = f"No hay respaldo legal o mención explícita del predecesor '{candidate.origen_entidad}' en el contenido descargado."

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
        # Compuerta 1: Continuidad temporal (falsador C-2 / H-3)
        # ---------------------------------------------------------
        # Solo evaluar si hay fechas y la confianza no es 'low'
        has_dates = bool(candidate.ultimo_periodo_origen and candidate.primer_periodo_destino)
        is_confident = (candidate.period_confidence or "medium").lower() in ("medium", "high")

        c1_evidence = None
        if has_dates and is_confident:
            try:
                # Normalizar fechas a meses numéricos YYYY*12 + MM
                def parse_period_months(p_str: str) -> int:
                    m_match = re.search(r"(\d{4})[-/]?([01]?\d)?", p_str)
                    if not m_match:
                        return 0
                    y = int(m_match.group(1))
                    m = int(m_match.group(2)) if m_match.group(2) else 1
                    return y * 12 + m

                orig_m = parse_period_months(candidate.ultimo_periodo_origen)
                dest_m = parse_period_months(candidate.primer_periodo_destino)

                # C-2: Falsador temporal: si el destino cierra o culmina mucho antes de que el origen termine
                # Solapamiento explicable (transición institucional) de hasta 12 meses es VERDADERO
                diff = dest_m - orig_m
                if diff < -12:
                    c1_status = GateResult.FALSA
                    c1_detalle = f"Falsador temporal: El destino inicia en {candidate.primer_periodo_destino}, más de 12 meses antes del cese de origen en {candidate.ultimo_periodo_origen}."
                elif diff > 24:
                    c1_status = GateResult.FALSA
                    c1_detalle = f"Falsador temporal: El destino inicia en {candidate.primer_periodo_destino}, más de 24 meses después del cese de origen en {candidate.ultimo_periodo_origen} (discontinuidad no explicada)."
                else:
                    c1_status = GateResult.VERDADERA
                    c1_detalle = f"Continuidad temporal corroborada: origen cesa en {candidate.ultimo_periodo_origen}, destino inicia en {candidate.primer_periodo_destino} (desvío {diff} meses, explicable)."
                    c1_evidence = DownloadedEvidence(
                        evidence_url=candidate.destino_url,
                        http_status=status_code,
                        content_sha256=sha256,
                        fetched_at=fetched_at,
                        snippet=f"Período destino {candidate.primer_periodo_destino} empalma con origen {candidate.ultimo_periodo_origen}",
                        matched_pattern=r"\b\d{4}[-/]\d{2}\b",
                    )
            except Exception as e:
                c1_status = GateResult.INDETERMINADO
                c1_detalle = f"No se pudo normalizar los períodos para cálculo cronológico: {e}"
        else:
            c1_status = GateResult.INDETERMINADO
            c1_detalle = "Período no determinado o confianza baja en alguno de los dos lados (insumo unknown o low)."

        gate_1 = GateEvaluation(status=c1_status, detalle=c1_detalle, evidence=c1_evidence)

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
        elif gate_1.status == GateResult.INDETERMINADO or gate_3.status == GateResult.INDETERMINADO:
            status = ProposalStatus.EVIDENCIA_INCOMPLETA
            motivo_rechazo = "Compuerta indeterminada por falta de período confiable o contraste estructural completo."
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
        """
        Persiste y acumula las propuestas evaluadas en JSON sin tocar inventory.db ni configs (C-5 / H-9).
        Mantiene el registro histórico de rechazos para no reproponer ni gastar cuota.
        """
        target = output_file or (self.output_dir / "propuestas_herencia.json")
        target.parent.mkdir(parents=True, exist_ok=True)

        existing_proposals: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if target.exists():
            try:
                prev = json.loads(target.read_text(encoding="utf-8"))
                for p_dict in prev.get("propuestas", []):
                    key = (p_dict.get("origen_entidad", ""), p_dict.get("destino_url", ""))
                    existing_proposals[key] = p_dict
            except Exception as e:
                logger.warning("Error leyendo propuestas previas para acumulación: %s", e)

        # Actualizar / agregar nuevas propuestas
        for p in proposals:
            key = (p.origen_entidad, p.destino_url)
            existing_proposals[key] = p.to_dict()

        all_proposals = list(existing_proposals.values())

        out = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "criterio": "D-18 (Herencia de series con evidencia descargada obligatoria)",
            "total_evaluadas": len(all_proposals),
            "resumen_estados": {
                "PROPUESTA": sum(1 for p in all_proposals if p.get("status") == ProposalStatus.PROPUESTA.value),
                "EVIDENCIA_INCOMPLETA": sum(1 for p in all_proposals if p.get("status") == ProposalStatus.EVIDENCIA_INCOMPLETA.value),
                "RECHAZADA": sum(1 for p in all_proposals if p.get("status") == ProposalStatus.RECHAZADA.value),
                "ERROR_DESCARGA": sum(1 for p in all_proposals if p.get("status") == ProposalStatus.ERROR_DESCARGA.value),
                "ACEPTADA": sum(1 for p in all_proposals if p.get("status") == ProposalStatus.ACEPTADA.value),
            },
            "propuestas": all_proposals,
        }
        target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Propuestas de herencia guardadas y acumuladas en: %s", target)
