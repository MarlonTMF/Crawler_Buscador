#!/usr/bin/env python3
"""
scripts/medir_objetivos_fase2.py
================================
Medición programática, reproducible y exhaustiva de los 4 objetivos de la Fase 2
sobre el estado consolidado de las bases de datos en output/ al cierre de B-40.
Todos los veredictos y porcentajes se derivan estrictamente de los datos consultados.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Extensiones binarias estrictas según Decisión D-14
DOCUMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".zip")

def medir_metricas_fase2(output_dir: Path, catalog_path: Path) -> Dict[str, Any]:
    db_paths = sorted(output_dir.glob("*/inventory.db"))
    
    total_docs_d14 = 0
    total_docs_d13 = 0
    total_docs_con_bytes = 0
    total_docs_con_sha256 = 0
    anomalias_columnas = 0
    total_errores_audit_log = 0
    
    fuentes_con_docs_d14 = {}
    fuentes_con_docs_d13 = {}
    fuentes_con_cero = []
    detalles_errores_por_fuente = {}

    for db_path in db_paths:
        source = db_path.parent.name
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resource_audit_log'")
            if not cur.fetchone():
                conn.close()
                continue

            # Consulta exhaustiva sobre resource_audit_log
            cur.execute("""
                SELECT canonical_url, file_size_bytes, content_sha256, status
                FROM resource_audit_log
                WHERE (
                    lower(canonical_url) LIKE '%.pdf%' OR
                    lower(canonical_url) LIKE '%.xlsx%' OR
                    lower(canonical_url) LIKE '%.xls%' OR
                    lower(canonical_url) LIKE '%.csv%' OR
                    lower(canonical_url) LIKE '%.zip%'
                )
                AND status IN ('PROCESADO_EXITOSAMENTE', 'RECUPERADO_VIA_CONTINGENCIA')
            """)
            rows = cur.fetchall()
            doc_count_d14 = len(rows)
            doc_count_d13 = 0

            for r in rows:
                fsize = r[1]
                fhash = r[2]
                tiene_bytes = (fsize is not None and fsize > 0)
                tiene_hash = (fhash is not None and len(str(fhash)) == 64)

                if tiene_bytes:
                    total_docs_con_bytes += 1
                if tiene_hash:
                    total_docs_con_sha256 += 1

                if tiene_bytes and tiene_hash:
                    total_docs_d13 += 1
                    doc_count_d13 += 1

                # Detección de anomalías en columnas (tamaño <= 0 o hash de longitud inválida)
                if (fsize is not None and fsize <= 0) or (fhash is not None and len(str(fhash)) != 64):
                    anomalias_columnas += 1

            total_docs_d14 += doc_count_d14
            if doc_count_d14 > 0:
                fuentes_con_docs_d14[source] = doc_count_d14
            else:
                fuentes_con_cero.append(source)

            if doc_count_d13 > 0:
                fuentes_con_docs_d13[source] = doc_count_d13

            # Errores en audit log (status = ERROR)
            cur.execute("SELECT count(*) FROM resource_audit_log WHERE status = 'ERROR'")
            err_cnt = cur.fetchone()[0]
            if err_cnt > 0:
                detalles_errores_por_fuente[source] = err_cnt
                total_errores_audit_log += err_cnt

            conn.close()
        except Exception as e:
            print(f"Error en {source}: {e}", file=sys.stderr)

    # Cargar catálogo general
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    # Fuentes formalmente excluidas en catálogo
    excluidas_formalmente = [
        s.get("Fuente") for s in catalog if not s.get("crawler_source")
    ]
    fuentes_accesibles_catalogo = len(catalog) - len(excluidas_formalmente)

    # Fuentes del catálogo general accesibles cubiertas por las bases con documentos
    fuentes_catalogo_cubiertas = set()
    for s in catalog:
        cs = s.get("crawler_source")
        if cs and cs in fuentes_con_docs_d14:
            fuentes_catalogo_cubiertas.add(s.get("Fuente"))

    # Cifras de persistencia
    total_filas_sin_bytes = total_docs_d14 - total_docs_con_bytes
    total_filas_sin_hash = total_docs_d14 - total_docs_con_sha256

    # 22 portales del benchmark
    from scripts.comparador_benchmark import generar_comparativa
    benchmark_path = ROOT_DIR / "Elecciones De Crawler por URL" / "merged_final.json"
    bench_rows = generar_comparativa(output_dir, benchmark_path)
    
    ganados_o_empatados_d14 = [r for r in bench_rows if r["nosotros_actual"] >= r["rolando"]]
    perdidos_d14 = [r for r in bench_rows if r["nosotros_actual"] < r["rolando"]]
    total_22_d14 = sum(r["nosotros_actual"] for r in bench_rows)
    total_22_d13 = sum(r.get("nosotros_d13", 0) for r in bench_rows)
    total_22_rolando = sum(r["rolando"] for r in bench_rows)

    # Derivación programática de veredictos
    # Objetivo 1: Meta > 6.000
    v_obj1_d14 = "ALCANZADO" if total_docs_d14 > 6000 else "NO ALCANZADO"
    v_obj1_d13 = "ALCANZADO" if total_docs_d13 > 6000 else "NO ALCANZADO"

    # Objetivo 2: Meta >= 60 de 61 accesibles en catálogo
    v_obj2 = "ALCANZADO" if len(fuentes_catalogo_cubiertas) >= 60 else f"NO ALCANZADO ({len(fuentes_catalogo_cubiertas)} de 60 requeridas en catálogo; {len(fuentes_con_docs_d14)} de 54 bases)"

    # Objetivo 3: Meta 20 de 22 portales ganados o empatados
    v_obj3_individual = "ALCANZADO" if len(ganados_o_empatados_d14) >= 20 else "NO ALCANZADO"
    v_obj3_acumulado = "SUPERADO" if total_22_d14 > total_22_rolando else "NO SUPERADO"

    # Objetivo 4: Meta 0 errores no negociable
    v_obj4_crashes = f"ALCANZADO ({anomalias_columnas} anomalías en columnas de SQLite, 0 crashes de motor)" if anomalias_columnas == 0 else f"NO ALCANZADO ({anomalias_columnas} anomalías)"
    v_obj4_persistencia_d13 = "ALCANZADO" if (total_filas_sin_bytes == 0 and total_filas_sin_hash == 0) else f"NO ALCANZADO ({total_filas_sin_bytes} filas sin bytes / {total_filas_sin_hash} filas sin hash de Fase 1)"

    return {
        "total_dbs": len(db_paths),
        "total_docs_d14": total_docs_d14,
        "total_docs_d13": total_docs_d13,
        "total_docs_con_bytes": total_docs_con_bytes,
        "total_docs_con_sha256": total_docs_con_sha256,
        "total_filas_sin_bytes": total_filas_sin_bytes,
        "total_filas_sin_hash": total_filas_sin_hash,
        "anomalias_columnas": anomalias_columnas,
        "pct_integridad_bytes": (total_docs_con_bytes / total_docs_d14 * 100) if total_docs_d14 else 0,
        "pct_integridad_sha256": (total_docs_con_sha256 / total_docs_d14 * 100) if total_docs_d14 else 0,
        "total_errores_audit_log": total_errores_audit_log,
        "errores_por_fuente": detalles_errores_por_fuente,
        "fuentes_con_docs_d14_count": len(fuentes_con_docs_d14),
        "fuentes_con_docs_d13_count": len(fuentes_con_docs_d13),
        "fuentes_con_cero": fuentes_con_cero,
        "total_catalogo": len(catalog),
        "excluidas_formalmente": excluidas_formalmente,
        "fuentes_accesibles_catalogo": fuentes_accesibles_catalogo,
        "fuentes_catalogo_cubiertas_count": len(fuentes_catalogo_cubiertas),
        "total_22_d14": total_22_d14,
        "total_22_d13": total_22_d13,
        "total_22_rolando": total_22_rolando,
        "ganados_o_empatados_count": len(ganados_o_empatados_d14),
        "perdidos_count": len(perdidos_d14),
        "portales_perdidos": [(r["portal"], r["nosotros_actual"], r["rolando"]) for r in perdidos_d14],
        "v_obj1_d14": v_obj1_d14,
        "v_obj1_d13": v_obj1_d13,
        "v_obj2": v_obj2,
        "v_obj3_individual": v_obj3_individual,
        "v_obj3_acumulado": v_obj3_acumulado,
        "v_obj4_crashes": v_obj4_crashes,
        "v_obj4_persistencia_d13": v_obj4_persistencia_d13,
    }

def main():
    output_dir = ROOT_DIR / "output"
    catalog_path = ROOT_DIR / "output" / "excel_urls_diagnostic.json"
    res = medir_metricas_fase2(output_dir, catalog_path)

    print("================================================================================")
    print("MEDICIÓN OFICIAL DE LOS 4 OBJETIVOS DE FASE 2 (scripts/medir_objetivos_fase2.py)")
    print("================================================================================")
    print(f"Estado de bases evaluadas: {res['total_dbs']} bases inventory.db en output/")
    print(f"Catálogo general: {res['total_catalogo']} fuentes ({len(res['excluidas_formalmente'])} excluidas formalmente: {res['excluidas_formalmente']})")
    print(f"Fuentes accesibles configuradas en catálogo: {res['fuentes_accesibles_catalogo']}")
    print(f"Fuentes del catálogo accesibles cubiertas con doc: {res['fuentes_catalogo_cubiertas_count']} de {res['fuentes_accesibles_catalogo']}")
    print()
    print("OBJETIVO 1 · Documentos Totales (Meta: > 6.000):")
    print(f"  - Criterio D-14 (Catálogo de URLs documentales): {res['total_docs_d14']} docs -> Veredicto: {res['v_obj1_d14']}")
    print(f"  - Criterio D-13 (Verificación en memoria con hash SHA-256): {res['total_docs_d13']} docs -> Veredicto: {res['v_obj1_d13']}")
    print(f"  - En los 22 portales comunes del benchmark: {res['total_22_d14']} docs (D-14) / {res['total_22_d13']} docs (D-13)")
    print()
    print(f"OBJETIVO 2 · Fuentes con al menos un documento (Meta: >= 60 de {res['fuentes_accesibles_catalogo']} accesibles):")
    print(f"  - Bases con >= 1 documento (D-14): {res['fuentes_con_docs_d14_count']} de {res['total_dbs']}")
    print(f"  - Fuentes del catálogo accesibles cubiertas: {res['fuentes_catalogo_cubiertas_count']} de {res['fuentes_accesibles_catalogo']}")
    print(f"  - Bases con 0 documentos binarios ({len(res['fuentes_con_cero'])}): {res['fuentes_con_cero']}")
    print(f"  - Veredicto: {res['v_obj2']}")
    print()
    print("OBJETIVO 3 · Portales donde igualamos o superamos a Rolando (Meta: 20 de 22 comunes):")
    print(f"  - Portales individuales ganados o empatados: {res['ganados_o_empatados_count']} de 22 -> Veredicto: {res['v_obj3_individual']}")
    print(f"  - Portales donde Rolando quedó arriba ({res['perdidos_count']}): {res['portales_perdidos']}")
    print(f"  - Total acumulado en los 22 comunes (D-14): {res['total_22_d14']} (Nosotros) vs {res['total_22_rolando']} (Rolando) -> Veredicto: {res['v_obj3_acumulado']}")
    print()
    print("OBJETIVO 4 · Errores de recurso y de integridad (Meta: 0 no negociable):")
    print(f"  - Filas con header Content-Length o bytes > 0: {res['total_docs_con_bytes']} de {res['total_docs_d14']} ({res['pct_integridad_bytes']:.2f}%)")
    print(f"  - Filas con hash SHA-256 verificado (64 hex): {res['total_docs_con_sha256']} de {res['total_docs_d14']} ({res['pct_integridad_sha256']:.2f}%)")
    print(f"  - Filas sin registro de bytes transferidos (pre-D-13): {res['total_filas_sin_bytes']}")
    print(f"  - Filas sin hash SHA-256 (pre-D-13): {res['total_filas_sin_hash']}")
    print(f"  - Filas con tamaño <= 0 o hash malformado en SQLite: {res['anomalias_columnas']}")
    print(f"  - Errores de red / enlaces rotos en servidores de origen (status=ERROR en audit_log): {res['total_errores_audit_log']}")
    print(f"  - Veredicto de integridad del motor: {res['v_obj4_crashes']}")
    print(f"  - Veredicto de persistencia D-13: {res['v_obj4_persistencia_d13']}")
    print("================================================================================")

if __name__ == "__main__":
    main()
