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

## D-03 · Sitios protegidos por Cloudflare/WAF: reintentar con navegador antes de dar por muerto

**Contexto.** BCP (Banco Central del Paraguay) devolvía 403 en las 3 URLs de
documentos y en la portada, con `curl`/`requests` y con distintos headers de
navegador simulados.

**Alternativas consideradas.** Marcar el dominio como muerto/bloqueado y
descartarlo del catálogo.

**Decisión.** Antes de marcar un dominio como inaccesible por 403, probarlo
con `HeadlessFetcher` (Playwright, `wait_until="domcontentloaded"`, no
`"networkidle"` — ver nota de umbral abajo). BCP respondió 200 con navegador
real y sin ningún ajuste adicional.

**Razón.** Un 403 contra un fetcher HTTP simple no prueba que el sitio esté
caído — Cloudflare y WAFs similares distinguen tráfico de navegador real de
tráfico de librería HTTP por huella TLS/JS challenge, no por el dominio en
sí.

**Consecuencia.** FMI (Fase 0 del plan de cobertura) es candidato a tener el
mismo patrón — pendiente de probar. El motor de discovery ya tiene
`HeadlessFetcher` disponible; falta decidir (Fase 3 del plan) si el reintento
con headless ante un 403 se automatiza por defecto o se activa caso por
caso.

**Umbral que cambiaría esto.** Si `wait_until="networkidle"` se usa en lugar
de `"domcontentloaded"`, el timeout es mucho más probable — un sitio con
Cloudflare Challenge en background nunca llega a inactividad total de red.
Verificado empíricamente: con `networkidle` el primer intento contra
`bcp.gov.py` dio timeout a los 20s; con `domcontentloaded` respondió 200.

**Verificado el.** 2026-09-17, contra `https://www.bcp.gov.py/`.

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

**Pendiente de verificar.** Por qué el mock de `fetcher.session` no
intercepta la llamada real en esos 2 casos — probablemente el fallback usa
`requests.get`/`requests.post` a nivel de módulo en vez de `self.session`,
o pasa por `_probe_gemini_alternatives`/similar sin pasar por el objeto
mockeado. No se investigó a fondo en esta sesión porque no era el objetivo;
queda anotado para no repetir el hallazgo de cero.

**Umbral que reabriría esto.** Diagnosticar y corregir el escape del mock en `HttpFetcher` para que la suite completa pueda correr 100% desconectada y en <15s sin requerir deseleccionar tests `live` en el ciclo de desarrollo rápido.

**Verificado el.** 2026-09-17.

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
