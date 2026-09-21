# Diagnóstico Forense de Brechas contra Rolando y Plan de Acción (Fase 3)

**Autor del Razonamiento y Diagnóstico:** Claude (Opus 5)  
**Fecha:** 2026-09-21  
**Solicitado por:** Marlon  
**Objetivo:** Analizar con precisión quirúrgica qué hizo el crawler de Rolando en los portales donde nos supera por margen amplio (ASFI, BCB, FINRURAL, ASOFIN, IBCH, MEFP) y diseñar el plan técnico para revertir y superar esas brechas en la Fase 3.

---

## 1. Hallazgo Inicial: Una de las seis derrotas no existe (FINRURAL)

**FINRURAL 240 vs 562 no es una brecha real.** De los 583 registros de `url_descarga` de Rolando:

| Forma | Cantidad | Explicación |
|---|---:|---|
| `.pdf` canónicos sin query | 218 | Documentos reales únicos |
| `.zip` (mismo nombre base que el `.pdf`) | 218 | Contenedor idéntico del mismo archivo |
| con `?x16877=` | 126 | Duplicado exacto por parámetro de cache/tracking |

En el directorio `info_financiera/2023/` de FINRURAL existe la tripla: `financiera_01_2023.pdf`, `financiera_01_2023.pdf?x16877=`, `financiera_01_2023.zip` — tres registros computados para un solo documento.  
- **Contenido único de Rolando:** ≈ **218 documentos**.  
- **Contenido único nuestro:** **240 documentos**.  
- **Causa:** Nuestro normalizador (`discovery.py:113`) depura activamente parámetros basura como `x16877`, `utm_*`, `fbclid` y `gclid`. Nos estábamos penalizando en el benchmark comparativo por deduplicar con rigor.

---

## 2. Diagnóstico de Causa Raíz en las Cinco Brechas Reales

| Portal | Nosotros | Rolando | Brecha | Causa Dominante |
|---|---:|---:|---:|---|
| **ASFI** | 577 | 2.422 | −1.845 | Generación de URLs por patrón: **1.606 salen de UNA sola página** |
| **BCB** | 116 | 811 | −695 | `max_depth: 1`, `max_pages: 15` + ausencia de paginación HTML |
| **ASOFIN** | 18 | 195 | −177 | Cero paginación del índice WordPress + límites mezquinos (`depth: 1, pages: 35`) |
| **IBCH** | 23 | 32 | −9 | Dos rutas no sembradas (`/pavimentos/dossier/`, `/pub/`) |
| **MEFP** | 0 | 7 | −7 | Corrida abortada (`status: partial`, 60s timeout) + docs en IP `200.75.171.4` |

---

### Análisis Detallado Portal por Portal

#### ASFI (577 vs 2.422)
Las 2.422 URLs de Rolando provienen de 4 corridas disjuntas (2.428 URLs únicas). La determinante es `asfi_finrural`: **1.606 archivos descubiertos desde solo 2 páginas visitadas**, y el `url_origen` de los 1.606 es uno solo:  
`https://www.asfi.gob.bo/pb/instituciones-financieras-desarrollo`  
Esta URL **ya está en nuestras semillas** (`source_asfi.yaml:35`). Sin embargo, en nuestra corrida obtuvimos 0 de esa ruta. El log de Rolando revela la técnica:
```
[ASFI_FINRURAL] GENERADOS DESCUBIERTOS | grupos=260 | .../pb/instituciones-financieras-desarrollo
```
Rolando no siguió enlaces hipertextuales estándar: **generó URLs por plantilla temporal** sobre:  
`int_fin_des/{YYYY}/{MM}/{YYYYMM}_IFD_{Serie}.zip` (23 archivos por período × ~70 períodos, probados secuencialmente a ritmo de ~0,6 s por archivo).  
Además, nuestro YAML de ASFI tenía configurado `rate_limit_per_second: 0.05` (**20 segundos de espera por petición**); el crawler agotó el tiempo de reloj mucho antes de poder explorar el portal.

#### BCB (116 vs 811)
Se configuró con `max_depth: 1` y `max_pages: 15` a uno de los portales institucionales más voluminosos del país. Rolando le asignó: 13 semillas, `max_depth: 6` y `max_pages: 300` (213 páginas visitadas).  
La mitad de sus 811 documentos sale de listados paginados (`?page=1..9&q=reporte-estadistico`, `?page=1..2&q=pub_boletin-mensual`).  
En nuestro motor, `discovery.py` no implementa paginación HTML (la única paginación existente en el código es `strapi_v4` en `api_consumer.py` para APIs REST).  
Adicionalmente, 78 de los 811 archivos de Rolando en BCB corresponden a extensiones `.ods`, formato no incluido en `allowed_extensions` ni en la lista original de D-14.

#### ASOFIN (18 vs 195)
135 de sus 195 documentos se alojan en `wp-content/uploads/2022/03/` (`boletin100.pdf`...`boletin2xx.pdf`), correspondiente a una migración histórica masiva. Rolando llegó navegando la paginación del blog (`/index.php/boletines/page/N/`), visitando 230 páginas. Nosotros sembramos 4 permalinks fijos y limitamos a 35 páginas con profundidad 1.

