# Decisiones técnicas — Prospector DataX / crawler_finrural

Formato: contexto, alternativas descartadas, decisión, razón, consecuencia,
umbral que la reabriría, y fecha de verificación. Una decisión cerrada no se
reabre sin una razón nueva — si aparece, se agrega una entrada, no se borra
la anterior.

---

## D-01 · Ninguna URL se acepta sin verificar contenido, nunca solo por status 200

**Contexto.** Un status HTTP 200 confirma que *algo* respondió, no que sea la
institución correcta. Pasó tres veces antes de que se formalizara esta regla:
Gemini sugirió `cadex.org` para CADEXCO (era CADEX Santa Cruz, institución
distinta), sugirió `ibce.org.bo` para IBCH (era IBCE, comercio exterior, no
cemento/hormigón), y `fetcher.py` escribió automáticamente `bcp.org` para BCP
sin verificar — se detectó y se corrigió antes de contaminar el dataset.

**Decisión.** Toda URL candidata (sugerida por IA, por investigación externa,
o encontrada a mano) se acepta solo si el contenido de la página menciona
palabras clave de la institución real. Un ejemplo de esta disciplina
funcionando: `sicsantacruz.com`, que una investigación externa (`URLsFaltantes.md`)
dio por "confianza alta" el 2026-09-11, resultó ser una página de parking de
Namecheap al verificarla el 2026-09-17 — el dominio expiró y fue
re-registrado por un tercero en el medio. Sin la verificación de contenido,
hubiera quedado aceptada como válida en el dataset.

**Consecuencia.** Cada resolución de URL en `config/moved_urls.json` lleva
`reason` y `matched_keywords`, y cada intento (exitoso o no) queda en
`output/url_resolution_log.json` con la respuesta cruda de la IA cuando
aplica — auditable, no solo el resultado final.

**Umbral que reabriría esto.** Ninguno — esta regla no se relaja por
conveniencia ni urgencia.

**Verificado el.** 2026-09-17 (caso SICSANTACRUZ), acumulando evidencia desde
sesiones anteriores.

---

## D-02 · `allow_variants=True` solo para dominios raíz muertos, nunca para URLs de documentos específicos

**Contexto.** Probar variantes mecánicas (www, TLD, esquema) tiene sentido
cuando un dominio entero no resuelve. Aplicado a una URL de reporte/documento
puntual que falla, generó sondeos larguísimos y resoluciones sin sentido —
probó variantes de una URL con ruta completa, no del dominio.

**Decisión.** `resolve_dead_domain(..., allow_variants=True)` se usa
exclusivamente cuando el dominio raíz no resuelve DNS. Para verificar una URL
puntual que falla, se hace un chequeo directo simple (GET con headers de
navegador), sin generar variantes.

**Consecuencia.** `resolve_dead_domains.py` distingue ambos casos en su
lógica de reintento.

**Umbral que reabriría esto.** Si se identifica un caso donde una reestructuración institucional migró sistemáticamente rutas completas a un nuevo TLD o esquema conservando el path idéntico; aun así, solo se aplicaría tras confirmar que el dominio base cambió, nunca por sondeo ciego de URLs de documentos.

**Verificado el.** 2026-09-17 (sesión previa, ver `RESUMEN_SESION.md`).

---

## D-03 · Sitios protegidos por Cloudflare/WAF: reintento automático condicional con navegador real ante 403 [CERRADA]

**Contexto.** BCP (Banco Central del Paraguay) devolvía 403 en las URLs de
documentos y en la portada con clientes HTTP simples (`curl`/`requests`) y con
distintos headers simulados, debido a desafíos Cloudflare/WAF de huella TLS/JS.

**Alternativas descartadas.**
1. Marcar el dominio como muerto/bloqueado y descartarlo del catálogo.
2. Forzar renderizado Playwright headless en todas las peticiones de toda la corrida
   (inviable: el consumo de CPU/memoria y la latencia aumentan en órdenes de magnitud).
3. Exigir configuración manual obligatoria portal por portal con `use_playwright: true`
   para cada fuente que presente desafíos WAF sobrevenidos.

**Decisión (Cerrada en B-23).**
Se automatiza el reintento condicional con `HeadlessFetcher` (Playwright con
`wait_until="domcontentloaded"` y User-Agent realista) por defecto en `HttpFetcher`:
1. El cliente HTTP simple ejecuta la petición ordinaria.
2. Si y solo si la respuesta del servidor es HTTP 403 (bloqueo WAF/bot challenge),
   se dispara de forma transparente el reintento automático con navegador headless real.
3. El resultado exitoso se etiqueta y registra formalmente en la auditoría con la
   marca `"resuelto_via_headless"` (en logs, `ResourceMetadata.resolved_via_headless = True`,
   `ResourceEvidence.extraction_methods` y `validate_url_access`), permitiendo total
   auditoría y trazabilidad.
4. La bandera declarativa `use_playwright: true` a nivel de configuración YAML queda
   reservada exclusivamente para portales SPAs dinámicos (donde los enlaces requieren
   ejecución JavaScript desde la primera carga, aunque el servidor responda HTTP 200).

**Razón.** Un 403 contra un fetcher HTTP simple no demuestra que el recurso esté caído
ni que el portal sea inaccesible; la huella TLS y el JS challenge impiden el paso a
librerías estándar pero son transparentes para un navegador real con headless Chromium.
El reintento puramente condicional optimiza rendimiento: no incurre en coste de render
para peticiones 200/404/5xx ordinarias.

**Consecuencia.** Portales que bloquean scrapers por Cloudflare (ej. BCP) recuperan
sus documentos de forma autónoma sin intervención manual ni cambios de configuración.

**Umbral que cambiaría esto.**
1. Si `wait_until="networkidle"` se usa en lugar de `"domcontentloaded"`, el timeout es mucho más probable — un sitio con Cloudflare Challenge en background nunca llega a inactividad total de red. Verificado empíricamente: con `networkidle` el primer intento contra `bcp.gov.py` dio timeout a los 20s; con `domcontentloaded` respondió 200.
2. Si un portal implementa protecciones CAPTCHA interactivas (ej. Cloudflare Turnstile interactivo obligatorio) que impidan la resolución headless no asistida, en cuyo caso se requerirá ruta de contingencia Wayback o descarte fundado.

**Verificado el.** 2026-09-17 (análisis inicial en BCP con medición de `networkidle` vs `domcontentloaded`) y 2026-09-18 (subsanación B-23: corrida real sobre BCP con `use_playwright: false` que recuperó 25 documentos reales (PDF) entre 36 recursos exportados, el mismo rendimiento que con `use_playwright: true` forzado, 75/75 tests passing).

---

