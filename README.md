# Prospector Externo FINRURAL (`crawler_finrural`)

> **Subsistema responsable:** Equipo 1 — Extracción externa de fuentes  
> **Fuente piloto:** FINRURAL ([finrural.org.bo](https://www.finrural.org.bo/))  
> **Versión:** 1.0.0

---

## 1. Descripción del Proyecto

`crawler_finrural` es la plataforma automatizada, profesional y modular de prospección externa desarrollada por el Equipo 1 de DataX Bolivia. A diferencia de prototipos monolíticos como `example_bcb_crawler`, este sistema implementa una arquitectura basada en **Núcleo Genérico + Adaptadores Declarativos por Fuente (Dataset-First)**.

Mapea de forma dinámica las publicaciones de FINRURAL, identifica el dataset **Reporte Financiero Mensual**, extrae fechas de vigencia mediante una estrategia en 4 capas, calcula huellas digitales SHA-256, deduplica recursos y exporta simultáneamente tres contratos JSON independientes para producción, visualización y modelos de IA.

---

## 2. Arquitectura de Diseño y Principios (ADRs)

### 2.1 Modelo de Dominio Dataset-First (ADR-001)
En lugar de recorrer recursivamente todo el sitio web (lo cual generaría ruido y saturación innecesaria en páginas institucionales como historia o misión), el dominio se organiza en:

```text
Source (FINRURAL)
 └── Datasets (Reporte Financiero Mensual, Archivo Histórico)
      └── Resources (financiera_01_2026.pdf)
           └── Observations (Metadatos: fecha de corte, SHA-256, tamaño, evidencia)
```

### 2.2 Núcleo Genérico + Adaptadores Declarativos (ADR-002)
El código central (descubrimiento, extracción de fechas, canonicalización, deduplicación, reducción y exportación) es 100% reutilizable. Lo específico de FINRURAL (semillas, selectores, regex y palabras excluidas) vive en un archivo de configuración YAML (`config/source_finrural.yaml`) y su adaptador (`FinruralAdapter`).

### 2.3 Estrategia de Extracción de Vigencia en 4 Capas (ADR-003)
Aplica un orden de costo creciente para resolver la fecha del último dato (`period_end`) sin descargar ni abrir innecesariamente los archivos:
1. **Capa 1 (URL Pattern):** Regex de patrón en el nombre del archivo (`financiera_05_2025.pdf` ➔ `2025-05-31`, confianza `high`).
2. **Capa 2 (DOM Context):** Búsqueda de meses en español y años en el texto ancla o contenedores HTML adyacentes (`medium`).
3. **Capa 3 (HTTP Metadata):** Headers HTTP `Last-Modified` via solicitudes `HEAD` (`low`).
4. **Capa 4 (PDF Content Fallback):** Parsing del contenido interno del archivo en caso de ambigüedad.

### 2.4 Identidad Estable del Recurso (`resource_key`) (ADR-005)
Cada recurso genera una clave estable independiente de la URL (ej. `finrural:reporte_financiero_mensual:2026-01:pdf`). Esto permite al Motor de Conciliación detectar cuando la fuente cambia la URL de descarga sin perder la referencia al recurso original.

### 2.5 Capa de Reducción Semántica para IA (ADR-004)
Filtra el ruido de navegación HTML y genera una `content_signature` para evitar reprocesar contenido equivalente en llamadas a modelos de IA downstream, reduciendo el consumo de tokens en más del 80%.

---

## 3. Formatos de Salida (Multi-Formato — ADR-006)

Al finalizar la prospección, el sistema exporta tres archivos JSON en la carpeta `output/`:

1. **`mapa_finrural.json` (Contrato Oficial Estandarizado — `ExternalSourceMap` v1.0.0):**
   * Consumido por el Motor de Conciliación y Auditoría Interna (Equipo 1 + Equipo 2).
   * Contiene metadatos de Nivel 5: hashes `sha256`, tamaño en bytes, `etag`, `last_modified`, `period_start`, `period_end`, confianza y evidencias.
   * **Validado 100%** contra el esquema formal `schemas/source-map.schema.json` (JSON Schema Draft 2020-12).

2. **`mapa_finrural_tree.json` (Formato Jerárquico BCB — Tree View):**
   * Compatible con el visor web estático del prototipo (`web/index.html`).
   * Organiza la información en 5 niveles de carpetas finalizando en sufijos `.csv` con atributos `descripcion` y `url_descarga`.

3. **`mapa_finrural_compact.json` (Vista Compacta para IA):**
   * Matriz reducida sin boilerplate para consumo rápido por agentes LLM.

---

## 4. Buenas Prácticas de Web Scraping y Ética

El cliente HTTP ([`src/crawler/core/fetcher.py`](src/crawler/core/fetcher.py)) incluye controles estrictos para garantizar un rastreo ético y prevenir bloqueos o baneos:

* **Cumplimiento Automático de `robots.txt`:** Utiliza `urllib.robotparser` para verificar dinámicamente que la URL a visitar esté explícitamente autorizada.
* **Rate-Limiting (Control de Frecuencia):** Pausa obligatoria de 1.0 segundo entre peticiones al mismo dominio (`rate_limit_per_second: 1.0`).
* **Optimización con Solicitudes `HEAD`:** Consulta metadatos HTTP sin descargar el cuerpo binario de los archivos PDF.
* **Tolerancia a Fallos y Manejo de HTTP 429:** Reintentos automáticos con backoff exponencial cuando el servidor responde `429 Too Many Requests`.
* **User-Agent Transparente:** Identificación clara: `ProspectorExterno/1.0 (+contacto-proyecto-datax)`.

---

## 5. Estructura del Repositorio

```text
crawler_finrural/
├── config/
│   └── source_finrural.yaml       # Configuración declarativa de FINRURAL
├── schemas/
│   └── source-map.schema.json     # JSON Schema borrador 2020-12
├── src/
│   └── crawler/
│       ├── core/
│       │   ├── models.py          # Modelos de dominio Pydantic v2
│       │   ├── fetcher.py         # Cliente HTTP ético con robots.txt y rate-limit
│       │   ├── discovery.py       # Descubrimiento enfocado en datasets
│       │   ├── extractor.py       # Extractor de vigencia en 4 capas y metadatos
│       │   ├── canonicalizer.py   # Canonicalización de URLs y resource_key
│       │   ├── reducer.py         # Reducción semántica para consumo por IA
│       │   ├── exporter.py        # Exporter multi-formato (Standard, Tree, Compact)
│       │   └── orchestrator.py    # Orquestador del pipeline end-to-end
│       ├── sources/
│       │   ├── base_adapter.py    # Interfaz abstracta para adaptadores
│       │   └── finrural_adapter.py# Adaptador declarativo para FINRURAL
│       ├── validators/
│       │   └── schema_validator.py# Validador de JSON Schema
│       └── main.py                # Punto de entrada CLI
├── tests/
│   ├── test_canonicalizer.py
│   ├── test_exporter.py
│   ├── test_extractor.py
│   ├── test_finrural_adapter.py
│   └── test_models_and_schema.py
├── .gitignore                     # Exclusión de cache, entorno virtual y outputs
├── pyproject.toml                 # Configuración de paquete Python
└── README.md
```

---

## 6. Instalación y Uso

### 6.1 Preparación del Entorno
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 6.2 Ejecución de la Prospección Externa
```bash
python3 -m crawler.main --config config/source_finrural.yaml --output-dir output/ --verbose
```

### 6.3 Ejecución de la Suite de Pruebas Automated (Pytest)
```bash
PYTHONPATH=src pytest tests/ -v
```
