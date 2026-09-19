#!/usr/bin/env python3
"""
scripts/reverificar_track_a.py
==============================
Script de re-verificación periódica de conectividad de Track A (Etapa E · B-25).

Detecta regresiones de conectividad en el catálogo maestro (output/excel_urls_diagnostic.json):
identifica automáticamente cuando una URL que estaba en estado 200 (o accesible) deja de estarlo.

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
import requests

DEFAULT_CATALOG_PATH = Path("output/excel_urls_diagnostic.json")
DEFAULT_TIMEOUT = 10
DEFAULT_USER_AGENT = "DataX-WebProspector/1.0 (+https://datax.org.bo; health-check)"

logger = logging.getLogger("reverificar_track_a")


def check_url_connectivity(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    session: Optional[requests.Session] = None,
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Verifica la conectividad de una URL mediante HEAD con fallback a GET stream.
    Retorna: (is_ok_200, http_status_code, error_message)
    """
    s = session or requests.Session()
    headers = {"User-Agent": user_agent}

    try:
        # 1. Intento inicial vía HEAD siguiendo redirecciones
        resp = s.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return True, 200, None
        
        # Si el servidor no permite HEAD (405 Method Not Allowed) o devuelve 403 a HEAD
        if resp.status_code in (405, 403):
            # Fallback a GET ligero (stream=True para no descargar body completo)
            resp_get = s.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
            if resp_get.status_code == 200:
                return True, 200, None
            return False, resp_get.status_code, None
        
        return False, resp.status_code, None

    except requests.exceptions.SSLError as e:
        return False, None, f"SSL Error: {type(e).__name__}"
    except requests.exceptions.Timeout:
        return False, None, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, None, "Connection Error"
    except requests.exceptions.RequestException as e:
        return False, None, f"Request Error: {str(e)}"
    except Exception as e:
        return False, None, f"Unexpected Error: {str(e)}"


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

    s = session or requests.Session()

    for reg in registros_a_verificar:
        fuente = reg.get("Fuente", "DESCONOCIDA")
        institucion = reg.get("Institucion", "")
        url = reg.get("Final_Url") or reg.get("Url_Original")
        estado_previo = str(reg.get("HTTP_Status", "")).strip()

        ok, status_actual, error_msg = check_url_connectivity(url, timeout=timeout, session=s)

        es_regresion = False
        # Regresión: estaba en 200 en el baseline y ahora no responde 200
        if estado_previo == "200" and not ok:
            es_regresion = True

        res_item = {
            "fuente": fuente,
            "institucion": institucion,
            "url": url,
            "estado_previo": estado_previo,
            "estado_actual": status_actual,
            "error": error_msg,
            "ok": ok,
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
        "regresiones": regresiones,
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
        "--fail-on-regression",
        action="store_true",
        default=True,
        help="Salir con código 1 si se detecta al menos una regresión (default: True)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilitar salida detallada para cada URL verificada",
    )

    args = parser.parse_args()

    fuentes_list = [f.strip() for f in args.fuentes.split(",") if f.strip()] if args.fuentes else None
    solo_200 = not args.todas

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

    if args.verbose:
        for r in reporte["resultados"]:
            status_desc = str(r["estado_actual"]) if r["estado_actual"] else f"ERR ({r['error']})"
            icon = "OK" if r["ok"] else "FAIL"
            print(f" [{icon:<4}] {r['fuente']:<15} | Prev: {r['estado_previo']:<5} -> Actual: {status_desc:<15} | {r['url']}")

    print("-" * 80)
    print("Resumen de Re-verificación Track A:")
    print(f"  Total URLs verificadas: {total_verificados}")
    print(f"  URLs activas en 200:   {total_ok} ({round(total_ok/total_verificados*100, 1) if total_verificados else 0}%)")
    print(f"  Regresiones detectadas: {total_regresiones}")

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

    if total_regresiones > 0 and args.fail_on_regression:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
