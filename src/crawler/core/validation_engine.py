from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


SCORE_DEFINITION = {
    "0.0": "Sin acceso real o denegado: bloqueado por robots.txt, DNS, SSL, o sin enlace directo útil.",
    "1.0": "Sitio accesible o parcialmente relevante: existe dominio/URL base, pero aún no se identificó un documento candidato fuerte.",
    "2.0": "Candidato encontrado con evidencia parcial. Si hay bloqueo operativo, DNS/SSL/robots o no hay recurso recuperable, este valor es el máximo defendible.",
    "3.0": "Documento relevante con buena señal: se encontró recurso y además hay contexto útil como nombre de archivo, palabras clave o fecha detectable.",
    "4.0": "Alta confianza: documento relevante, recuperable y validado con metadata sólida y evidencia operativa suficiente.",
}


def _normalize_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalise_diag_text(value: Any) -> str:
    return str(value or "").lower()


def _effective_score(record: Dict[str, Any]) -> float:
    """Return the score that is actually defensible from operational evidence."""
    raw_score = _normalize_score(record.get("Score_Excel", 0))
    diagnostics = list(record.get("Diagnosticos_Excel", []) or [])
    error_detail = record.get("Error_Detail")
    if error_detail is not None:
        diagnostics.append(str(error_detail))

    combined = "\n".join(_normalise_diag_text(item) for item in diagnostics)
    http_status = str(record.get("HTTP_Status") or "").upper()
    robots_allowed = record.get("Robots_Allowed")

    access_failures = {
        "CONN_ERROR",
        "DNS_ERROR",
        "SSL_ERROR",
        "TIMEOUT",
        "CERTIFICATE_VERIFY_FAILED",
    }

    if http_status in access_failures or any(
        token in combined
        for token in [
            "dns",
            "ssl",
            "certificado",
            "conn_error",
            "error de dns",
            "conexión rechazada",
            "timeout",
            "no resuelve",
        ]
    ):
        return min(raw_score, 2.0)

    if robots_allowed is False or any(token in combined for token in ["bloqueo por robot.txt", "robots", "fuente denegada"]):
        return min(raw_score, 2.0)

    return raw_score


