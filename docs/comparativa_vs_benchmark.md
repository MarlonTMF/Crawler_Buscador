# Comparativa Final contra el Benchmark — Cierre de Fase 2 (B-40)

Medición final al cierre de la Fase 2 (2026-09-21), contra el benchmark original de septiembre de 2026 (`Elecciones De Crawler por URL/merged_final.json`). Todas las cifras provienen de la consulta programática reproducible sobre las bases de datos `inventory.db` de cada portal (`scripts/comparador_benchmark.py`), aplicando estrictamente la Decisión **D-14** (solo formatos binarios documentales `.pdf`, `.xlsx`, `.xls`, `.csv`, `.zip` y estados exitosos/contingencia con verificación de integridad y bytes reales).

---

## 1. Tabla Comparativa sobre los 22 Portales Comunes

La comparación contra el benchmark se realiza de forma curada y estricta sobre los **22 portales comunes** evaluados históricamente, consolidando fuentes multidominio (como las 4 de ASFI y las 2 de APS):

| Portal | Douglas | Rolando | Nosotros (sep) | Baseline (19-sep) | **Nosotros (actual)** | Δ vs Baseline |
|---|---:|---:|---:|---:|---:|---:|
| senamhi | 0 | 0 | 0 | 798 | **798** | 0 |
| ae | 0 | 0 | 3 | 113 | **131** | +18 |
| fam | 0 | 0 | 0 | 111 | **111** | 0 |
| mmym | 0 | 28 | 69 | 107 | **107** | 0 |
| anapo | 0 | 0 | 0 | 99 | **99** | 0 |
| cndc | 0 | 0 | 1 | 93 | **93** | 0 |
| att | 0 | 27 | 58 | 65 | **65** | 0 |
| atc | 0 | 20 | 2 | 39 | **39** | 0 |
| ibce_cao | 0 | 24 | 0 | 26 | **60** | +34 |
| cadexco | 0 | 1 | 0 | 10 | **10** | 0 |
| bcb | 13 | 811 | 103 | 116 | **116** | 0 |
| finrural | 0 | 562 | 5 | 129 | **240** | +111 |
| asfi | 13 | 2422 | 103 | 61 | **577** | +516 |
| ada | 1 | 1075 | 5 | 2 | **1090** | +1088 |
| asofin | 0 | 195 | 5 | 18 | **18** | 0 |
| ibch | 0 | 32 | 0 | 23 | **23** | 0 |
| ine | 0 | 112 | 53 | 9 | **305** | +296 |
| aps | 22 | 24 | 18 | 12 | **170** | +158 |
| dgac | 12 | 42 | 144 | 12 | **1196** | +1184 |
| seprec | 0 | 12 | 64 | 12 | **154** | +142 |
| snis | 9 | 9 | 31 | 9 | **9** | 0 |
| mefp | 0 | 7 | 0 | 0 | **0** | 0 |
| **TOTAL** | **70** | **5403** | **664** | **1864** | **5411** | **+3547** |

### Síntesis del Benchmark Común
- **Crecimiento vs Baseline (19-sep):** Pasamos de **1.864 a 5.411 documentos** (+3.547 documentos, un incremento de **+190%** en los mismos portales).
- **Victoria sobre el Benchmark Histórico de Rolando:** Con **5.411 documentos**, superamos el total consolidado de Rolando (**5.403 documentos**) por **+8 documentos**, manteniendo un estándar de integridad documental (D-13 y D-14) significativamente más riguroso.
- **Portales Ganados o Empatados:** **16 de 22 portales** (72.7%), frente a 12 de 22 en la línea base de la Fase 1.

---

## 2. Evaluación Literal de los 4 Objetivos de la Fase 2

Según lo estipulado en `docs/plan_bloques_fase2.md` (§ *Objetivos y criterios de éxito de la fase*), a continuación se reportan los cuatro objetivos medidos de forma literal, sin ajustes de conveniencia y con la causa técnica detallada de cada resultado:

| # | Objetivo | Línea Base (19-sep) | Meta Fase 2 | Resultado Medido | Estado |
|---|---|---:|---:|---:|:---:|
| 1 | **Documentos totales** | 2.357 | **> 6.000** | **10.985** (global en `output/`) / **5.411** (22 comunes) | **ALCANZADO** |
| 2 | **Fuentes con ≥ 1 documento** | 26 | **≥ 60** de 64 accesibles | **46** (con base `inventory.db`) | **NO ALCANZADO** |
| 3 | **Portales donde igualamos o superamos a Rolando** | 12 de 22 | **20 de 22** | **16 de 22** (pero superado en el total: 5.411 vs 5.403) | **NO ALCANZADO** |
| 4 | **Errores de recurso no controlados / integridad** | 0 | **0** (no negociable) | **0** crashes o corruptos / **100%** SHA-256 verificado | **ALCANZADO** |

---

### Análisis Detallado Objetivo por Objetivo

#### Objetivo 1 · Documentos Totales (> 6.000) — ALCANZADO
- **Medición:** El universo total descargado y verificado en el repositorio asciende a **10.985 documentos binarios reales** a través de 54 bases de inventario en `output/`.
- **Benchmark Común:** Aun si la medición se restringiera exclusivamente a los 22 portales comunes del benchmark original, el crawler alcanzó **5.411 documentos**, multiplicando casi por tres la línea base inicial (1.864).
- **Conclusión:** La meta de superar los 6.000 documentos a nivel de proyecto se superó con un excedente de **+4.985 documentos (+83%)**.

#### Objetivo 2 · Fuentes con al menos un documento (≥ 60 de 64 accesibles) — NO ALCANZADO (46 / 60)
- **Medición:** De las 67 fuentes del catálogo general (`output/excel_urls_diagnostic.json`), **46 fuentes** cuentan con al menos un documento binario válido descargado, verificado por hash y con bytes reales.
- **Causa Técnica:**
  1. **6 Exclusiones Formales Justificadas:** BCRP (Cloudflare Turnstile bloqueante), BOLCEREALES (entidad formalmente disuelta), CEPAL (requiere integración API/OAI-PMH), FDTA-Valles (error de origen en Excel de entrada), FMI (bloqueo estricto 403 / anti-bot) y FUNDEMPRESA (cierre definitivo y liquidación estatal tras creación de SEPREC).
  2. **8 Fuentes con `inventory.db` y 0 documentos bajo D-14:**
     - *NIH (National Institutes of Health):* Los reportes estadísticos y notas de investigación se publican directamente en la web como artículos HTML estructurados sin adjuntos binarios. Bajo D-14, fueron reclasificados como `sin_documentos_detectados`.
     - *FEGASACRUZ:* Portal en construcción con landing page estática sin enlaces institucionales operativos (`reachable_unverified`).
     - *Data.Gov:* Portal de metadatos gubernamentales abiertos; los datasets corresponden a hipervínculos externos distribuidos en agencias de EE. UU.
     - *DolarBlueBolivia:* Cotizaciones cambiarias en tiempo real servidas mediante componentes dinámicos JavaScript / tablas HTML, sin publicación de reportes binarios descargables.
     - *MEFP & SICOES:* Plataformas gubernamentales ASP.NET (ASPX) basadas en postbacks de sesión, ViewState dinámico y formularios POST complejos (B-33b se cerró sin implementación tras constatar ausencia de formularios GET simples en el catálogo).
     - *SIGMA:* Sistema de gestión gubernamental protegido por autenticación e intranet institucional.
     - *BCCH (Banco Central de Chile):* Estructura de navegación dinámica y bloqueos de seguridad que impidieron la extracción directa sin renderizado especializado.

#### Objetivo 3 · Portales donde igualamos o superamos a Rolando (20 de 22) — NO ALCANZADO (16 / 22)
- **Medición:** Superamos o igualamos a Rolando en **16 de los 22 portales comunes** (72.7%).
- **Donde Ganamos o Empatamos (16 portales):**
  - Victorias masivas en portales donde Rolando obtuvo 0 gracias al mapa de fuentes corregido: **SENAMHI** (798 vs 0), **AE** (131 vs 0), **FAM** (111 vs 0), **ANAPO** (99 vs 0), **CNDC** (93 vs 0).
  - Victorias por calibración de profundidad real (B-28): **DGAC** (1.196 vs 42, +1.154), **ADA** (1.090 vs 1.075, +15), **INE** (305 vs 112, +193), **APS** (170 vs 24, +146), **SEPREC** (154 vs 12, +142).
  - Victorias en portales sectoriales y empresariales: **MMYM** (107 vs 28), **ATT** (65 vs 27), **IBCE-CAO** (60 vs 24), **ATC** (39 vs 20), **CADEXCO** (10 vs 1), y empate en **SNIS** (9 vs 9).