#### MEFP (0 vs 7)
Nuestra corrida no completó la ejecución: `mapa_mefp.json` registró `"status": "partial"`, `"datasets": []` por un timeout de 60 segundos sin descubrir enlaces. 6 de los 7 documentos de Rolando residen en el host por IP `https://200.75.171.4/`, fuera de los dominios permitidos por defecto.

---

## 3. Brechas de Capacidad del Motor frente a Rolando

| # | Capacidad | Evidencia | Impacto en Documentos |
|---|---|---|---:|
| **C-1** | Generación de URLs por patrón temporal | `asfi_finrural.log` | ~1.606 |
| **C-2** | Paginación HTML automática (`?page=N`, `/page/N/`) | Listados en BCB, ASOFIN e IBCH | ~400+ |
| **C-3** | Presupuesto dimensionado por portal (60–300 pág, depth 4–6) | Configuración de Rolando | Transversal |
| **C-4** | Cola de prioridad real (`heapq` por puntaje de enlace) | `_score_link()` desperdiciado | Transversal |
| **C-5** | Soporte de hojas de cálculo abiertas (`.ods`, `.xlsm`) | 78 `.ods` en BCB | ~90 |

### Hallazgo Crítico sobre C-4 en nuestro Motor
`_score_link()` en `src/crawler/core/discovery.py:127-178` implementa una heurística muy elaborada para evaluar la calidad del enlace, pero **no se usa para ordenar la cola de exploración**. La frontera es un simple `deque` FIFO (`discovery.py:349-354`). El puntaje solo sirve como filtro `>= 0` y para ordenar la lista final cuando el rastreo ya terminó. En portales con presupuestos acotados (`max_pages: 15`), el orden de la cola determina por completo el éxito de la cosecha.

---

## 4. La Decisión Metodológica Clave: D-17 (Extrapolación vs Sondeo)

La capacidad C-1 (generación de patrones) rozaba la prohibición de **D-02** (sondeo especulativo). Para resolverlo con rigor técnico, Claude propone formalizar la distinción entre dos conceptos:

- **Sondeo Especulativo (Prohibido bajo D-02):** Probar variantes aleatorias o ciegas de URLs que fallaron, sin evidencia previa en el portal.
- **Extrapolación de Serie Observada (Propuesta D-17):** Cuando se observan en el HTML real ≥3 URLs confirmadas que comparten una misma plantilla y varían únicamente en un eje predecible (e.g. `{YYYY}/{MM}`), se extrapola la serie temporal hacia atrás, y **cada candidato se valida estrictamente con petición `HEAD/GET` (status 200 + Content-Type documental + bytes > 0)** antes de ingresar al catálogo.

---

## 5. Plan de Bloques para la Fase 3

| Bloque | Denominación y Alcance | Estimado | Retorno Proyectado | Estado |
|---|---|---:|---:|---|
| **B-41** | Script de diff de brecha contra Rolando + verificación del HTML de IFD en ASFI | 1 h | Diagnóstico instrumental | ✅ Aprobado (`docs/auditorias/B-41.md`) |
| **B-42** | Recalibración de presupuestos y semillas en YAML (BCB, ASOFIN, IBCH, ASFI) | 2 h | **+400 a +600 docs** | ✅ Aprobado (`docs/auditorias/B-42.md`) |
| **B-43** | Paginación HTML en `discovery.py` (`rel=next`, `?page=N`, `/page/N/`) | 4 h | **+300 a +500 docs** | ✅ Aprobado (`docs/auditorias/B-43.md`) |
| **B-44** | Frontera con prioridad real (`heapq` ordenado por `_score_link`) | 3 h | Optimización transversal | ✅ Aprobado (`docs/auditorias/B-44.md`) |
| **B-45** | Reparación de MEFP + resolución de IP `200.75.171.4` bajo D-01 | 2 h | +1 a +7 docs | ⏳ Pendiente |
| **B-46** | Incorporación de `.ods` y `.xlsm` (enmienda formal a D-14) | 2 h | **+90 docs** | ⏳ Pendiente |
| **B-47** | Extrapolación de series observadas en ASFI bajo D-17 | 6 h | **+1.600 docs** | ⏳ Pendiente |
| **B-48** | Doble métrica en comparador (**D-16**): volumen bruto vs documentos únicos | 2 h | Transparencia (FINRURAL ganado) | ⏳ Pendiente |

### Proyección de Resultados
- **Sin B-47 (solo calibración y paginación):** ASFI ~900, BCB ~750, ASOFIN ~195, IBCH ~33, MEFP ~7, FINRURAL 240. Ganamos o empatamos en 20 de 22 portales.
- **Con B-47 (extrapolación de series temporales en ASFI):** ASFI ~2.500 docs. **Ganamos o empatamos en los 22 de 22 portales del benchmark**, revirtiendo todas las brechas históricas.