## D-04 · Separar "conectividad" (Track A) de "extracción de documentos" (Track B)

**Contexto.** El pipeline tiene dos capas con dueños de riesgo distintos: una
verifica que una URL responde (`validation_engine.py` + `fetcher.py`, rápida,
corre contra las ~63 fuentes), otra extrae documentos reales navegando el
sitio (`orchestrator.py` + `discovery.py` + adaptadores, mucho más pesada,
solo configurada para 2 fuentes al momento de esta decisión).

**Decisión.** El plan de cobertura (`docs/plan_cobertura_100.md`) trata
ambas como metas independientes con checklists propios, no como una sola
cifra de "% completado".

**Razón.** Llegar a 100% de Track A no implica nada sobre Track B —
confirmado el 2026-09-17: 59/63 fuentes en `200` (93.7%), pero solo 2/63
tenían configuración para extraer un documento real. Reportar un solo
número combinado escondería cuál de los dos problemas falta resolver.

**Umbral que reabriría esto.** Cuando el 100% de las fuentes del catálogo estén onboardeadas en Track B y validadas con extracción real; en ese punto Track A queda subsumido operativamente en Track B como precondición de red.

**Verificado el.** 2026-09-17.

---

## D-05 · FINRURAL como fuente piloto de Track B, no BBV

**Contexto.** Ambas fuentes (`BBV`, `FINRURAL`) ya tenían YAML de
configuración para el motor de extracción completo; había que elegir una
para validar el pipeline de punta a punta antes de generalizar a las 61
fuentes restantes.

**Alternativas consideradas.** BBV, por ser la otra fuente con adaptador
propio ya escrito.

**Decisión.** FINRURAL.

**Razón.** No fue una elección a priori — FINRURAL expuso en el primer
intento un bug real en `discovery.py` (ver D-06) que probablemente también
afecta a BBV y a cualquier fuente futura con enlaces `mailto:`/`tel:` en su
sitio. Quedarse en BBV lo habría escondido hasta que apareciera sin aviso en
otra fuente.

**Consecuencia — resultado medido.** Tras corregir el bug, una corrida real
contra FINRURAL descubrió 296 candidatos y procesó 175 exitosamente (0
errores), verificado en `inventory.db` (SQLite), con documentos reales
(`reporte-sostenibilidad-2023-FINRURAL.pdf`, `financiera_01_2026.pdf`) y
fechas extraídas correctamente. Esto cumple el criterio de "obtención de
documento de al menos una fuente" del plan.

**Umbral que reabriría esto.** Ninguno para la etapa de validación del piloto (ya cumplida con 175 documentos y 0 errores). BBV se reincorpora en su propio lote de la etapa C (B-14 a B-22) como fuente con adaptador a medida ya existente.

**Verificado el.** 2026-09-17.

---

## D-06 · Bug corregido: `mailto:`/`tel:` se trataban como páginas crawleables

**Contexto.** `DiscoveryEngine._is_allowed_domain` (`discovery.py:118-121`,
antes del fix) devolvía `True` para cualquier URL sin `netloc` — y
`urlparse("mailto:x@y.bo")` no le asigna `netloc`, así que la condición
`not domain` dejaba pasar el enlace como "dominio permitido". El filtro de
anclas (`discovery.py:323`, antes del fix) solo excluía `#` y `javascript:`,
no `mailto:`/`tel:`.

**Cómo se detectó.** No leyendo el código — corriendo el pipeline real
contra FINRURAL. Con un timeout de 100s, la corrida se quedó completamente
atascada reintentando ~15 enlaces `mailto:`/`tel:` de instituciones
afiliadas (cada uno: 3 reintentos con backoff, ~9-16s, sin ningún resultado),
sin escanear una sola página real del sitio.

**Decisión.** Filtrar explícitamente `mailto:`, `tel:`, `fax:`, `whatsapp:`,
`sms:` en el filtro de anclas, y además endurecer `_is_allowed_domain` para
rechazar cualquier esquema que no sea `http`/`https` — dos capas, no una,
porque un esquema no-HTTP podría llegar por otra vía (semillas, sitemap,
wayback) además de por enlace de ancla.

**Verificación (no solo lectura).** Prueba de regresión en
`tests/test_discovery.py` (5 casos). Se comprobó que falla sin el fix
(`git stash` del cambio, 3 de 5 casos fallan) antes de darla por buena.
Verificación de efecto real: la misma corrida que antes se atascaba en
enlaces de contacto, después del fix escaneó 19 páginas reales y descubrió
296 candidatos en 25 segundos.

**Por qué importa para el resto del plan.** Este bug no se habría notado
nunca leyendo el código o corriendo tests unitarios con mocks — solo
apareció al correr el pipeline contra un sitio real con enlaces de contacto
normales. Cualquier fuente nueva que se agregue en la Fase 2 del plan de
cobertura puede tener el mismo patrón (es HTML de sitio institucional
boliviano típico, no un caso raro de FINRURAL).

**Umbral que reabriría esto.** Si se incorpora soporte intencional para protocolos no-HTTP (por ejemplo, `ftp://` para repositorios estadísticos antiguos de multilaterales), lo cual requeriría un handler de protocolo dedicado y nunca encolarlo en el fetcher HTTP estándar.

**Verificado el.** 2026-09-17.

---

## D-07 · `GenericSourceAdapter` (YAML declarativo) para fuentes nuevas, no adaptadores Python a medida

**Contexto.** El motor de extracción tiene 2 adaptadores Python con lógica
propia (`BbvAdapter`, `FinruralAdapter`) y un fallback declarativo
(`GenericSourceAdapter`) que cubre cualquier `source.id` no reconocido
(`main.py:load_adapter()`), a partir solo de un YAML.

**Decisión.** Las ~61 fuentes restantes se onboardean generando un YAML
(`classification.dataset_rules`, `excluded_path_keywords`, semillas,
extensiones permitidas) sobre la plantilla `config/source_finrural.example.yaml`,
sin escribir código Python nuevo por fuente.

**Razón.** `BbvAdapter`/`FinruralAdapter` existen porque tenían reglas que no
encajaban en el modelo declarativo. Para el resto, escribir un adaptador
Python por institución sería repetir en código lo que el YAML ya resuelve, y
son 61 archivos más que mantener y explicar.

**Umbral que cambiaría esto, por fuente puntual.** Si al generalizar aparece
una fuente con lógica que el modelo declarativo no puede expresar
(paginación no estándar, autenticación, formularios dinámicos), esa fuente
se convierte en su propio adaptador — no se fuerza el modelo genérico a
cubrir un caso que no le corresponde. No es una razón para abandonar la
decisión general, solo para la fuente específica que lo necesite.