- **Donde Rolando quedó arriba (6 portales):**
  - **ASFI (577 vs 2.422):** Rolando logró descargar miles de series históricas empaquetadas en ZIPs dinámicos y subdirectorios AJAX. Aunque subimos de 61 a 577, una porción de las series sigue protegida detrás de llamadas JS dinámicas.
  - **BCB (116 vs 811):** Rolando aplicó una profundidad de rastreo no restrictiva (>5 niveles) sobre el archivo histórico de resoluciones y normativas.
  - **FINRURAL (240 vs 562):** Subdirectorios antiguos de balances y boletines no referenciados en el árbol de navegación principal.
  - **ASOFIN (18 vs 195):** Archivos mensuales históricos paginados.
  - **IBCH (23 vs 32):** Diferencia marginal de 9 boletines.
  - **MEFP (0 vs 7):** Formularios ASPX.
- **Compensación y Resultado Neto:** A pesar de no alcanzar la meta de 20 portales individuales, el volumen masivo capturado en DGAC (+1.154), ADA (+15) e INE (+193) compensó con creces la diferencia, permitiendo **ganar en el acumulado total del benchmark (5.411 vs 5.403)**.

#### Objetivo 4 · Errores de Recurso (Meta 0 no negociable) — ALCANZADO
- **Integridad y Ausencia de Corrupción:** El 100% de los 10.985 documentos catalogados cuenta con archivo físico verificado, tamaño mayor a cero bytes (`file_size_bytes > 0`) y firma criptográfica SHA-256 comprobada. No se registraron crashes no controlados del motor, truncamientos silenciosos ni corrupciones de base de datos.
- **Gestión de Errores de Red Remota:** En el `resource_audit_log` se registraron **222 enlaces rotos / errores HTTP 404** en los servidores de origen (145 en MDRyT, 46 en BBV, 18 en BCP, etc.) correspondientes a archivos eliminados o inaccesibles en los portales remotos. El crawler capturó y aisló estos fallos de red sin interrumpir el pipeline ni contaminar el inventario final.

---

## 3. Impacto Medido de las Palancas de la Fase 2

A lo largo de los bloques B-28 a B-39 se activaron y midieron las palancas de aceleración:

1. **Profundidad de Rastreo (B-28):** Fue la palanca de mayor retorno de todo el proyecto. La recalibración de los 6 portales que estaban congelados en `max_depth: 0` aportó **+3.384 documentos** directos (ADA de 2 a 1.090; DGAC de 12 a 1.196; ASFI de 61 a 577; INE de 9 a 305; SEPREC de 12 a 154; APS de 12 a 170).
2. **Renderizado Headless (B-29):** Desbloqueó el acceso a portales con rendering JavaScript y Single Page Applications, permitiendo a BCP alcanzar 1.711 documentos catalogados.
3. **Extracción de Comprimidos (B-30):** Verificación de descompresión automática en producción, aportando documentos desglosados en ASFI e IN.
4. **Sitemaps XML (B-31):** Descubrimiento masivo estructurado que amplió la cobertura en portales como `ibce_cao` (+34 docs) y `ae` (+18 docs).
5. **Series Históricas y Wayback Contingency (B-32, B-36..B-38):** Incorporación de la máquina de contingencia Wayback para rescatar documentos cuyos enlaces originales sufrieron rotura o migración de CMS (e.g. FIFA, SENAMHI).
6. **Integración Declarativa de APIs (B-33a):** Onboarding exitoso del portal Strapi REST de SICSANTACRUZ, sumando 201 documentos con metadatos estructurados.
7. **Onboarding de Nuevos Lotes (B-34 a B-38):** Expansión masiva a más de 30 fuentes del catálogo general bajo el estándar D-13/D-14, incorporando miles de documentos binarios en BBV, Banco Mundial, ICCO, ITU, MDRyT, VIPFE, OBA, SABSA y MHE.

---

## 4. Conclusión y Veredicto Final

La Fase 2 cumplió su propósito fundamental: **superar el benchmark histórico de Rolando en el acumulado de portales comunes (5.411 vs 5.403) y elevar la producción documental global del proyecto a 10.985 documentos verificados**, manteniendo un control de calidad y reproducibilidad técnica sin precedentes en el proyecto.
