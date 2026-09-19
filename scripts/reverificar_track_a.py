#!/usr/bin/env python3
"""
scripts/reverificar_track_a.py
==============================
Script de re-verificación periódica de conectividad de Track A (Etapa E · B-25).

Detecta regresiones de conectividad en el catálogo maestro (output/excel_urls_diagnostic.json):
identifica automáticamente cuando una URL que estaba en estado 200 deja de estarlo.

Criterios de aceptación (docs/plan_bloques.md · B-25):
- Corrido dos veces seguidas sin cambios en la web no produce ninguna alerta (sin falsos positivos).
- Contra una URL rota a propósito sí produce alerta (ambas comprobaciones).
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_CATALOG_PATH = Path("output/excel_urls_diagnostic.json")
DEFAULT_TIMEOUT = 10
DEFAULT_USER_AGENT = "DataX-WebProspector/1.0 (+https://datax.org.bo; health-check)"

logger = logging.getLogger("reverificar_track_a")


def check_url_connectivity(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    session: Optional[requests.Session] = None,
) -> Tuple[bool, Optional[int], Optional[str], bool]:
    """
    Verifica la conectividad de una URL mediante HEAD con fallback garantizado a GET stream
    ante cualquier fallo (código != 200 o excepción, H-1).
    
    Retorna: (is_ok_200, http_status_code, error_message, requiere_headless)
    """
    s = session or requests.Session()
    headers = {"User-Agent": user_agent}

    # 1. Intento inicial vía HEAD
    head_ok = False
    try:
        resp_head = s.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp_head.status_code == 200:
            return True, 200, None, False
    except Exception:
        # Cualquier fallo en HEAD (TooManyRedirects, SSL, timeout, etc.) dispara fallback a GET
        head_ok = False

    # 2. Fallback universal a GET ligero (stream=True para evitar descargar el cuerpo)
    try:
        resp_get = s.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
        if resp_get.status_code == 200:
            return True, 200, None, False
        if resp_get.status_code == 403:
            # H-2 / D-03: Posible protección bot/WAF, no es regresión de caída definitiva
            return False, 403, "403 Forbidden (posible bot challenge / Cloudflare)", True
        return False, resp_get.status_code, None, False

    except requests.exceptions.SSLError as e:
        # Verificar si con verify=False el portal responde 200 (cadena intermedia incompleta)
        try:
            resp_insecure = s.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True, verify=False)
            if resp_insecure.status_code == 200:
                return False, None, "SSL_CERT_ERROR (cadena incompleta; responde 200 con verify=False)", False
        except Exception:
            pass
        return False, None, f"SSL Error: {type(e).__name__}", False
    except requests.exceptions.TooManyRedirects:
        return False, None, "Too Many Redirects", False
    except requests.exceptions.Timeout:
        return False, None, "Timeout", False
    except requests.exceptions.ConnectionError:
        return False, None, "Connection Error", False
    except requests.exceptions.RequestException as e:
        return False, None, f"Request Error: {type(e).__name__}", False
    except Exception as e:
        return False, None, f"Unexpected Error: {str(e)}", False


def verificar_catalogo_track_a(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    solo_200: bool = True,
    fuentes_filter: Optional[List[str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Verifica las URLs del catálogo contra su estado previo y detecta regresiones.
    """
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catálogo no encontrado en: {catalog_path}")

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    fuentes_set = {f.lower().strip() for f in fuentes_filter} if fuentes_filter else None

    # Filtrar registros a verificar
    registros_a_verificar = []
    for reg in catalogo:
        fuente_id = str(reg.get("Fuente", "")).strip()
        if fuentes_set and fuente_id.lower() not in fuentes_set:
            continue

        estado_previo = str(reg.get("HTTP_Status", "")).strip()
        
        if solo_200 and estado_previo != "200":
            continue

        url = reg.get("Final_Url") or reg.get("Url_Original")
        if not url:
            continue

        registros_a_verificar.append(reg)

    resultados: List[Dict[str, Any]] = []
    regresiones: List[Dict[str, Any]] = []
    alertas_headless: List[Dict[str, Any]] = []
    alertas_ssl: List[Dict[str, Any]] = []

    s = session or requests.Session()

    for reg in registros_a_verificar:
        fuente = reg.get("Fuente", "DESCONOCIDA")
        institucion = reg.get("Institucion", "")
        url = reg.get("Final_Url") or reg.get("Url_Original")
        estado_previo = str(reg.get("HTTP_Status", "")).strip()

        ok, status_actual, error_msg, req_headless = check_url_connectivity(url, timeout=timeout, session=s)

        es_regresion = False
        if estado_previo == "200":
            if req_headless:
                alertas_headless.append({
                    "fuente": fuente, "institucion": institucion, "url": url,
                    "estado_previo": estado_previo, "estado_actual": 403, "error": error_msg,
                })
            elif error_msg and "SSL_CERT_ERROR" in error_msg:
                alertas_ssl.append({
                    "fuente": fuente, "institucion": institucion, "url": url,
                    "estado_previo": estado_previo, "estado_actual": status_actual, "error": error_msg,
                })
                # No es regresión de caída del sitio, es problema de certificado
            elif not ok:
                es_regresion = True

        res_item = {
            "fuente": fuente,
            "institucion": institucion,
            "url": url,
            "estado_previo": estado_previo,
            "estado_actual": status_actual,
            "error": error_msg,
            "ok": ok,
            "requiere_headless": req_headless,
            "es_regresion": es_regresion,
        }

        resultados.append(res_item)
        if es_regresion:
            regresiones.append(res_item)

    reporte = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "catalog_path": str(catalog_path),
        "total_catalogo": len(catalogo),
        "total_verificados": len(registros_a_verificar),
        "total_ok": sum(1 for r in resultados if r["ok"]),
        "total_regresiones": len(regresiones),
        "total_requiere_headless": len(alertas_headless),
        "total_alertas_ssl": len(alertas_ssl),
        "regresiones": regresiones,
        "alertas_headless": alertas_headless,
        "alertas_ssl": alertas_ssl,
        "resultados": resultados,
    }

    return reporte