**Verificado el.** 2026-09-17, revisando `main.py:31-47`.

---

## D-08 · La suite de pytest se divide entre rápida y `live`, no se corre completa por defecto en el hook

**Contexto.** `pytest tests/` completo tardó **65 minutos** (49 tests, medido
el 2026-09-17, no estimado) para terminar con 0 fallos. Investigando cuál
test causaba la demora: 2 de los 49 (`test_http_fetcher_validate_url_access_caps_connection_error`,
`test_browser_fallback_distinguishes_document_from_landing_page`, en
`tests/test_validation_engine.py`) se cuelgan más de 60 segundos cada uno
pese a mockear `fetcher.session.head`/`.get` — el fallback interno de
`HttpFetcher` ante `ConnectionError` escapa el mock y hace una llamada de
red real. Root cause exacto sin diagnosticar todavía (queda como pendiente
abierto, no se inventa una causa sin verificarla).

**Decisión.** Marcar esos 2 tests con `@pytest.mark.live` (registrado en
`pyproject.toml`). El resto de la suite (52 tests) corre en **8.3 segundos**
con `pytest tests/ -m "not live"`, verificado.

**Razón — la misma lección de otros proyectos del equipo.** Una
verificación automática que tarda 65 minutos no se ejecuta en la práctica —
ni un desarrollador ni un hook la van a correr antes de cada cambio, así que
equivale a no tener verificación. Un hook rápido y confiable que corre
siempre vale más que uno completo que nadie ejecuta.

**Consecuencia.** El hook `PostToolUse` de `.claude/settings.json` usa la
suite filtrada. La suite completa (`pytest tests/`, sin filtro) sigue
existiendo y debe correrse antes de cerrar una fase grande del plan de
cobertura — el filtro es para iteración rápida, no reemplaza la verificación
completa.

**Diagnóstico confirmado (2026-09-18, auditoría de B-07).** Tres causas
independientes, verificadas leyendo `fetcher.py` línea por línea, no
asumidas:

1. **Escape a nivel de módulo.** `_generate_gemini_content` llama
   `requests.post(...)` directo, no `self.session.post(...)`. Los mocks
   sobre `fetcher.session.head`/`.get` nunca lo interceptan.
2. **Activación involuntaria por `.env` ambiental.** `HttpFetcher.__init__`
   carga `GEMINI_API_KEY` de `.env` por defecto si no se pasa
   `gemini_api_key` explícito. En cualquier máquina con una clave real
   configurada —esta incluida, verificado: hay una clave de 39 caracteres
   cargando en este entorno—, un test que simula una caída de conexión cae
   en el fallback real a la API de Google sin que nadie lo pidiera.
3. **El backoff de reintentos es real incluso con el mock.** `fetch_head` y
   `fetch_html` ejecutan `time.sleep(1.5 * attempt)` entre reintentos
   **sin condicionarlo a que el fallo sea real** — un mock que lanza la
   excepción al instante igual duerme. 9s por método fallido (HEAD+GET),
   ×2 URLs en `test_browser_fallback...` = los 18s medidos, exactos.

**Consecuencia — más allá de la suite de tests.** Esto no era solo un
problema de velocidad de tests: cualquier corrida de `pytest tests/`
completa en una máquina con clave real configurada **gastaba cuota real de
la API de Gemini en cada ejecución**, sin que apareciera en ningún log
visible. Es la misma cuota que ya se agotó dos veces en sesiones anteriores
de este proyecto (ver `RESUMEN_SESION.md`) — parte de ese agotamiento pudo
venir de acá, no solo del uso intencional en `resolve_dead_domains.py`.

**Decisión del fix.** Se corrige en el mismo commit que introduce
`_generate_gemini_content` (nunca se había commiteado con el bug, así que no
hace falta un commit de arreglo separado — se escribe bien desde el
principio):

- `_generate_gemini_content` pasa a usar `self.session.post(...)`.
- Los dos tests afectados pasan `gemini_api_key=None` explícito al
  construir `HttpFetcher()`, para que ningún `.env` ambiental los alcance
  —es la guarda real: `_ask_gemini_for_alternatives` corta antes de llamar
  a la red si `self.gemini_api_key` es falsy, sin importar qué esté
  mockeado.
- Ambos tests mockean también `time.sleep` para no pagar los 9-18s de
  backoff real, que es comportamiento intencional del fetcher y no algo que
  deba cambiar para producción.
- Se retira `@pytest.mark.live` de ambos.

**Lo que NO se cambia, y por qué.** El comportamiento por defecto de
`HttpFetcher()` —cargar `.env` automáticamente si no se pasa clave— se
queda igual. Es una decisión de conveniencia para el uso real (CLI,
`resolve_dead_domains.py`) y cambiar el default para acomodar tests sería
una superficie de cambio más grande y más riesgosa que corregir los dos
tests puntuales que necesitaban aislarse del ambiente.

**Umbral que reabriría esto.** Cumplido — ver "Decisión del fix" arriba.
Si en el futuro aparece un tercer test que dependa de que el fallback a
Gemini esté desactivado por defecto, aislarlo de la misma forma
(`gemini_api_key=None` explícito), no cambiar el default de la clase.

**Verificado el.** 2026-09-17 (hallazgo original) · 2026-09-18 (diagnóstico
confirmado y fix decidido, B-07).

---

## Apéndice · Mapa de módulos del motor de extracción (Track B)

Verificado leyendo el código el 2026-09-17, útil para no tener que
redescubrirlo:

| Módulo | Qué hace |
|---|---|
| `orchestrator.py` | Orquesta la corrida completa: discovery → descarga/extracción → export |
| `discovery.py` | BFS/DFS con scoring semántico, sitemaps, wayback, dorking y subdominios como canales opcionales |
| `fetcher.py` | HTTP con reintentos, robots.txt por URL (cacheado por dominio), fallback a Gemini para URLs muertas |
| `headless_fetcher.py` | Playwright opcional para sitios que requieren render (SPA, Cloudflare) |
| `archive_extractor.py` | Extrae ZIP/TAR; cada archivo interno se vuelve su propio `ResourceItem` |
| `contingency_engine.py` | Reintenta/recupera URLs de recursos que fallaron, incluido snapshot de Wayback |
| `wayback_engine.py` | Consulta la API CDX de Wayback Machine para URLs históricas |
| `subdomain_finder.py` | Descubre subdominios vía Certificate Transparency (crt.sh) |
| `search_dorker.py` | Dorking vía Bing/Google Custom Search (opcional, requiere API key) |
| `form_automator.py` | Expande formularios GET (combinaciones de parámetros) para simular consultas |
| `drift_monitor.py` | Detecta anomalías de volumen/estructura entre corridas |
| `canonicalizer.py` | Normaliza URLs y genera `resource_key` estables para deduplicar |
| `reducer.py` | Limpia boilerplate y genera versión compacta para consumo por agentes de IA |
| `async_fetcher.py` | Fetcher HTTP asíncrono opcional (`httpx.AsyncClient`) |
| `control_db.py` | SQLite de auditoría (`inventory.db`) — fuente de verdad para verificar resultados sin fiarse solo del log |

