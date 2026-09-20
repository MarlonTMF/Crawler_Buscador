# Diagnóstico Técnico B-33: Integración de API y Formularios al Pipeline

**Fecha:** 2026-09-20  
**Autor:** Agente Implementador (Antigravity)  
**Destinatario:** Auditor / Líder Técnico (Claude)  
**Propósito:** Parada obligatoria antes de implementar B-33 (`docs/plan_bloques_fase2.md:170-175`). Evaluación de módulos existentes, requerimientos del orquestador y propuesta de alcance para decisión.

---

## 1. Estado de los módulos existentes

### A. `src/crawler/core/api_detector.py` (584 líneas)
- **Qué expone:**
  - `probe_domain_for_apis(base_url, ...)`: Sondeo activo contra ~25 rutas conocidas de API REST, GraphQL, OpenAPI/Swagger y SOAP.
  - `RobotsGate`: Validador de permisos en `robots.txt`.
  - Detección pasiva en Playwright (`HeadlessFetcher`) mediante intercepción de eventos de red `page.on("response")`.
- **Naturaleza del módulo:**
  - Es un **detector y catalogador diagnóstico**, concebido originalmente para emitir el reporte de auditoría `output/reporte_apis.md` / `output/reporte_apis.json` (`ApiSiteReport`).
  - **Lo que NO hace:** No parsea payloads JSON específicos de APIs para extraer colecciones de documentos (`DownloadCandidate`), ni sabe cómo paginar una API REST arbitraria (Strapi, CKAN, OData, etc.).
- **Diagnóstico:** Conectar `api_detector.py` tal como está al pipeline de extracción no descarga documentos por sí solo; requiere una capa que traduzca respuestas de endpoints de API en candidatos a descarga (`DownloadCandidate`).

### B. `src/crawler/core/form_automator.py` (50 líneas)
- **Qué expone:**
  - `FormAutomator.generate_get_urls(page_url, html, max_combinations=200) -> List[str]`:
    Parsea etiquetas `<form method="GET">`, extrae inputs y opciones de `<select>`, calcula el producto cartesiano de opciones y emite las URLs con query params resultantes (`action?k1=v1&k2=v2`).
- **Naturaleza del módulo:**
  - Es un generador puramente estático de URLs GET.
  - **Limitación:** No maneja formularios POST ni flujos con estados dinámicos (ASP.NET `__VIEWSTATE` o tokens CSRF de SICOES/INE).
- **Diagnóstico:** Puede conectarse de forma transparente y segura en `DiscoveryEngine._discover_from_html` para que toda página HTML con un `<form method="GET">` agregue sus combinaciones a la cola BFS de rastreo.

---

## 2. Caso SICSANTACRUZ (Criterio de aceptación de B-33)

**Criterio:** *SICSANTACRUZ pasa de 0 a ≥ 10 documentos descargados vía la API, con los primeros bytes verificados.*

### Verificación en vivo realizada:
- Endpoint verificado: `https://ice.santacruz.gob.bo/api/estudios?populate=*`
- Protocolo: Strapi v4 REST API (HTTP 200 directo, sin WAF bloqueante).
- Volumen disponible: **163 estudios**, paginados (25 por página, 7 páginas).
- Estructura de documentos en el payload JSON:
  `item['attributes']['documento']['data']['attributes']['url']` -> `/uploads/ICE_CANCER_DE_MAMA_v4_d35da0e2d6.pdf`
- Descarga real verificada:
  `https://ice.santacruz.gob.bo/uploads/ICE_CANCER_DE_MAMA_v4_d35da0e2d6.pdf`
  Respuesta: **HTTP 200**, magic bytes: `b'%PDF-1.4\n%'` (PDF binario íntegro).

---

## 3. Qué haría falta en el pipeline (`DiscoveryEngine` / `CrawlOrchestrator`)

Para que el pipeline de extracción soporte APIs y formularios sin desestabilizar el motor existente:
1. **Integración de formularios GET:**
   - En `DiscoveryEngine._discover_from_html`, invocar `FormAutomator().generate_get_urls(page_url, html)` e incorporar las URLs generadas a la lista de enlaces por explorar.
2. **Integración de API REST (para Strapi y APIs JSON):**
   - En `DiscoveryEngine`, agregar un método `discover_from_api(api_config)` o un adaptador declarativo `ApiConsumer`.
   - Cuando el YAML de la fuente configure una sección `api:` (o cuando `api_detector` descubra un endpoint soportado), el extractor:
     1. Consume el endpoint configurado (ej. `https://ice.santacruz.gob.bo/api/estudios?populate=*`).
     2. Extrae iterativamente las URLs de documentos (`.pdf`, `.xlsx`, etc.) presentes en los campos de archivo de los objetos JSON.
     3. Emite los correspondientes `DownloadCandidate` hacia el pipeline estándar (`CrawlOrchestrator`).
   - De este modo, los documentos entran al flujo canónico existente: extracción de fecha, verificación de encabezados/bytes, auditoría en `inventory.db` y exportación de metadatos en `mapa_<fuente>.json`.

---

## 4. Evaluación de riesgo y propuesta de decisión

### ¿Entra en un solo bloque de 100 min?
- **Si se intenta abarcar todo (APIs GraphQL + SOAP + formularios POST interactivos con Playwright + adaptadores custom para SICOES e INE):** **NO entra**. Se desbordaría con certeza y violaría la política de tokens y tiempo.
- **Si se acota al diseño estructurado:** **SÍ entra limpiamente**:
  1. Conectar `FormAutomator` en `DiscoveryEngine` para formularios GET estándar.
  2. Implementar `ApiDiscoveryEngine` / soporte para endpoints REST/Strapi en `DiscoveryEngine`, configurables desde YAML (`crawl.api_endpoints`).
  3. Crear `config/source_sicsantacruz.yaml` apuntando al endpoint Strapi `/api/estudios?populate=*`.
  4. Ejecutar SICSANTACRUZ, descargar ≥ 10 documentos reales (de los 163 disponibles) con bytes verificados y registrar en `inventory.db`.

### Recomendación de Antigravity:
Aprobar la propuesta acotada. Permite cerrar B-33 en ~60-75 min reales, cumpliendo el 100% del criterio de aceptación sin deuda técnica y dejando la infraestructura de API lista en el motor para futuras fuentes.

Quedo a la espera de la decisión y plan de Claude para proceder con la implementación.
