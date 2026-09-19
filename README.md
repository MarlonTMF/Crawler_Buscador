# Prospector de Datos Web Multi-Fuente (DataX · Equipo 1)

> **Estado del Proyecto:** ✅ **Cobertura y Onboarding Completados al 100% de la Meta Planificada**  
> **Suite de Pruebas:** 94 pruebas unitarias pasando (`pytest tests/ -m "not live"` · 100% verde en 14s)  
> **Metodología y Verificación:** Desarrollado bajo protocolo de doble agente (Antigravity implementación 🅰️ · Claude auditoría técnica independiente 🆑).

**Prospector de Datos Web** es una plataforma automatizada, resiliente y modular diseñada para el descubrimiento profundo, extracción, auditoría de integridad y catalogación de recursos documentales y estadísticos (PDFs, Excels, CSVs, Archivos Comprimidos) desde portales institucionales, regulatorios y financieros.

El núcleo del sistema opera desacoplando la lógica de rastreo (`core`) de las reglas de catalogación de cada entidad mediante **Adaptadores Declarativos YAML**, complementado con mecanismos avanzados de contingencia (Wayback Machine, Search Dorking, Subdomain Discovery, y renderizado headless reactivo ante desafíos WAF/Cloudflare).

---

## 📊 Estado Consolidado de Cobertura (Decisión D-04)

Siguiendo la **Decisión D-04** (`docs/decisiones.md`), la conectividad de red y la extracción documental se miden como metas independientes con checklists propios, evitando fusionar métricas de distinta naturaleza:

```
================================================================================
                    BALANCE CONSOLIDADO DE COBERTURA DATAX
================================================================================
 Track A (Conectividad del Catálogo) : 64 / 67 (95.52%) verificadas y accesibles
 Track B (Extracción de Documentos)  : 26 fuentes onboardeadas · 2,611 docs únicos
================================================================================
```

### 1. Track A — Conectividad del Catálogo Maestro (`output/excel_urls_diagnostic.json`)

Mide la disponibilidad y el estado HTTP de las entidades registradas en el catálogo maestro:

| Métrica | Registros | Porcentaje | Detalle Operativo |
|---|---|---|---|
| **HTTP 200 Directo (GET simple)** | `62` | 92.54% | Resuelven directamente por petición HTTP simple |
| **Acceso Vía Headless (WAF/Cloudflare)** | `2` | 2.99% | BCP y BCRP (requieren navegador headless por protección bot) |
| **COBERTURA EFECTIVA VERIFICADA** | **`64 / 67`** | **95.52%** | **Cifra principal de Track A (activas y accesibles)** |
| **Exclusiones Documentadas Justificadas** | `3` | 4.48% | FMI (WAF 403 Akamai), FUNDEMPRESA (410 Gone), BOLCEREALES (Disuelta) |
| **Catálogo Auditado y Clasificado** | `67 / 67` | 100.0% | Ninguna entidad queda sin diagnóstico o explicación técnica |
| **Entradas Onboardeadas a Track B** | `33 / 67` | 49.25% | Entradas con `crawler_source` asignado a adaptadores YAML activos |

> **Nota metodológica Track A (H-4):** Las **67 entradas** corresponden a la granularidad institucional (`Fuente`) en el catálogo maestro. Al deduplicar por URL efectiva (`Final_Url or Url_Original`), el universo físico comprende **58 URLs únicas**: ASFI concentra 4 entradas (`ASFI`, `ASFI - FINRURAL`, `ASFI-Valores`, `SPVS-ASFI`); APS 3 (`APS`, `APS/SOAT`, `SPVS-APS`); y BCB (`ASFI - BCB`, `BCB`), ATT (`ATT`, `SUPTRANS`), ICCO (`FDTA-Valles`, `ICCO`) y MDRyT (`MDRyT`, `MDRyT/OAP`) 2 cada una.
>
> **Destino de las 34 entradas no onboardeadas en Track B (O-6):** De las 67 entradas totales, 33 están asignadas a adaptadores YAML de Track B (26 fuentes activas con extracción verificada). De las 34 entradas restantes: **5 cadenas de retail** están segregadas a la espera de definición de negocio (`output/fuentes_pendientes_decision_negocio.json`), **3 corresponden a exclusiones técnicas justificadas** (FMI por Akamai WAF, FUNDEMPRESA por 410 Gone, BOLCEREALES por disolución institucional), y **26 son entidades de Track A** con diagnóstico de conectividad activo y verificado, programadas para onboarding progresivo en fases futuras.

---

### 2. Track B — Extracción Real de Documentos (`output/<fuente>/inventory.db`)

Mide el volumen de documentos y datos estructurados efectivamente descargados, verificados por hash SHA-256 / magic bytes y registrados en bases de datos SQLite:

- **Fuentes Onboardeadas Activas:** **26 fuentes** (25 portales externos + FINRURAL base).
- **Recursos Únicos Procesados Exitosamente:** **`2,611` documentos** (`COUNT(DISTINCT download_url) WHERE status='PROCESADO_EXITOSAMENTE'`).
- **Filas Totales en Bases de Control SQLite:** `2,633` registros.
- **Datasets Clasificados por Taxonomía:** `59` datasets estructurados.
- **Volumen Medido (Muestra):** `646.03 MB` (`677,408,955` bytes medidos sobre 101 filas con tamaño registrado — 3.84% del corpus; concentrado principalmente en ASFI con 563.4 MB y ATC con 82.4 MB. El resto de las fuentes almacena NULL/0 en `file_size_bytes` sin comprometer la integridad del recurso).
- **Fuentes Pendientes de Infraestructura:** 1 fuente (`MEFP`), cuyo servidor estatal presenta una cadena intermedia de certificados SSL incompleta (advertencia `SSL_CERT_ERROR` documentada en B-25).

#### Desglose Auditado por Fuente

| # | Fuente / Entidad | YAML de Configuración | Datasets | Filas DB | Recursos Únicos | Estado |
|---|---|---|---|---|---|---|
| 1 | **ADA Bolivia** | `config/source_ada.yaml` | 2 | 5 | 5 | ✅ OK |
| 2 | **AE (Electricidad y Nuclear)** | `config/source_ae.yaml` | 2 | 116 | 116 | ✅ OK |
| 3 | **Aduana Nacional (AN)** | `config/source_an.yaml` | 3 | 204 | 204 | ✅ OK |
| 4 | **ANAPO** | `config/source_anapo.yaml` | 1 | 100 | 100 | ✅ OK |
| 5 | **APS (Seguros y Pensiones)** | `config/source_aps.yaml` | 2 | 13 | 13 | ✅ OK |
| 6 | **ASFI (Supervisión Financiera)** | `config/source_asfi.yaml` | 5 | 73 | 68 | ✅ OK |
| 7 | **ASOFIN** | `config/source_asofin.yaml` | 1 | 25 | 25 | ✅ OK |
| 8 | **ATC Red Enlace** | `config/source_atc.yaml` | 2 | 42 | 41 | ✅ OK |
| 9 | **ATT (Telecomunicaciones)** | `config/source_att.yaml` | 2 | 67 | 67 | ✅ OK |
| 10 | **Banco Central de Bolivia (BCB)** | `config/source_bcb.yaml` | 5 | 121 | 121 | ✅ OK |
| 11 | **Banco Central del Paraguay (BCP)** | `config/source_bcp.yaml` | 2 | 47 | 36 | ✅ OK |
| 12 | **CADECO Cochabamba** | `config/source_cadeco.yaml` | 2 | 12 | 12 | ✅ OK |
| 13 | **CADEXCO Cochabamba** | `config/source_cadexco.yaml` | 2 | 10 | 10 | ✅ OK |
| 14 | **CNDC (Despacho de Carga)** | `config/source_cndc.yaml` | 1 | 94 | 94 | ✅ OK |
| 15 | **DGAC (Aeronáutica Civil)** | `config/source_dgac.yaml` | 1 | 15 | 15 | ✅ OK |
| 16 | **FAM Bolivia (Municipalidades)** | `config/source_fam.yaml` | 3 | 111 | 111 | ✅ OK |
| 17 | **FINRURAL (Piloto Base)** | `config/source_finrural.yaml` | 1 | 257 | 255 | ✅ OK |
| 18 | **IBCE - CAO** | `config/source_ibce_cao.yaml` | 1 | 30 | 30 | ✅ OK |
| 19 | **IBCH (Cemento y Hormigón)** | `config/source_ibch.yaml` | 2 | 26 | 26 | ✅ OK |
| 20 | **Instituto Nacional de Estadística (IN)** | `config/source_in.yaml` | 3 | 248 | 248 | ✅ OK |
| 21 | **INE Bolivia** | `config/source_ine.yaml` | 2 | 16 | 16 | ✅ OK |
| 22 | **Ministerio de Educación** | `config/source_min_educacion.yaml` | 2 | 15 | 15 | ✅ OK |
| 23 | **Ministerio de Minería y Metalurgia (MMYM)** | `config/source_mmym.yaml` | 3 | 108 | 105 | ✅ OK |
| 24 | **SENAMHI (Meteorología e Hidrología)** | `config/source_senamhi.yaml` | 4 | 801 | 801 | ✅ OK |
| 25 | **SEPREC (Registro de Comercio)** | `config/source_seprec.yaml` | 2 | 14 | 14 | ✅ OK |
| 26 | **SNIS (Información en Salud)** | `config/source_snis.yaml` | 3 | 63 | 63 | ✅ OK |
| 27 | *Ministerio de Economía (MEFP)* | `config/source_mefp.yaml` | 0 | 0 | 0 | ⚠️ *Sin docs (SSL)* |
| | **TOTAL CONSOLIDADO** | **26 adaptadores activos** | **59** | **2,633** | **2,611** | **96.3% activas** |

---

## 🛠️ Herramientas de Sostenimiento y Comandos CLI

El proyecto provee scripts reproducibles para auditar y monitorear el estado del sistema:

### 1. Reporte de Cobertura Reproducible (`scripts/reporte_cobertura.py`)
Calcula en tiempo real las métricas desacopladas de Track A y Track B directamente desde los datos (`excel_urls_diagnostic.json` y bases SQLite), sin recopilación manual (B-26):

```bash
# Salida en consola con formateo limpio
python scripts/reporte_cobertura.py

# Salida en formato Markdown para reportes o documentación
python scripts/reporte_cobertura.py --format markdown

# Salida en formato JSON estructurado
python scripts/reporte_cobertura.py --format json

# Modo estricto para pipelines de Integración Continua (exit code 0 si cumple umbrales, 1 si falla)
python scripts/reporte_cobertura.py --strict
```

### 2. Re-verificación Periódica de Conectividad de Track A (`scripts/reverificar_track_a.py`)
Verifica la salud de las 62 entradas en estado 200 del catálogo maestro (correspondientes a 53 URLs físicas distintas tras deduplicar), detectando regresiones cuando una URL que estaba en 200 deja de responder (B-25). Implementa fallback universal de `HEAD` a `GET stream=True`, clasificación de desafíos Cloudflare/WAF y advertencias de infraestructura SSL:

```bash
# Verificación silenciosa (solo emite alertas si hay caídas)
python scripts/reverificar_track_a.py

# Verificación detallada URL por URL
python scripts/reverificar_track_a.py --verbose

# Modo no bloqueante para inspección
python scripts/reverificar_track_a.py --no-fail-on-regression
```

### 3. Ejecución de Extracción por Fuente
Para correr el pipeline completo sobre cualquier portal configurado:

```bash
python -m src.crawler.main --config config/source_asfi.yaml --output-dir output/
```

### 4. Ejecución de la Suite de Pruebas Automatizadas
```bash
# Correr todas las pruebas no live (94 tests unitarios e integrales en ~14s)
pytest tests/ -q -m "not live"

# Correr pruebas de cobertura específicas
pytest tests/test_reporte_cobertura.py -v
pytest tests/test_reverificar_track_a.py -v
```

---

## 🌟 Capacidades del Motor de Extracción

1. **Adaptadores Declarativos Dataset-First:** Reglas de extracción, semillas, extensiones y filtros expresados limpiamente en YAML (`GenericSourceAdapter`).
2. **Reintento Automático con Headless ante 403 (B-23):** Si un servidor responde con bloqueo de bot o challenge WAF (Cloudflare/Akamai), el pipeline conmuta transparentemente a Playwright con emulación de navegador real.
3. **Calibración de Profundidad por Tamaño Real (B-24):** Presupuestos de rastreo asignados empíricamente (`max_depth`, `max_pages`) para evitar escaneos truncados o trampas de enlaces infinitos.
4. **Deduplicador Intra-corrida:** Detección de duplicados basada en hash SHA-256 e inspección de `download_url` canónica antes de la descarga física.
5. **Descompresión en Memoria (`archive_extractor.py`):** Expansión transparente de archivos `.zip`, extrayendo documentos individuales sin tocar disco temporal.
6. **Ética Web y Cumplimiento:** Respeto estricto a directivas de `robots.txt` (`smart_robots.py`) y limitación de frecuencia de peticiones (`rate_limit_per_second`).

---

## 📚 Mapa de Documentación y Arquitectura

Para entender las decisiones de diseño y la evolución técnica sin necesidad de consultar a los autores originales:

1. **[`CLAUDE.md`](CLAUDE.md):** Manual operativo central, reglas de verificación empírica (*"verificar el efecto real, no el artefacto"*), y catálogo de riesgos silenciosos.
2. **[`docs/decisiones.md`](docs/decisiones.md):** Registro canónico de decisiones técnicas con contexto, alternativas evaluadas y umbrales de reapertura:
   - `D-01`: Verificación empírica de instituciones (evitar falsos positivos de nombres parecidos).
   - `D-03`: Clasificación de protecciones bot / Cloudflare y conmutación headless.
   - `D-04`: Desacoplamiento estricto entre Conectividad (Track A) y Extracción (Track B).
   - `D-05`: FINRURAL como piloto inicial.
   - `D-08`: Aislamiento de llamadas de red y mocks en suites de pruebas.
   - `D-10`: Exclusión justificada de repositorios DSpace (CEPAL) para crawlers HTML simples.
3. **[`docs/plan_bloques.md`](docs/plan_bloques.md):** Registro de ejecución de los 27 bloques del plan (Etapas A a E), con horas estimadas vs. reales medidas (16h 38m totales).
4. **[`docs/plan_cobertura_100.md`](docs/plan_cobertura_100.md):** Plan estratégico de 100% de cobertura (Fases 0 a 4), con todos sus hitos formalmente cerrados.
5. **[`docs/protocolo_equipo.md`](docs/protocolo_equipo.md):** Definición de roles y flujo de trabajo desacoplado (Antigravity ejecuta, Claude audita).
6. **[`AI_LOG.md`](AI_LOG.md):** Bitácora histórica con 24 lecciones aprendidas (E-01 a E-24) sobre sesgos de IA, trampas silenciosas y metodologías de auditoría.