Adaptadores (`src/crawler/sources/`): `BaseSourceAdapter` (ABC) con
`is_url_excluded()`/`classify_dataset()` abstractos; `GenericSourceAdapter`
los implementa desde YAML (ver D-07).

---

## D-09 · El catálogo curado se versiona; el resto de `output/` no

**Contexto.** `.gitignore` excluía `output/` entero, por buenas razones: ahí
caen los artefactos de cada corrida del crawler (jobs, caches, HTML
descargado, `inventory.db`). Pero dentro de esa carpeta viven también dos
archivos que **no son artefactos sino el entregable**:

- `output/excel_urls_diagnostic.json` (90 KB) — el catálogo maestro de las
  62 fuentes, con su estado, mapeos y evidencia. Es literalmente el dato
  detrás de la cifra de cobertura.
- `output/url_resolution_log.json` (44 KB) — la auditoría completa de cada
  intento de resolución de URL, incluida la respuesta cruda de la IA.

**Descubierto el 2026-09-18**, ordenando el árbol tras la verificación en
vivo: todo el trabajo de Track A existía únicamente en el disco de una
máquina. Si ese disco falla, se pierde el catálogo y su trazabilidad, y no
queda forma de reconstruir por qué cada URL quedó como quedó.

**Decisión.** Cambiar la regla de `output/` a `output/*` y re-incluir esos
dos archivos por excepción explícita.

**Detalle que importa, porque falló en el primer intento.** Escribir
`!output/archivo.json` debajo de una regla `output/` **no hace nada**: git no
puede re-incluir un archivo si su directorio padre está excluido. La regla se
ve correcta, no da ningún error, y el archivo sigue ignorado. Hay que
excluir el *contenido* (`output/*`) para que la negación tenga efecto.
Verificado con `git check-ignore` antes y después — otro caso de la familia
"parece correcto y no hace nada" que ya documenta `CLAUDE.md`.

**Consecuencia.** El catálogo pasa a tener historial: se puede ver cuándo una
fuente cambió de estado y por qué. Costo: ~135 KB versionados y un diff por
cada corrida que actualice el dataset.

**Umbral que reabriría esto.** Si el dataset crece a un tamaño donde el diff
por corrida sea impracticable (orden de megabytes), o si se migra a una base
de datos real — en cuyo caso el versionado pasa a ser responsabilidad de esa
base y estos archivos vuelven a ser exportaciones desechables.

**Verificado el.** 2026-09-18, con `git check-ignore` sobre los tres casos
(los dos incluidos y uno del resto de `output/`, que sigue ignorado).

---

## D-10 · CEPAL: exclusión técnica justificada de Track A por arquitectura DSpace

- **Origen:** Decisión adoptada en auditoría B-17 (`docs/auditorias/B-17.md:392-410`) y formalizada en B-20.
- **Contexto.** CEPAL (Comisión Económica para América Latina y el Caribe) almacena y distribuye sus publicaciones y documentos oficiales a través de su Repositorio Digital institucional (`repositoriodigital.cepal.org`), implementado sobre la plataforma DSpace. En este repositorio, los documentos no se enlazan como archivos estáticos directos (`.pdf`) en el HTML indexable, sino mediante identificadores handle y bitstreams REST (`/bitstreams/.../content` o llamadas dinámicas OAI-PMH).
- **Alternativas consideradas.**
  1. *Forzar rastreo con GenericSourceAdapter (BFS HTML):* Descartado porque el rastreo superficial recorre metadatos y páginas de visor sin descargar el documento real ni resolver la estructura REST del bitstream.
  2. *Implementar un conector ad-hoc para DSpace en Track A:* Descartado para la Etapa C para mantener la homogeneidad declarativa YAML y el criterio de costo/complejidad de la fase de prospección externa estándar.
- **Decisión.** CEPAL se clasifica formalmente como **exclusión técnica justificada** para el prospector declarativo HTML de Track A. Se mantiene en el catálogo `output/excel_urls_diagnostic.json` con `crawler_source: null` y nota explicativa, completándose la meta de 25 portales externos de la Etapa C con el Instituto Boliviano del Cemento y Hormigón (IBCH).
- **Razón.** Una tubería de prospección HTML no debe deformarse para resolver casos de APIs documentales complejas cuando existen suficientes fuentes institucionales nacionales vivas con documentos directamente accesibles.
- **Consecuencia.** CEPAL queda documentada como candidata prioritaria para un conector de API REST / OAI-PMH en la etapa de conectores especializados (Fase 4). No contabiliza en el subtotal de portales HTML de la Etapa C.
- **Umbral que reabriría esto.** Si la CEPAL rediseña su portal principal para exponer enlaces directos descargables en páginas HTML estáticas, o cuando se abra formalmente la Fase 4 de adaptadores REST especializados.
- **Verificado el.** 2026-09-18, contra `https://www.cepal.org/es/publicaciones` y `repositoriodigital.cepal.org`.

---

## D-11 · Recuperación de series históricas: gateway directo Wayback y plantillas determinísticas ante degradación de APIs

- **Origen:** Auditoría y corrección B-32 (`docs/auditorias/B-32.md:210-228`).
- **Contexto.** Internet Archive CDX API y la API de disponibilidad (`archive.org/wayback/available`) presentan saturación frecuente y respuestas HTTP 429 ("Too Many Requests"). Si un crawler depende exclusivamente de la API `/available` para descubrir snapshots de recursos caídos, un 429 anula la contingencia para todos los recursos subsiguientes. Por otro lado, enumerar miles de URLs mensuales a mano en YAML no escala a las 61 fuentes de prospector.
- **Alternativas consideradas.**
  1. *Depender exclusivamente de la API /available de archive.org:* Descartado porque 429 silencia la contingencia y bloquea la recuperación.
  2. *Descarga manual fuera del crawler:* Descartado porque viola la reproducibilidad y trazabilidad en `resource_audit_log`.
  3. *Sondeo ciego sin plantilla temporal:* Descartado (D-02 aplicada a documentos).