def main():
    parser = argparse.ArgumentParser(
        description="Re-verificador de conectividad periódica de Track A — DataX Web Prospector"
    )
    parser.add_argument(
        "--catalogo",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help=f"Ruta al catálogo de URLs (default: {DEFAULT_CATALOG_PATH})",
    )
    parser.add_argument(
        "--todas",
        action="store_true",
        help="Verificar todas las URLs del catálogo, no solo las que estaban en 200",
    )
    parser.add_argument(
        "--fuentes",
        type=str,
        default="",
        help="Lista separada por comas de fuentes específicas a verificar (ej. 'ADA,ASFI,BCB')",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout por URL en segundos (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Ruta opcional para guardar el reporte estructurado en JSON",
    )
    parser.add_argument(
        "--no-fail-on-regression",
        action="store_true",
        help="No salir con código 1 ante regresiones (por defecto sale con código 1 si hay regresiones)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilitar salida detallada para cada URL verificada",
    )

    args = parser.parse_args()

    fuentes_list = [f.strip() for f in args.fuentes.split(",") if f.strip()] if args.fuentes else None
    solo_200 = not args.todas
    fail_on_regression = not args.no_fail_on_regression

    print("=" * 80)
    print("Re-verificación de Conectividad Track A · DataX Web Prospector (B-25)")
    print("=" * 80)
    print(f"Catálogo: {args.catalogo}")
    print(f"Filtro solo_200: {solo_200}")
    if fuentes_list:
        print(f"Fuentes filtradas ({len(fuentes_list)}): {', '.join(fuentes_list)}")
    print("-" * 80)

    try:
        reporte = verificar_catalogo_track_a(
            catalog_path=args.catalogo,
            solo_200=solo_200,
            fuentes_filter=fuentes_list,
            timeout=args.timeout,
        )
    except Exception as e:
        print(f"ERROR al verificar catálogo: {e}", file=sys.stderr)
        sys.exit(2)

    total_verificados = reporte["total_verificados"]
    total_ok = reporte["total_ok"]
    total_regresiones = reporte["total_regresiones"]
    total_headless = reporte.get("total_requiere_headless", 0)
    total_ssl = reporte.get("total_alertas_ssl", 0)

    if args.verbose:
        for r in reporte["resultados"]:
            status_desc = str(r["estado_actual"]) if r["estado_actual"] else f"ERR ({r['error']})"
            if r["ok"]:
                icon = "OK"
            elif r.get("requiere_headless"):
                icon = "BOT"
            elif r.get("error") and "SSL_CERT_ERROR" in str(r.get("error")):
                icon = "SSL"
            else:
                icon = "FAIL"
            print(f" [{icon:<4}] {r['fuente']:<15} | Prev: {r['estado_previo']:<5} -> Actual: {status_desc:<20} | {r['url']}")

    print("-" * 80)
    print("Resumen de Re-verificación Track A:")
    print(f"  Total URLs verificadas:   {total_verificados}")
    print(f"  URLs activas en 200:     {total_ok} ({round(total_ok/total_verificados*100, 1) if total_verificados else 0}%)")
    print(f"  Regresiones detectadas:   {total_regresiones}")
    print(f"  Alertas Bot / Headless:   {total_headless}")
    print(f"  Alertas SSL (cert chain): {total_ssl}")

    if total_headless > 0:
        print("\n" + "-" * 80)
        print("AVISO: Fuentes con protección Bot / Cloudflare sobrevenida (D-03):")
        for b in reporte["alertas_headless"]:
            print(f"  - [{b['fuente']}] {b['url']} (requiere headless)")
        print("-" * 80)

    if total_ssl > 0:
        print("\n" + "-" * 80)
        print("AVISO: Fuentes con cadena de certificados SSL incompleta (servidor activo):")
        for s_item in reporte["alertas_ssl"]:
            print(f"  - [{s_item['fuente']}] {s_item['url']} ({s_item['error']})")
        print("-" * 80)

    if total_regresiones > 0:
        print("\n" + "!" * 80)
        print("ALERTA DE REGRESIÓN: URLs que estaban en 200 y dejaron de estarlo:")
        print("!" * 80)
        for reg in reporte["regresiones"]:
            status_desc = str(reg["estado_actual"]) if reg["estado_actual"] else f"FALLO DE CONEXIÓN ({reg['error']})"
            print(f"  - [{reg['fuente']}] {reg['institucion']}")
            print(f"    URL: {reg['url']}")
            print(f"    Estado previo: {reg['estado_previo']} -> Estado actual: {status_desc}")
        print("!" * 80)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(reporte, f, ensure_ascii=False, indent=2)
        print(f"\nReporte JSON guardado en: {args.output_json}")

    print("=" * 80)

    if total_regresiones > 0 and fail_on_regression:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