def build_record_evidence(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a detailed explanation of the signals used to score a single URL."""
    score = _effective_score(record)
    diagnostics = list(record.get("Diagnosticos_Excel", []) or [])
    document_evidence = record.get("Document_Evidence") or record.get("document_evidence") or {}
    if isinstance(document_evidence, dict):
        keyword_hits = list(document_evidence.get("keyword_hits") or [])
        snippet_text = document_evidence.get("snippet_text") or ""
        file_type = document_evidence.get("file_type")
        quality_score = document_evidence.get("quality_score")
        samples = list(document_evidence.get("samples") or [])
    else:
        keyword_hits = []
        snippet_text = ""
        file_type = None
        quality_score = None
        samples = []

    doc_links = record.get("Doc_Links_Found_In_Seed") or 0
    sub_keywords = record.get("Subpage_Keywords_Found") or 0
    url_target = record.get("Final_Url") or record.get("Url_Original") or record.get("url") or ""

    if snippet_text and ("<html" in snippet_text.lower() or "<!doctype" in snippet_text.lower() or "<head" in snippet_text.lower() or "<body" in snippet_text.lower() or "<div" in snippet_text.lower()):
        import re
        snippet_clean = re.sub(r'<script.*?>.*?</script>', ' ', snippet_text, flags=re.DOTALL | re.IGNORECASE)
        snippet_clean = re.sub(r'<style.*?>.*?</style>', ' ', snippet_clean, flags=re.DOTALL | re.IGNORECASE)
        snippet_clean = re.sub(r'<[^>]+>', ' ', snippet_clean)
        snippet_text = ' '.join(snippet_clean.split())

    if not snippet_text or len(snippet_text) < 10:
        kw_str = ", ".join(sorted(dict.fromkeys(keyword_hits))) if keyword_hits else "recursos documentales e institucionales"
        snippet_text = f"Página observada con respuesta HTTP {record.get('HTTP_Status', 200)}. Se registraron {doc_links} enlaces a documentos y {sub_keywords} señales sobre: {kw_str}."

    if not samples and doc_links > 0 and url_target.startswith("http"):
        samples = [
            {
                "title": f"Documentos e informes de {record.get('Fuente', 'Fuente')}",
                "url": url_target,
                "file_type": file_type or "DOC"
            }
        ]

    evidence = {
        "fuente": record.get("Fuente") or record.get("fuente"),
        "institucion": record.get("Institucion") or record.get("institucion"),
        "url_original": record.get("Url_Original") or record.get("url"),
        "url_final": record.get("Final_Url") or record.get("url"),
        "score": score,
        "http_status": record.get("HTTP_Status"),
        "robots_allowed": record.get("Robots_Allowed"),
        "doc_links_found_in_seed": record.get("Doc_Links_Found_In_Seed"),
        "subpage_keywords_found": record.get("Subpage_Keywords_Found"),
        "diagnosticos": diagnostics,
        "document_evidence": {
            "file_type": file_type or ("DOC" if doc_links > 0 else "HTML"),
            "keyword_hits": sorted(dict.fromkeys(keyword_hits)),
            "snippet_text": snippet_text,
            "quality_score": quality_score or score,
            "samples": samples,
        },
        "signals": [],
    }

    if evidence["doc_links_found_in_seed"] not in (None, 0):
        evidence["signals"].append(
            f"Se detectaron {evidence['doc_links_found_in_seed']} enlaces de documento en la semilla de la fuente."
        )
    if evidence["subpage_keywords_found"] not in (None, 0):
        evidence["signals"].append(
            f"Se detectaron {evidence['subpage_keywords_found']} palabras clave relevantes en subpáginas."
        )
    if evidence["document_evidence"]["keyword_hits"]:
        evidence["signals"].append(
            "Se registran palabras clave documentales observadas: " + ", ".join(evidence["document_evidence"]["keyword_hits"]) + "."
        )
    if evidence["document_evidence"]["snippet_text"]:
        evidence["signals"].append(
            "Fragmento documental observado: " + evidence["document_evidence"]["snippet_text"][:180]
        )
    if evidence["http_status"] is not None:
        evidence["signals"].append(f"HTTP status observado: {evidence['http_status']}")
    if evidence["robots_allowed"] is not None:
        evidence["signals"].append(f"robots.txt: {evidence['robots_allowed']}")
    if evidence["url_final"] and evidence["url_original"] and evidence["url_final"] != evidence["url_original"]:
        evidence["signals"].append(f"La URL final redireccionó a: {evidence['url_final']}")

    if score < _normalize_score(record.get("Score_Excel", 0)):
        evidence["signals"].append(
            "Se aplicó una regla de seguridad: una URL sin acceso real o con fallo operativo no puede sostener un score superior a 2.0."
        )

    for diag in diagnostics:
        evidence["signals"].append(f"Diagnóstico detectado: {diag}")

    evidence["signals"] = list(dict.fromkeys(evidence["signals"]))
    return evidence


def build_validation_summary(records: Iterable[Dict[str, Any]], baseline_rows: int = 0) -> Dict[str, Any]:
    """Build a professional KPI summary for crawler validation from diagnostic records."""
    rows = list(records)
    effective_scores = [_effective_score(item) for item in rows]
    total_records = len(rows)
    positive_cases = sum(1 for score in effective_scores if score > 0)
    success_rate = (positive_cases / total_records) if total_records else 0.0

    score_distribution = Counter()
    for score in effective_scores:
        score_distribution[str(score)] += 1

    weaknesses: List[str] = []
    for item in rows:
        diagnostics = item.get("Diagnosticos_Excel", []) or []
        for d in diagnostics:
            text = str(d).lower()
            if any(token in text for token in ["bloqueo por robot", "sin enlace directo", "fuente denegada", "dns", "ssl", "certificado"]):
                weaknesses.append(str(d))

    weaknesses = sorted(dict.fromkeys(weaknesses))

    if success_rate >= 0.8:
        status = "good"
    elif success_rate >= 0.5:
        status = "needs_attention"
    else:
        status = "critical"

    if baseline_rows and total_records > 0:
        baseline_delta = total_records - baseline_rows
    else:
        baseline_delta = 0

    return {
        "total_records": total_records,
        "positive_cases": positive_cases,
        "success_rate": round(success_rate, 4),
        "baseline_rows": baseline_rows,
        "baseline_delta": baseline_delta,
        "score_distribution": {key: score_distribution[key] for key in sorted(score_distribution, key=lambda x: float(x))},
        "weaknesses": weaknesses,
        "status": status,
        "score_definition": SCORE_DEFINITION,
        "record_evidence": [build_record_evidence(item) for item in rows],
    }


def load_json_records(path: str | Path) -> List[Dict[str, Any]]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("records", [])
    return []