- **Decisión.**
  1. **Fallback de Gateway Directo en `ContingencyEngine`:** Cuando la API de disponibilidad devuelve 429 o falla, el motor conmuta automáticamente al gateway canónico de snapshots `https://web.archive.org/web/{timestamp}id_/{target_url}`. Se prueban variantes de esquema (`http` y `https`) y de prefijo de subdominio (`www`), utilizando el año del documento (si está presente en la URL) para anclar el snapshot al período en que el recurso estaba vivo.
  2. **Estrategia para series documentales históricas:** Cuando un portal institucional organiza sus publicaciones en rutas determinísticas (ej. `{año}/financiera_{mes}_{año}.pdf`), la enumeración se formula mediante generadores paramétricos de URL (formalizados en B-33 para ASFI-IFD y aplicables a otras fuentes), manteniendo en el YAML las semillas maestras de bootstrapping.
  3. **Disciplina estricta de documentos vs sidecars:** Ningún recurso con extensión no incluida en `allowed_extensions` (como sidecars de checksum `.sha` de 89 bytes) puede ser clasificado como documento descargable. `_is_download_link` debe verificar y rechazar extensiones estáticas no permitidas antes de aplicar heurísticas de tokens de ruta.
- **Razón.** Garantiza que la tubería de prospección sea resiliente a fallas transitorias de infraestructura de terceros (archive.org) y que las métricas de cobertura midan documentos reales descargables (`.pdf`, `.xlsx`, etc.) y no artefactos auxiliares.
- **Consecuencia.** Se recuperan exitosamente boletines y documentos históricos eliminados del sitio vivo (ej. serie `fr-bem` de FINRURAL) conservando la procedencia `wayback_snapshot` en la base de auditoría.
- **Umbral que reabriría esto.** Si Internet Archive bloquea a nivel de IP el gateway directo web de snapshots, o si los portales implementan ofuscación no determinística de nombres de archivo que impida inferir rutas pasadas.
- **Verificado el.** 2026-09-19 (bloque B-32, recuperación verificada de 18 boletines `fr-bem` con bytes reales).

---

## D-12 · Las APIs se consumen por configuración declarativa; `api_detector.py` no se conecta al pipeline de extracción

- **Origen:** Parada obligatoria de B-33 (`docs/plan_bloques_fase2.md:170-175`). Diagnóstico en `docs/diagnostico_b33_api_formularios.md`, decisión y pautas en `docs/decision_b33_api_formularios.md`.

**Contexto.** `api_detector.py` (583 líneas) y `form_automator.py` (49 líneas)
están implementados y no los llama nadie. B-33 proponía conectarlos al motor de
extracción para desbloquear SICSANTACRUZ (API Strapi), SICOES e INE
(formularios). El diagnóstico previo estableció dos hechos que cambian el
planteo: `api_detector` es un catalogador diagnóstico que no produce
`DownloadCandidate`, y `FormAutomator` no maneja POST ni `__VIEWSTATE`, que es
justamente lo que usan SICOES e INE.

**Alternativas descartadas.**

1. *Conectar `probe_domain_for_apis` al pipeline para autodescubrir endpoints.*
   Descartado: son ~25 sondeos ciegos por dominio, que en la mayoría de los
   portales devuelven 404. Es D-02 —sondeo especulativo sin señal previa—
   trasladado de URLs a APIs. Además no ahorra trabajo: la capa de traducción
   JSON → candidato hay que escribirla igual.
2. *Implementar API y formularios en un solo bloque y un solo commit.*
   Descartado: el criterio de aceptación de B-33 solo mide la mitad API, con lo
   cual la mitad de formularios entraría al motor sin evidencia. Y los riesgos
   son de distinta naturaleza — el camino API es aditivo y aislado, mientras
   que la expansión de formularios escribe dentro del bucle BFS con producto
   cartesiano, que es la forma exacta del bug D-06.
3. *Configurar la ruta del documento dentro del JSON con JSONPath o un
   mini-lenguaje de rutas.* Descartado: la ruta de Strapi
   (`attributes.documento.data.attributes.url`) es específica de una fuente y
   de una versión. Un barrido recursivo del payload que recoge strings
   resolubles a `allowed_extensions` cubre Strapi, CKAN y OData con menos
   código y sin configuración por fuente.

**Decisión.**

1. Los endpoints de API se **declaran verificados en el YAML de la fuente**
   (`crawl.api_endpoints`), no se autodescubren en tiempo de corrida. La
   ausencia de la sección equivale a comportamiento idéntico al actual.
2. La traducción JSON → `DiscoveredCandidate` vive en un módulo nuevo
   (`api_consumer.py`) enganchado en un solo punto de `DiscoveryEngine`, con el
   mismo patrón que wayback y search dorking. Procedencia `url_origin="api"`.
3. `api_detector.py` conserva su rol actual —generar `output/reporte_apis.md`—
   y no participa de la extracción. Lo único que se reutiliza de él es
   `RobotsGate`.
4. B-33 se parte en **B-33a** (API + SICSANTACRUZ, aprobado) y **B-33b**
   (formularios GET, condicionado a encontrar antes un caso GET real en el
   catálogo). SICOES e INE dejan de ser casos objetivo de B-33b.

**Razón.** Un endpoint verificado es un dato, y los datos verificados se
escriben, no se re-descubren en cada corrida. Separar los dos mecanismos
permite además que cada uno cierre con evidencia propia, que es la única forma
de que la auditoría pueda decir algo sobre ellos.

**Consecuencia.** El motor gana un canal de descubrimiento por API utilizable
por cualquier fuente futura con endpoint JSON conocido —incluida CEPAL, que
D-10 dejó pendiente de un conector REST/OAI-PMH— sin agregar sondeo
especulativo. Los formularios POST con estado (SICOES, INE) quedan
explícitamente diferidos a la fase de conectores especializados.

**Umbral que reabriría esto.** Si aparecen tres o más fuentes con API cuyo
endpoint no se pueda determinar por inspección manual, el autodescubrimiento
pasa a tener caso y se evalúa como bloque propio. Si el barrido recursivo
sobre-recoge en alguna fuente, se agrega un `items_path` opcional sin cambiar
el resto de la decisión.

**Verificado el.** 2026-09-19, contra `src/crawler/core/api_detector.py`,
`src/crawler/core/form_automator.py`, `src/crawler/core/discovery.py:320-414`
y la entrada SICSANTACRUZ de `output/excel_urls_diagnostic.json`.

---

## D-13 · `content_hashing: enabled: true` como default obligatorio para toda fuente nueva en el prospector

**Contexto.** En la arquitectura del prospector, `orchestrator.py:313-317` cortaba la ejecución devolviendo `ResourceStatus.PROCESSED` sin transferir bytes ni calcular el hash cuando `content_hashing.enabled` era `false`. En ese modo, `inventory.db` acumulaba filas catalogadas con `file_size_bytes` y `content_sha256` en `NULL`. La plantilla `config/source_finrural.example.yaml` y los primeros lotes de fuentes nuevas salieron con `enabled: false`, provocando que miles de URLs se reportaran como documentos reales sin haber transferido ni un solo byte de la red (reprobado en B-33a y en la auditoría agrupada B-34/B-35).

