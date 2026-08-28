# Prospector de Datos Web Multi-Fuente (DataX - Equipo 1)

**Prospector de Datos Web** es una plataforma automatizada, resiliente y modular diseñada para el descubrimiento, extracción, auditoría y catalogación de recursos públicos documentales y estadísticos (PDFs, Excels, Archivos Comprimidos) desde portales institucionales y financieros.

A diferencia de un scraper monolítico, este sistema implementa un **Núcleo de Descubrimiento Multipropósito** con **Adaptadores Declarativos por Fuente**, y mecanismos avanzados de contingencia para la búsqueda profunda de URLs, garantizando la recuperación de datos incluso ante arquitecturas web adversas, recursos descontinuados, o enlaces caídos.

---

## 🌟 Características Principales

### 1. Arquitectura Dataset-First y Adaptadores Declarativos
El núcleo (`core`) es 100% reutilizable. Las reglas de negocio, palabras clave y exclusiones de cada fuente se configuran de manera declarativa en YAML (ej. `config/source_finrural.yaml`, `config/source_bbv.yaml`). El sistema clasifica automáticamente los enlaces encontrados en **Datasets** lógicos (ej. *Reportes Financieros*, *Memorias Anuales*, *Estadísticas Bursátiles*).

### 2. Motores Avanzados de Búsqueda y Descubrimiento de URLs
El sistema implementa múltiples estrategias (activas y pasivas) para buscar listas de URL y recursos más allá del rastreo convencional (Crawling BFS/DFS):

* **Sitemap Discovery (`smart_robots.py`):** Detección e ingesta automática de sitemaps XML declarados en `robots.txt` o en rutas estándar.
* **Enumeración de Subdominios (`subdomain_finder.py`):** Integración con Certificate Transparency (`crt.sh`) para descubrir subdominios ocultos asociados a la entidad.
* **Search Dorking Programático (`search_dorker.py`):** Automatización de búsquedas avanzadas en Bing Search o Google Custom Search (ej. `site:dominio.com filetype:pdf "reporte"`).
* **Motor Wayback (`wayback_engine.py`):** Consulta a la API CDX de Web Archive para descubrir URLs históricas y recuperar archivos eliminados o movidos en el dominio.

### 3. Contingencia y Resiliencia Activa (`contingency_engine.py`)
Si el sistema detecta que un recurso ha sido movido o presenta errores (404, 403, timeout), activa automáticamente protocolos de contingencia:
* **Resolución de Variantes de URL:** Prueba variaciones de protocolo (HTTP/HTTPS), subdominios `www.`, rutas y extensiones territoriales (ej. `.org` a `.org.bo`).
* **Fallback a Wayback Machine:** Si la fuente primaria falla por completo, descarga el recurso directamente desde la última instantánea disponible en *archive.org*.

### 4. Cliente HTTP Ético e Híbrido (`fetcher.py`)
* **Respeto a `robots.txt`:** Verificación estricta de políticas.
* **Control de Frecuencia (Rate-Limit):** Manejo de errores HTTP 429 y retrasos (backoff) exponenciales.
* **Fallback a Navegador (Headless Playwright):** Permite renderizado de páginas SPA (React/Vue/Angular) u ofuscadas si la petición HTTP tradicional no encuentra enlaces documentales.

### 5. Descompresión Automática en Memoria (`archive_extractor.py`)
Descarga contenedores comprimidos (`.zip`, `.tar`, `.tgz`, `.bz2`) directamente en memoria, filtrando y extrayendo de forma transparente los documentos internos relevantes (`.pdf`, `.xlsx`, `.csv`) asignándoles metadatos independientes y trazabilidad del contenedor origen.

### 6. Extracción de Vigencia en 4 Capas (`extractor.py`)
Jerarquía de bajo costo a alto costo para determinar la vigencia de un documento:
1. **URL Pattern:** Regex sobre nombres de archivo (ej. `financiera_05_2025.pdf`).
2. **DOM Context:** Análisis de texto adyacente (nodos padre, texto ancla).
3. **HTTP Metadata:** Evaluación de `Last-Modified` vía `HEAD`.
4. **Fallback Hash/Content:** (Opcional) Análisis de contenido directo.

### 7. Panel de Diagnóstico y Auditoría Local (`dashboard_server.py`)
Incluye una interfaz web local para monitorear ejecuciones, evaluar puntajes de calidad (0.0 a 4.0), visualizar causas de fallos ("Diagnósticos Excel"), y aprobar manualmente mapeos de contingencia o redirecciones.
Base de datos SQLite integrada (`control_db.py`) para historial de estado por recurso (PENDIENTE, PROCESADO, ERROR, RECUPERADO).

