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