**Opciones consideradas.**
1. *Mantener content_hashing opt-in (default false).* Descartado: provocó la devolución sucesiva de B-33a y B-34, e indujo a reportar métricas infladas de cobertura basadas en URLs catalogadas en lugar de documentos efectivamente descargados y verificados.
2. *Eliminar el flag y forzar descarga incondicional siempre.* Descartado: fuentes excepcionales con archivos masivos de gigabytes o bloqueos puntuales podrían requerir modo liviano de catálogo de forma justificada.
3. *Default `enabled: true` para toda fuente nueva, con apagado explícito y justificado por fuente.* Opción adoptada: garantiza que cada fila en `inventory.db` represente contenido digital real con tamaño y hash criptográfico verificable.

**Decisión.**
1. **`content_hashing.enabled: true` es el valor por defecto y obligatorio** para todas las fuentes nuevas que se configuren en el prospector.
2. En toda corrida de onboarding y auditoría, el criterio de aceptación se mide estrictamente sobre **filas con `file_size_bytes > 0` y `content_sha256` no nulo** (`SELECT count(*) WHERE file_size_bytes > 0`).
3. La plantilla base `config/source_finrural.example.yaml` y todas las fuentes activas se actualizan con `content_hashing: enabled: true`.
4. El apagado de `content_hashing` (`enabled: false`) solo es permisible como excepción justificada por escrito (ej. repositorios de archivos masivos donde el almacenamiento o ancho de banda esté restringido), documentado en la bitácora y en el YAML respectivo.

**Razón.** El valor del inventario reside en los documentos reales transferibles y analizables, no en meras listas de URLs. Medir filas sin bytes es el mismo error conceptual que D-01 (aceptar URLs por status 200 sin verificar contenido).

**Verificado el.** 2026-09-20, acordado entre Antigravity y Claude CLI y aprobado por Marlon.

---

## D-14 · Criterio de qué cuenta como documento: contenido digital real (extensión o MIME documental), no heurística de URL

**Contexto.** En la auditoría agrupada de B-36 + B-37 + B-38 (`docs/auditorias/B-36_B-37_B-38.md`), se identificó el hallazgo H-1: 16 de los 907 "documentos descargados con bytes reales y SHA-256" correspondían en realidad a **páginas HTML de navegación** (`text/html`, cuerpo `<!DOCTYPE html>`). Una fuente completa (NIH / NIDA) aportaba 5 filas que eran exclusivamente artículos y notas de prensa web sin extensión de documento, capturadas porque `_is_download_link()` en `src/crawler/core/discovery.py:204-246` clasificaba como documento cualquier URL cuyo path contuviera subcadenas como `/reporte`, coincidiendo accidentalmente con el participio en inglés `"reported"` (`reported-use-...`). De igual modo, en portales en español capturó páginas índice (`boletin-diario-page/`) duplicándolas junto a los PDFs enlazados.

**Opciones consideradas.**
1. *Contar cualquier recurso transferido con status 200 y bytes > 0.* Descartado: infla artificialmente el conteo incorporando páginas HTML de navegación o artículos web que no constituyen archivos documentales binarios.
2. *Modificar inmediatamente la heurística de `_is_download_link()` en el motor.* Descartado para la entrega de los lotes: modificar el core del motor alteraría de forma retrospectiva los conteos de todas las fuentes ya cerradas en fases previas sin un bloque de calibración y regresión dedicado.
3. *Adopción de D-14 en la capa de auditoría y métricas, con reclasificación estricta de documentos y tarea técnica diferida para el motor.* Opción adoptada: los conteos de cobertura y documentos reales se miden únicamente sobre recursos con extensión o MIME documental verificable (`.pdf`, `.xlsx`, `.xls`, `.csv`, `.zip`). El ajuste del motor se programa como bloque técnico propio.

**Decisión.**
1. **Qué cuenta como documento:** Una fila en `inventory.db` cuenta formalmente como documento si y solo si su contenido corresponde a un formato documental o binario permitido (`.pdf`, `.xlsx`, `.xls`, `.csv`, `.zip`, `.ods`, `.xlsm`, `.doc`, `.docx` o `Content-Type` documental equivalente).
2. Las páginas HTML sin extensión capturadas por heurística de subcadenas de path se clasifican como **páginas de navegación / índice**, y **no se computan** en las cifras de documentos reales descargados.
3. Los tokens de path y texto de `discovery.py` se definen formalmente como mecanismos para **priorizar rastreo**, nunca como determinantes taxonómicos de documento final.
4. Las fuentes que solo aporten páginas HTML sin archivos documentales descargables (como NIH) cierran válidamente como **portales sin documentos detectados**, documentando fehacientemente la causa técnica.
5. El refactor de `_is_download_link()` en el motor se ejecutará en un bloque técnico posterior para salvaguardar la estabilidad de las suites de prueba de la Fase 2.

**Enmienda a D-14 (Bloque B-46 / Fase 3 — 2026-09-21):**
- **Inclusión de formatos abiertos y estructurados:** Se autorizan formalmente las extensiones `.ods` (OpenDocument Spreadsheet - estándar ISO/IEC 26300) y `.xlsm` (hojas de cálculo Excel habilitadas para macros).
- **Justificación empírica:** El Banco Central de Bolivia (BCB) y la Autoridad de Supervisión del Sistema Financiero (ASFI) publican decenas de series estadísticas históricas y boletines monetarios en formato `.ods`. Su exclusión previa privaba al catálogo de 78 documentos oficiales en BCB y 90 en ASFI, capturados legítimamente por el benchmark de Rolando.
- **Alcance normativo:** `.ods` y `.xlsm` se homologan al mismo nivel taxonómico que `.xlsx` y `.csv` en todas las herramientas de medición, motores de descubrimiento (`allowed_extensions`) y scripts de auditoría.

**Razón.** Una métrica de inventario documental no puede mezclar páginas web con archivos descargables, pero debe reconocer rigurosamente todos los estándares internacionales de hojas de cálculo abiertas y formatos financieros institucionales.

**Verificado el.** 2026-09-21, acordado en acta de auditoría B-36..B-38 y enmendado en B-46 con aprobación de Marlon y Claude.

---

## D-15 · Definición del entregable de Fase 2: Catálogo Verificado de Recursos con Hash vs Corpus de Archivos en Disco

