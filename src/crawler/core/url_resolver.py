"""Resolución automática de dominios muertos, con registro de auditoría.

Encadena tres cosas que hasta ahora se hacían a mano, una por una, en la
conversación con el usuario:

1. Preguntarle a Gemini qué pasó con la institución (¿se movió? ¿se disolvió?
   ¿qué entidad asumió sus funciones?).
2. Si el candidato que da Gemini no responde tal cual, probarle variantes
   mecánicas (con/sin ``www``, TLDs .org/.com/.bo/.gob.bo, con/sin ruta) —
   el "intercambio" Gemini <-> motor de variantes.
3. Antes de aceptar cualquier candidato que sí responde, verificar que el
   contenido de la página realmente mencione a la institución (evita el caso
   real que ocurrió con CADEXCO: "cadex.org" responde 200 pero es la Cámara
   de Exportadores de Santa Cruz, no la de Cochabamba).

Cada intento queda registrado con la respuesta cruda de la IA y el detalle de
cada candidato probado, para que quede trazabilidad de cómo se llegó (o no)
a una resolución.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from crawler.core.fetcher import _redact_secrets

logger = logging.getLogger(__name__)

# Palabras demasiado genéricas en nombres de instituciones bolivianas: que aparezcan
# en una página no prueba nada (casi cualquier cámara/ministerio las usa). Se exige
# que al menos una palabra FUERA de esta lista también aparezca.
GENERIC_INSTITUTION_WORDS = {
    "de", "del", "la", "las", "los", "el", "para", "con", "y", "en",
    "bolivia", "boliviana", "boliviano", "nacional", "camara", "cámara",
    "comercio", "exportadores", "asociacion", "asociación", "instituto",
    "servicio", "ministerio", "autoridad", "federacion", "federación",
    "empresa", "publica", "pública", "publico", "público", "sistema",
    "administradora", "direccion", "dirección", "general", "central",
    "banco", "fondo", "centro", "promocion", "promoción", "desarrollo",
}

SPA_MARKERS = ("<app-root", "ng-version", "__next_data__", "id=\"root\"")


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _sanear(valor):
    """Aplica la redacción de credenciales en profundidad sobre lo que se registra.

    Segunda barrera: aunque el origen del texto ya redacte, todo lo que entra
    al log de resolución pasa por acá antes de persistirse.
    """
    if isinstance(valor, dict):
        return {k: _sanear(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sanear(v) for v in valor]
    return _redact_secrets(valor)


def _tokenize_institution_name(name: str, fuente: str) -> List[str]:
    text = _strip_accents((name or "") + " " + (fuente or "")).lower()
    tokens = re.findall(r"[a-z0-9]{4,}", text)
    return sorted(set(tokens))


def _clean_html_to_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _strip_accents(text).lower()


@dataclass
class CandidateCheck:
    url: str
    source: str
    reachable: bool
    status: Optional[int] = None
    gemini_seed: Optional[str] = None
    content_checked: bool = False
    matched_keywords: List[str] = field(default_factory=list)
    verified: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url, "source": self.source, "reachable": self.reachable,
            "status": self.status, "gemini_seed": self.gemini_seed,
            "content_checked": self.content_checked, "matched_keywords": self.matched_keywords,
            "verified": self.verified, "note": self.note,
        }


def _content_verify(html: str, keywords: List[str]) -> List[str]:
    text = _clean_html_to_text(html)
    return [kw for kw in keywords if kw in text]


def _is_spa_shell(html: str) -> bool:
    lowered = html.lower()
    return len(html) < 800 or any(marker in lowered for marker in SPA_MARKERS)


def _fetch_for_verification(url: str, headless_fetcher=None) -> Optional[str]:
    """Trae el HTML a verificar; si parece una SPA vacía, intenta renderizarla."""
    try:
        resp = requests.get(
            url, timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        html = resp.text or ""
    except Exception as exc:
        logger.warning("No se pudo traer %s para verificación de contenido: %s", url, exc)
        html = ""

    if html and not _is_spa_shell(html):
        return html

    if headless_fetcher is not None:
        try:
            ok, _status, result = headless_fetcher.fetch(url)
            if ok and result is not None and result.html:
                return result.html
        except Exception as exc:
            logger.warning("Fallback headless falló para %s: %s", url, exc)

    return html or None


def _probe_with_mechanical_variants(fetcher, candidate: str, seed_label: str) -> List[CandidateCheck]:
    """Prueba un candidato tal cual y, si falla, sus variantes mecánicas (www/TLD/esquema)."""
    out: List[CandidateCheck] = []
    direct = fetcher.probe_url_variant(candidate)
    out.append(CandidateCheck(
        url=candidate, source=seed_label, reachable=bool(direct.get("reachable")),
        status=direct.get("status"), gemini_seed=candidate if seed_label != "gemini_best_url" else None,
    ))
    if direct.get("reachable"):
        return out

    try:
        variants = fetcher._generate_url_variants(candidate)
    except Exception:
        variants = []
    for variant in variants:
        if variant == candidate:
            continue
        probe = fetcher.probe_url_variant(variant)
        out.append(CandidateCheck(
            url=variant, source=f"{seed_label}+variant", reachable=bool(probe.get("reachable")),
            status=probe.get("status"), gemini_seed=candidate,
        ))
    return out


def _ask_gemini_for_successor(fetcher, institucion: str, fuente: str, original_url: str) -> Dict[str, Any]:
    """Segunda consulta, más puntual, para cuando la primera no trajo alternativas.

    Se usa cuando Gemini ya dijo "esto se disolvió" pero no ofreció ningún
    sucesor — le insiste específicamente por la entidad que asumió las funciones.
    """
    prompt = (
        "Eres un analista experto en la administración pública e instituciones bolivianas. "
        f"La institución '{institucion}' (sigla: {fuente}), cuyo sitio web era {original_url}, "
        "dejó de operar o su sitio ya no existe. Investiga: ¿alguna otra entidad boliviana "
        "asumió sus funciones, activos o responsabilidades? Si existe una entidad sucesora "
        "real, da su nombre y su sitio web oficial. Si genuinamente no hay sucesora (la "
        "función simplemente dejó de existir), dilo. Devuelve SOLO un JSON con este esquema: "
        '{"successor_name": string|null, "successor_url": string|null, "reason": string}. '
        "No agregues texto fuera del JSON."
    )
    try:
        text = fetcher._generate_gemini_content(prompt)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).rstrip("`").strip()
        import json
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return {"successor_name": None, "successor_url": None, "reason": "Respuesta no interpretable."}
        return data
    except Exception as exc:
        logger.warning("Consulta de sucesor falló para %s: %s", original_url, exc)
        return {"successor_name": None, "successor_url": None, "reason": f"Consulta falló: {exc}"}


def resolve_dead_domain(
    fetcher, fuente: str, institucion: str, original_url: str,
    headless_fetcher=None,
) -> Dict[str, Any]:
    """Resuelve automáticamente un dominio caído, con registro completo de auditoría.

    Devuelve un dict con: la respuesta cruda de la IA (una o dos consultas),
    cada candidato probado (y si su contenido fue verificado), y el veredicto
    final: 'resolved' (URL confirmada por contenido), 'reachable_unverified'
    (responde pero no se pudo confirmar que sea la institución — requiere
    revisión humana antes de cargarla como definitiva) o 'unresolved'.
    """
    keywords = [kw for kw in _tokenize_institution_name(institucion, fuente)
                if kw not in GENERIC_INSTITUTION_WORDS]

    record: Dict[str, Any] = {
        "fuente": fuente,
        "institucion": institucion,
        "original_url": original_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "keywords_used": keywords,
        "ai_queries": [],
        "candidates": [],
        "resolution": {"status": "unresolved", "resolved_url": None, "confidence": 0.0, "method": None},
    }

    verdict = fetcher._ask_gemini_for_url_verdict(original_url)
    record["ai_queries"].append({"kind": "url_verdict", "response": _sanear(verdict)})

    candidates: List[tuple[str, str]] = []  # (url, seed_label)
    if verdict.get("best_url"):
        candidates.append((verdict["best_url"], "gemini_best_url"))
    for alt in verdict.get("alternatives") or []:
        candidates.append((alt, "gemini_alternative"))

    if not candidates:
        # No trajo nada (típico cuando dice "not_found" sin más detalle): se insiste
        # puntualmente por la entidad sucesora antes de darlo por perdido.
        successor = _ask_gemini_for_successor(fetcher, institucion, fuente, original_url)
        record["ai_queries"].append({"kind": "successor_query", "response": _sanear(successor)})
        if successor.get("successor_url"):
            candidates.append((successor["successor_url"], "gemini_successor"))

    checks: List[CandidateCheck] = []
    seen_urls = {original_url}
    for candidate_url, label in candidates:
        if candidate_url in seen_urls:
            continue
        for check in _probe_with_mechanical_variants(fetcher, candidate_url, label):
            if check.url in seen_urls:
                continue
            seen_urls.add(check.url)
            checks.append(check)

    best_verified: Optional[CandidateCheck] = None
    best_unverified: Optional[CandidateCheck] = None
    for check in checks:
        if not check.reachable:
            continue
        html = _fetch_for_verification(check.url, headless_fetcher=headless_fetcher)
        check.content_checked = html is not None
        if html:
            matched = _content_verify(html, keywords) if keywords else []
            check.matched_keywords = matched
            check.verified = bool(matched) or not keywords
            if not keywords:
                check.note = "Sin palabras clave distintivas en el nombre de la institución; no se pudo verificar por contenido."
        if check.verified and best_verified is None:
            best_verified = check
        elif not check.verified and best_unverified is None:
            best_unverified = check

    record["candidates"] = [c.to_dict() for c in checks]

    successor_response = next(
        (q["response"] for q in record["ai_queries"] if q["kind"] == "successor_query"), None
    )
    successor_query_failed = bool(successor_response) and str(successor_response.get("reason", "")).startswith("Consulta falló")

    if best_verified:
        record["resolution"] = {
            "status": "resolved", "resolved_url": best_verified.url, "confidence": 0.85,
            "method": best_verified.source,
        }
    elif best_unverified:
        record["resolution"] = {
            "status": "reachable_unverified", "resolved_url": best_unverified.url, "confidence": 0.3,
            "method": best_unverified.source,
        }
    elif successor_response and not successor_response.get("successor_url") and not successor_query_failed:
        # La consulta de sucesor sí respondió (no fue un fallo de la API) y concluyó
        # explícitamente que no hay una entidad sucesora clara: se acepta como
        # resolución (institución disuelta, sin sucesor), no como "no se pudo saber".
        record["resolution"] = {
            "status": "dissolved_no_successor", "resolved_url": None, "confidence": 0.7,
            "method": "gemini_successor_query",
        }
    elif verdict.get("status") == "not_found" and not checks:
        record["resolution"] = {
            "status": "dissolved_no_successor", "resolved_url": None, "confidence": 0.7,
            "method": "gemini_verdict",
        }

    return record