### 8. Exportación Estandarizada
Exporta catálogos JSON listos para ingestión humana o IA:
- **Estandarizado (`mapa_*.json`):** Contrato principal detallado.
- **Árbol Jerárquico (`mapa_*_tree.json`):** Formato agrupado por gestión y niveles compatibles con el BCB.
- **Compacto para IA (`mapa_*_compact.json`):** Vista reducida semánticamente generada por `reducer.py`.

---

## 🏗️ Estructura del Proyecto

```text
crawler_finrural/
├── config/
│   ├── source_finrural.yaml       # Configuración para FINRURAL
│   ├── source_bbv.yaml            # Configuración para Bolsa Boliviana de Valores
│   └── moved_urls.json            # Historial persistente de mapeos/redirecciones
├── dashboard/                     # Archivos estáticos de la interfaz web de auditoría
├── scripts/                       # Scripts auxiliares (check_urls.py, etc.)
├── src/
│   └── crawler/
│       ├── core/                  # Núcleo 100% reutilizable (Motores, Fetcher, Modelos)
│       ├── sources/               # Adaptadores Declarativos por institución
│       ├── validators/            # Validadores de JSON Schemas
│       └── main.py                # CLI de ejecución del Crawler
├── tests/                         # Pruebas automatizadas del núcleo y adaptadores
├── benchmark_runner.py            # Orquestador para pruebas masivas en frío (50+ fuentes)
├── dashboard_server.py            # Servidor local del panel de auditoría (API/UI)
├── pyproject.toml                 # Dependencias
└── README.md                      # Documentación
```

---

## 🚀 Instalación y Uso

### 1. Requisitos e Instalación

Requiere **Python 3.9+**.

```bash
# Crear entorno virtual
python -m venv .venv

# Activar entorno (Linux/macOS)
source .venv/bin/activate
# Activar entorno (Windows)
.venv\Scripts\activate

# Instalar paquete y dependencias
pip install -e .

# Opcional: instalar Playwright para rendering headless (Fallback SPA)
pip install playwright
playwright install
```

### 2. Ejecutar la Prospección

Para ejecutar el crawler en una fuente específica, utiliza el adaptador YAML correspondiente:

**Para FINRURAL:**
```bash
python -m crawler.main --config config/source_finrural.yaml --output-dir output/
```

**Para Bolsa Boliviana de Valores (BBV):**
```bash
python -m crawler.main --config config/source_bbv.yaml --output-dir output/
```

### 3. Iniciar el Panel de Diagnóstico Web

El panel permite analizar los resultados, ver logs de jobs paralelos y resolver URLs caídas.

```bash
python dashboard_server.py
```
> Ingresa a `http://127.0.0.1:8000` en tu navegador.

### 4. Ejecutar Benchmark de Fuentes

Permite evaluar en frío el descubrimiento en docenas de fuentes pre-configuradas (BM, ASFI, BCB, etc.):

```bash
python benchmark_runner.py
```

### 5. Ejecutar Pruebas Automatizadas

```bash
pytest tests/ -v
```

---

## ⚙️ Opciones de Motores de Búsqueda (Opt-in en YAML)

En los archivos de configuración (`config/source_*.yaml`), puedes activar opciones pasivas para descubrir listas de URLs no visibles navegando, modificando la sección `crawl`:

```yaml
crawl:
  use_sitemaps: true                 # Busca y procesa robots.txt y sitemap.xml
  use_wayback: true                  # Consulta a la API CDX de archive.org
  use_search_dorking: true           # Consulta a Google/Bing APIs (Requiere llaves de entorno)
  use_subdomain_enumeration: true    # Búsqueda en crt.sh
```

---

## 🛡️ Manejo de Límites y Ética

Este sistema respeta incondicionalmente las buenas costumbres web:
- Limitador estricto `rate_limit_per_second` nativo.
- Verificación total del `robots.txt` a través de `urllib.robotparser`.
- Priorización de método `HEAD` para verificación previa de metadatos, evitando consumir ancho de banda si el archivo no cambió (ETag, Last-Modified).
- Alertas automatizadas de derivación volumétrica (`drift_monitor.py`) que evitan sobrecargar el sistema en caso de loops de redirección o trampas del servidor.