**Contexto.** En la auditoría de cierre de la Fase 2 (B-40), se evidenció que la arquitectura del prospector descarga bytes a memoria (`orchestrator.py:313-333`) para calcular el hash criptográfico SHA-256 e ingresarlo en `inventory.db` (`resource_audit_log`), pero no persiste los archivos `.pdf`, `.xlsx` o `.zip` en el sistema de archivos local. D-13 definió el criterio de aceptación sobre columnas de la base de datos (`file_size_bytes > 0 AND content_sha256 IS NOT NULL`), no sobre archivos en disco. El benchmark histórico de Rolando y Douglas tampoco guardaba los archivos; listaba y catalogaba URLs de recursos. Esto generó una ambigüedad terminológica al usar la frase "descarga física de documentos".

**Opciones consideradas.**
1. *Detener el cierre de Fase 2 e implementar persistencia masiva en disco antes de cerrar.* Descartado: cambiaría retroactivamente el alcance de la Fase 2, exigiría re-descargar decenas de gigabytes contra servidores públicos de Bolivia y desalinearía la comparativa con Rolando.
2. *Formalizar el entregable de la Fase 2 como Catálogo Verificado de Recursos Documentales (Opción A).* Opción adoptada: reconoce la naturaleza del prospector, valida la victoria homóloga contra el benchmark de Rolando (5.411 vs 5.403 en los 22 portales comunes bajo D-14) y transparenta las métricas de integridad sin ambigüedad.

**Decisión.**
1. **Entregable de la Fase 2:** Es formalmente un **Catálogo Estructurado y Verificado de Recursos Documentales** contenido en las bases SQLite `inventory.db`.
2. **Uso riguroso del vocabulario:** Se prohíbe el uso de la expresión "descarga física en disco" para referirse a filas de `inventory.db`. Las columnas `file_size_bytes` y `content_sha256` representan metadatos de verificación obtenidos en memoria o transferidos por red.
3. **Validez del Benchmark:** La comparación contra Rolando y Douglas se mantiene legítima y válida bajo la Decisión **D-14** (5.411 vs 5.403 en los 22 portales comunes, y 10.985 globales), pues todos los participantes se miden bajo el mismo estándar de catalogación de URLs documentales.
4. **Fase 3 (Data Lake / Almacenamiento Masivo):** La descarga y almacenamiento persistente de los archivos binarios al sistema de archivos local (o almacenamiento en la nube S3/GCS) se define explícitamente como el alcance de la Fase 3 del proyecto.

**Razón.** Transparencia metodológica absoluta: el software debe llamarse por lo que hace y medirse contra sus competidores bajo las mismas reglas.

**Verificado el.** 2026-09-21, aprobado por Marlon en el escalamiento de B-40.

---

## D-16 · Doble métrica en comparador: Volumen Bruto Homólogo vs Documentos Únicos Deduplicados

**Contexto.** En portales como FINRURAL, el benchmark de Rolando reportaba 583 URLs, de las cuales 218 correspondían a archivos `.pdf` canónicos, 218 a archivos `.zip` redundantes y 126 a URLs con parámetros de tracking y caché (`?x16877=`). El prospector institucional de DataX deduplica estrictamente estos parámetros mediante `canonicalizer.py`, reportando 241 documentos únicos. Al comparar por conteo bruto de URLs, el sistema era penalizado artificialmente por su rigor taxonómico.

**Decisión.**
1. El comparador de benchmark y los reportes de Fase 3 reportarán una **métrica dual transparente**:
   - **Volumen Bruto Homólogo (Estándar Histórico):** Mide el total de URLs y variantes documentales catalogadas por el prospector frente al baseline de los competidores.
   - **Documentos Únicos Canónicos (Estándar DataX):** Mide la cantidad de documentos distintos y deduplicados tras normalización rigurosa de parámetros y contenedores redundantes.
2. Ninguna optimización de motor deberá inflar los conteos agregando parámetros espurios de URL (`?utm_*`, `?x16877=`) solo para ganar por volumen bruto en el benchmark.

**Razón.** Rigor metodológico: un sistema de grado de producción debe ser auditable por la veracidad de su contenido único sin desfavorecer su posición en benchmarks comparativos históricos.

**Verificado el.** 2026-09-21, aprobado por Claude y Marlon en el diagnóstico forense de Fase 3.

---

## D-17 · Extrapolación Controlada de Series Temporales Observadas vs Sondeo Especulativo (D-02)

**Contexto.** Portales institucionales clave como ASFI (`/pb/instituciones-financieras-desarrollo`) renderizan sus catálogos documentales dinámicamente en el cliente mediante scripts JavaScript (`ifd-bol.js`), construyendo rutas deterministas sobre la plantilla `/sites/default/files/estadisticaif/int_fin_des/{YYYY}/{MM}/{YYYYMM}_{Serie}.zip`. Estas URLs no existen en el HTML inicial descargado por un parser estático. La Decisión D-02 prohíbe el sondeo especulativo ciego (probar variantes aleatorias o no fundamentadas de URLs fallidas). Se requería formalizar la distinción técnica entre el sondeo prohibido y la extrapolación legítima de series temporales sistemáticas observadas.

**Decisión.**
1. **Diferenciación conceptual estricta:**
   - **Sondeo Especulativo (Prohibido bajo D-02):** Probar variaciones heurísticas, aleatorias o ciegas sobre URLs que respondieron error, sin fundamento en la estructura del portal.
   - **Extrapolación Controlada de Serie Observada (Autorizada bajo D-17):** Cuando la existencia de una serie estructurada esté demostrada fehacientemente (por presencia de scripts oficiales del portal como `ifd-bol.js`, o por detección de ≥3 URLs canónicas activas que compartan una plantilla idéntica parametrizada por fecha `{YYYY}/{MM}` y serie `{Serie}`), se autoriza la generación de candidatos sobre la serie temporal.
2. **Obligatoriedad de Validación HEAD/GET previa a la admisión:**
   - Ninguna URL extrapolada bajo D-17 ingresará a la base de control (`inventory.db`) ni al mapa de la fuente sin una petición HTTP `HEAD` (o fallback `GET` en caso de status 405) previa y exitosa.
   - Requisitos indispensables para admisión en el catálogo:
     * Código de respuesta HTTP 200 (o 206).
     * `Content-Length > 0` (o bytes reales transferidos mayores a cero).
     * `Content-Type` o extensión correspondiente a formatos documentales autorizados bajo D-14.
   - Toda combinación extrapolada que devuelva HTTP 404, 403 u otro error es inmediatamente descartada en memoria sin persistir registros ni considerarse anomalía.
3. **Corte y Aborto Histórico:**
   - Las rutinas de extrapolación temporal hacia el pasado deben incorporar una ventana de corte por inactividad (por defecto: 24 períodos mensuales vacíos consecutivos) para detener el sondeo cuando la serie estadística aún no había sido creada por la institución.
4. **Respeto a Rate Limiting y Concurrencia:**
   - La validación de candidatos extrapolados debe acatar estrictamente el `rate_limit_per_second` de la fuente para no degradar el servicio de los servidores públicos.

**Razón.** Esta distinción permite superar los bloqueos de renderizado en cliente de la banca y el Estado boliviano con pleno respaldo empírico de red, cerrando la mayor brecha técnica frente a Rolando (+1.606 archivos ZIP en ASFI) sin violar la ética de scraping ni ingresar datos fantasma al catálogo.

**Verificado el.** 2026-09-21, acordado en el plan de Fase 3 diseñado por Claude Opus 5 y aprobado por Marlon.

---

## D-18 · Herencia de series entre instituciones: evidencia descargada y aprobación humana, nunca cambio automático de dominio

**Contexto.** La reforma del Estado boliviano extingue y fusiona entidades, y
sus series estadísticas migran a la sucesora: SPVS se dividió entre ASFI
(valores) y APS (pensiones y seguros), SUPTRANS pasó a ATT, SBEF pasó a ASFI. El
catálogo ya registra las tres como procedencia histórica. La Fase 4 necesita que
el motor reconozca esa migración para no declarar perdida una serie que sigue
publicándose bajo otro nombre. Pero «buscar qué entidad se hizo cargo de esta
serie» es la forma general del error que D-01 existe para prevenir: el proyecto
aceptó cuatro veces una institución equivocada que respondía 200 (CADEX por
CADEXCO, IBCE por IBCH, `bcp.org` por BCP, y `sicsantacruz.com`, que era un
dominio de parking avalado por una investigación externa). Automatizar la
herencia sin restricción es repetir ese error a escala y con apariencia de
fundamento jurídico.

**Alternativas descartadas.**
1. *Cambio automático de dominio cuando la serie deja de responder y un candidato
   plausible responde 200.* Descartada: es D-01 exactamente, agravada porque el
   fallo no dejaría rastro visible —la serie seguiría creciendo, con documentos
   de otra institución.
2. *Aceptar la herencia por correlación léxica o por similitud de nombre
   institucional.* Descartada: «CADEX» y «CADEXCO» son léxicamente casi idénticas
   y son entidades distintas.
3. *Aceptar como evidencia la cita legal que devuelva el agente.* Descartada por
   la razón de fondo de esta decisión: una cita inventada es indistinguible de
   una cierta al leerla, y nadie la abre para comprobarla. La evidencia se
   descarga o no existe.
4. *Bloquear del todo la herencia y archivar como `HISTORICO` toda serie cuyo
   dominio muera.* Descartada: perdería series vivas y contradice el criterio de
   B-56, donde archivar sin haber buscado bien es una fuente perdida, no una
   fuente histórica.

**Decisión.**
1. **Ninguna herencia se admite de forma automática.** El motor nunca escribe un
   cambio de entidad o de dominio institucional en `inventory.db`, en
   `config/source_<portal>.yaml`, en `config/moved_urls.json` ni en
   `output/excel_urls_diagnostic.json`. Propone; no admite.
2. **Artefacto de propuesta.** Toda herencia se emite como registro en
   `docs/entregas/propuestas_herencia.json`, con: `origen_entidad`,
   `origen_portal`, `origen_dataset`, `ultimo_periodo_origen`, `destino_entidad`,
   `destino_url`, las tres evidencias, `origen_agente` (si el candidato lo
   sugirió un modelo), `status` y `evaluado_en`.
3. **Compuertas de evidencia.** Son cuatro y se evalúan copulativamente:
   - *Continuidad temporal (falsador).* Rechaza si origen y destino publican
     datos contradictorios para el mismo corte, o si el destino no cubre el
     período buscado. Se evalúa solo sobre documentos con período de confianza
     `medium` o superior; si no hay período confiable, queda `INDETERMINADO` y no
     habilita por sí sola la aceptación.
   - *Respaldo legal o mención explícita del predecesor (necesaria).* El cuerpo
     descargado del destino debe contener la norma de transferencia de
     atribuciones o la mención de la entidad extinta. Sin esta evidencia no hay
     propuesta admisible: la correlación léxica es presunción insuficiente.
   - *Identidad estructural.* Comparación de campos entre recursos documentales
     bajo D-14, nunca entre páginas HTML. La coincidencia de periodicidad no
     cuenta como evidencia.
   - *Identidad del destino bajo D-01.* El destino debe acreditar ser la entidad
     sucesora con sus propias palabras clave, además de mencionar al predecesor.
4. **Procedencia obligatoria de la evidencia.** Un modelo puede proponer el
   candidato; no puede ser la fuente de ninguna evidencia. Cada evidencia lleva
   `evidence_url`, `http_status`, `content_sha256`, `fetched_at`, `snippet`
   literal y `matched_pattern`. Evidencia sin esos campos se cuenta como ausente.
5. **Estados y cierre humano.** `PROPUESTA`, `EVIDENCIA_INCOMPLETA`, `ACEPTADA`,
   `RECHAZADA`. Solo una persona pasa una propuesta a `ACEPTADA`, y lo hace
   editando la configuración YAML de la fuente receptora (D-07). Las rechazadas
   se conservan con su motivo para no volver a proponerlas ni a gastar cuota en
   ellas (D-08).
6. **Enlace con el ciclo de vida.** Una herencia `ACEPTADA` es lo único que lleva
   un dataset al estado `MIGRADO` de B-56. El silencio de una fuente nunca lo
   hace.

**Razón.** La herencia es el punto del sistema donde una equivocación se ve más
creíble: viene con nombre de institución pública y número de decreto. Exigir que
cada pieza de evidencia venga de bytes descargados y verificables convierte el
juicio institucional —que no sabemos automatizar— en una verificación mecánica
—que sí—, y deja la decisión que no se puede mecanizar en manos de una persona.

**Consecuencia.** El evaluador de herencia es un productor de propuestas
auditables, no un componente del pipeline de admisión. Cuesta una revisión humana
por herencia, y ese costo es deliberado: en 63 fuentes, las herencias son unidades
por año, no por corrida.

**Umbral que la reabriría.** Solo la automatización del paso 5 (aprobación),
y únicamente si se acumulan ≥ 20 propuestas evaluadas por persona con 0 falsos
positivos y todas sus evidencias reproducibles. Los puntos 1, 3 y 4 no se
reabren: son D-01 aplicada a entidades.

**Verificado el.** 2026-09-24, parada de diseño de B-55 sobre el diagnóstico de
Antigravity, decidido por Claude Opus 5 para aprobación de Marlon.

