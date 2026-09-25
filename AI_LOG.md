# Registro de uso de IA — Prospector DataX

Bitácora de cada intervención relevante de herramientas de IA en este
proyecto. Se escribe **mientras ocurre**, no al final: un ejemplo concreto de
algo que hubo que corregir no se reconstruye de memoria tres días después.

**Qué se registra:** una afirmación que no se sostuvo al verificarla, una
decisión tomada en contra de lo que sugirió la herramienta, una búsqueda
propia que cambió el rumbo, una sugerencia descartada con su razón, o un dato
confirmado contra la fuente oficial —aunque saliera correcto.

**Qué no se registra:** cada prompt escrito, erratas triviales, o cosas
aceptadas sin pensar. Cuarenta entradas irrelevantes esconden las cinco que
importan.

---

## Plantilla

```
## E-NN · [título: qué se discutió, en una frase]
- **Fecha / bloque:**
- **Tipo:** corrección · descarte · verificación · divergencia · criterio propio
- **Herramienta:**
- **Qué propuso la IA:**
- **Qué encontré o decidí yo:**
- **Cómo se resolvió:**
- **Por qué:**            ← el campo que importa. El razonamiento, no el hecho.
- **Fuente:**
- **Quién tenía razón:**  yo · la IA · ambos en parte · pendiente
```

---

## Paradas planificadas

Momentos del plan de bloques (`docs/plan_bloques.md`) donde ya se sabe que va
a haber algo que anotar. Si algo surge fuera de estas paradas se registra
igual.

| Entrada | Bloque | Qué se espera registrar |
|---|---|---|
| E-05 | B-07 · Cambios pendientes del fetcher | Qué reveló el diff de 341 líneas sin revisar, y si contiene la causa del escape del mock de D-08 |
| E-06 | B-08 · Brecha de 13 fuentes | Cuántas de la diferencia resultaron ser entradas internas nunca operativizadas frente a fuentes reales por cargar |
| E-07 | B-12 · Generador de YAML | Si el generador intentó inventar reglas de clasificación plausibles y hubo que frenarlo |
| E-08 | B-14→B-22 · Lotes | La primera fuente que no encaje en el modelo declarativo, y por qué se decidió no forzarla (D-07) |
| E-09 | B-23 · Headless ante 403 | Cuántas fuentes reales dieron 403 frente a las que se suponían — la decisión de D-03 se cierra con ese dato |

---

## Entradas

## E-01 · Tres sugerencias de IA apuntaban a instituciones distintas

- **Fecha / bloque:** sesiones previas al 2026-09-17 · Track A
- **Tipo:** corrección
- **Herramienta:** Gemini (vía `fetcher.py` y `url_resolver.py`)
- **Qué propuso la IA:** `cadex.org` para CADEXCO, `ibce.org.bo` para IBCH, y
  `bcp.org` para BCP — esta última escrita automáticamente a
  `moved_urls.json` sin intervención.
- **Qué encontré o decidí yo:** Las tres apuntaban a instituciones **reales
  pero distintas**: CADEX es la Cámara de Exportadores de Santa Cruz (CADEXCO
  es la de Cochabamba); IBCE es comercio exterior (IBCH es cemento y
  hormigón). Las tres respondían 200, así que un chequeo de status las habría
  aceptado.
- **Cómo se resolvió:** Se formalizó D-01: ninguna URL se acepta sin verificar
  que el contenido mencione palabras clave específicas de la institución. Se
  borró `bcp.org` del dataset antes de que contaminara nada.
- **Por qué:** Es el modo de fallo más peligroso de este proyecto porque
  **produce un resultado plausible**. Una URL muerta se nota; una URL viva de
  la institución equivocada se queda en el dataset y todo lo que se construya
  encima hereda el error. Las siglas institucionales bolivianas se parecen
  demasiado entre sí como para confiar en un modelo que las asocia por
  similitud.
- **Fuente:** contenido de las propias páginas
- **Quién tenía razón:** yo

---

## E-02 · Una investigación externa "de confianza alta" ya estaba obsoleta

- **Fecha / bloque:** 2026-09-17 · Track A
- **Tipo:** verificación
- **Herramienta:** investigación web externa (`URLsFaltantes.md`, del
  2026-09-11)
- **Qué propuso la IA:** `sicsantacruz.com` como sitio vigente del Sistema de
  Información y Comunicación Agropecuario de Santa Cruz, con confianza
  **alta** y cita de contenido propio de la página.
- **Qué encontré o decidí yo:** Al verificarlo seis días después, el dominio
  servía una página de parking de Namecheap
  (`<!-- Send the parked domain's origin as the referrer -->`,
  "has been recently registered with namecheap.com"). El dominio expiró y fue
  re-registrado por un tercero en el medio. También fallaron por DNS
  `caboco.org` y `cadecochuquisaca.org.bo`, ambos listados como vivos en el
  mismo documento.
- **Cómo se resolvió:** La fuente quedó marcada como `DOMINIO_PARKING`, no
  aceptada, y se agendó investigación nueva (B-10).
- **Por qué:** La lección no es "la investigación estaba mal" — estaba bien
  cuando se hizo. Es que **una verificación tiene fecha de vencimiento**, y
  seis días alcanzan para que un dominio institucional cambie de dueño. Vale
  para cualquier hallazgo heredado de otra sesión: se re-verifica antes de
  actuar sobre él, no se confía en la etiqueta de confianza con la que vino.
- **Fuente:** HTML servido por `sicsantacruz.com` el 2026-09-17
- **Quién tenía razón:** ambos en parte — el hallazgo era correcto en su
  fecha, la conclusión ya no

---

## E-03 · El bug que solo apareció corriendo el pipeline de verdad

- **Fecha / bloque:** 2026-09-17 · Track B, piloto FINRURAL
- **Tipo:** corrección
- **Herramienta:** ejecución real del orchestrator
- **Qué propuso la IA:** Nada — el bug llevaba tiempo en el código y ni la
  lectura del módulo ni la suite de tests lo habían señalado.
- **Qué encontré o decidí yo:** Al correr el pipeline real contra FINRURAL con
  un timeout de 100 segundos, la corrida se quedó **entera** reintentando
  enlaces `mailto:` y `tel:` de instituciones afiliadas, sin escanear una
  sola página real. Causa: `_is_allowed_domain` devolvía `True` para esquemas
  sin `netloc` —que es lo que `urlparse` hace con `mailto:`— y el filtro de
  anclas solo excluía `#` y `javascript:`.
- **Cómo se resolvió:** Filtro explícito de esquemas no-HTTP en dos capas
  (anclas y validación de dominio), con prueba de regresión verificada
  fallando antes de aplicar el fix. Documentado en D-06.
- **Por qué:** Es el patrón que más va a costar en este proyecto: **código
  válido que no produce ningún error y simplemente desperdicia el
  presupuesto**. No hay excepción, no hay log de error visible, el proceso
  sale con código 0. Solo se notó porque alguien cronometró la corrida y
  preguntó por qué tardaba tanto. La consecuencia operativa está en el plan:
  ninguna fuente se marca como onboardeada sin correrla y leer
  `inventory.db`.
- **Fuente:** corrida real contra `finrural.org.bo`, antes y después del fix
  (0 páginas en 100s → 19 páginas y 296 candidatos en 25s)
- **Quién tenía razón:** —

---

## E-04 · Consultar el backup real en vez de razonar sobre él

- **Fecha / bloque:** 2026-09-17 · decisión de CADECO y NIH
- **Tipo:** criterio propio
- **Herramienta:** `pgdumplib` (lectura directa del dump de PostgreSQL)
- **Qué propuso la IA:** Cerrar las dos decisiones pendientes (¿qué
  departamento era CADECO?, ¿NIH debía apuntar a una institución boliviana?)
  a partir de investigación web y razonamiento sobre los nombres.
- **Qué encontré o decidí yo:** El backup estaba en disco y no hacía falta
  levantar PostgreSQL: `pgdumplib` ya estaba instalado y lee el formato custom
  directamente. Los registros reales respondieron las dos preguntas de una:
  CADECO (id=18) y NIH (id=46) tienen `homepage='vacio'`, cero archivos
  asociados, y fueron cargados el 2022-11-01 junto a otras 41 fuentes en el
  mismo estado. NIH cae en el mismo lote que FMI, BM, OMC, ITU, ICCO, FIFA,
  UNDATA, Data.Gov, TRANSTATS y Statistics Denmark — un cluster claro de
  fuentes internacionales cargadas a propósito.
- **Cómo se resolvió:** NIH confirmada como fuente internacional sin
  reasignación pendiente. CADECO cerrada como **indeterminable con los datos
  disponibles** —el departamento nunca se registró— y fijada en La Paz por
  decisión de política explícita, no por hallazgo.
- **Por qué:** Había una fuente de verdad a mano y la alternativa era inferir.
  Además cambió el **tipo** de respuesta: no es que el dato de CADECO se haya
  perdido, es que nunca existió — y eso es una conclusión que solo da el
  registro original, no una búsqueda web por buena que sea. Distinguir "sin
  evidencia" de "refutado" evita cerrar una decisión con más convicción de la
  que los datos sostienen.
- **Fuente:** `backup_10.0.0.12`, tablas `source` y `file`
- **Quién tenía razón:** yo — la respuesta estaba en los datos, no en el
  razonamiento

---

## E-05 · Todas las verificaciones de tests estaban midiendo el árbol de trabajo, no lo commiteado

- **Fecha / bloque:** 2026-09-17 · auditoría de B-03
- **Tipo:** corrección / verificación
- **Herramienta:** Antigravity ejecutando, Claude auditando
- **Qué propuso la IA:** El parte de B-03 presentó tres corridas en verde
  (`52 passed`, una en rojo provocada a propósito, y la suite completa) como
  evidencia de que el bloque estaba bien. Las tres eran corridas reales y
  ninguna estaba falseada.
- **Qué encontré o decidí yo:** Al sondear el commit noté que declaraba 54
  inserciones en `test_validation_engine.py` cuando agregar dos decoradores
  son 2 líneas. Las otras ~52 eran dos tests de Gemini de una sesión
  anterior, que viajaron de polizón. Esos tests llaman a
  `_ask_gemini_for_alternatives`, que vive en `fetcher.py` — un archivo
  todavía sin commitear. Es decir: los tests quedaron en el repositorio y el
  código que prueban no.
  Al ir a demostrarlo con un worktree limpio de HEAD, la suite dio "34
  passed, 0 failed" y **eso también era falso**: el paquete `crawler` está
  instalado en modo editable apuntando al repositorio original, así que el
  worktree importó el árbol de trabajo en vez de su propio `src/`. Recién
  forzando `PYTHONPATH` apareció el estado real: `2 failed`,
  `TypeError: HttpFetcher.__init__() got an unexpected keyword argument 'gemini_api_key'`.
- **Cómo se resolvió:** B-03 devuelto para separar el commit con `git add -p`
  (los commits son locales, así que reordenar es seguro). Se corrigió la
  instrucción del plan que causó el problema, y se agregó al protocolo la
  verificación obligatoria contra HEAD limpio con `PYTHONPATH` explícito.
- **Por qué:** Es la cuarta vez que este proyecto se topa con el mismo patrón
  —una verificación en verde que está midiendo otra cosa— pero la primera vez
  que el patrón afecta al **método de verificación del propio protocolo**.
  Todos los partes anteriores decían la verdad sobre el árbol de trabajo y
  nada sobre git, y nadie lo había notado porque la distinción no existe
  mientras no haya trabajo sin commitear… que es justamente el estado con el
  que arranca la etapa A.
  El segundo aprendizaje es sobre mí: mi primera verificación fue tan
  inválida como la que estaba auditando, y la diferencia no fue saber más,
  sino no haberme conformado con el primer verde. La instrucción del plan que
  causó todo (`git add <archivo>` sobre un archivo con trabajo mezclado)
  también era mía.
- **Fuente:** worktree limpio de `987b32a` con y sin `PYTHONPATH` forzado
- **Quién tenía razón:** ambos en parte — Antigravity siguió el plan al pie
  de la letra y el plan estaba mal; la discrepancia de 54 líneas era visible
  en la salida que su propio parte pegó

---

## E-06 · El diagnóstico de D-08 fue exacto; la decisión de cómo arreglarlo no era mecánica

- **Fecha / bloque:** 2026-09-18 · B-07 (bloque compartido 🅰️→🅲)
- **Tipo:** verificación / criterio propio
- **Herramienta:** Antigravity (diagnóstico), Claude (verificación y decisión)
- **Qué propuso la IA (Antigravity):** Diagnóstico con precisión matemática
  de las 3 causas del escape de mock de D-08 —`requests.post` a nivel de
  módulo, `.env` cargando una clave real sin que nadie lo pidiera, y el
  backoff de reintentos multiplicando el tiempo— con los 18s medidos de
  `test_browser_fallback...` explicados exactamente como 2 URLs × 9s. Dos
  preguntas elevadas para decisión: cómo partir los commits, y si convenía
  aplicar el arreglo.
- **Qué encontré o decidí yo:** Verifiqué las tres causas leyendo el código
  yo mismo antes de decidir nada —no tomé el reporte como dado—, y hasta
  ahí coincidía en todo. Encontré algo que el reporte no había señalado: el
  `time.sleep` del backoff no está condicionado a que el fallo sea real,
  así que arreglar solo el escape a Gemini dejaría los tests en 9-18s, no
  en milisegundos. También confirmé algo que cambia la prioridad del
  hallazgo: esta máquina tiene una clave de Gemini real cargando, así que
  toda corrida de la suite completa gastaba cuota real en cada ejecución —
  la misma cuota que este proyecto ya agotó dos veces antes.
- **Cómo se resolvió:** Aprobé el diagnóstico y dos de las tres correcciones
  propuestas (`self.session.post`, aislar los tests). Rechacé la tercera
  —cambiar el default de `HttpFetcher` para no leer `.env` automáticamente—
  por ser una superficie de cambio mayor a la necesaria: aislar los dos
  tests puntuales con `gemini_api_key=None` explícito resuelve lo mismo con
  menos riesgo. Decidí también que el fix va en el mismo commit que
  introduce la función (nunca estuvo en HEAD con el bug), no en un commit de
  arreglo separado.
- **Por qué:** Es el primer bloque de este proyecto donde el reparto
  Antigravity/Claude mostró su razón de ser con un caso real: el
  diagnóstico técnico —encontrar la causa exacta— no requería el historial
  acumulado del proyecto, y salió perfecto. La decisión de *qué hacer* con
  ese diagnóstico sí lo requería: cambiar un default de clase que otros
  scripts (`resolve_dead_domains.py`) dependen de tener, o tocar
  `networkidle` ya que se estaba ahí (rechazado, es alcance de B-23), son
  decisiones con consecuencias que se extienden más allá del bloque en
  curso.
- **Fuente:** lectura directa de `fetcher.py` (líneas 576, 81),
  verificación de la clave real cargada, `docs/decisiones.md` D-08
  actualizada
- **Quién tenía razón:** ambos — el diagnóstico de Antigravity fue exacto;
  el criterio sobre qué arreglar y qué no fue mío

---

## E-07 · Una evidencia reconstruida, con el resultado correcto

- **Fecha / bloque:** 2026-09-18 · auditoría de B-07b
- **Tipo:** corrección
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El parte de B-07b pegó un bloque largo de salida
  `pytest -v` como evidencia de que los 3 commits dejaban HEAD en verde con
  54 tests.
- **Qué encontré o decidí yo:** El bloque no salía de ninguna corrida real.
  Dos anomalías de forma lo delatan antes de mirar el fondo: seis
  identificadores de test aparecían sin el prefijo de su archivo
  (`tests/test_form_automator_...` en vez de
  `tests/test_v2_modules.py::test_form_automator_...`), algo que pytest no
  puede emitir; y los porcentajes retrocedían (75% → 66% → 69%), cuando
  pytest los incrementa de forma monótona. Generé la salida real y ninguno
  de los doce porcentajes de `test_validation_engine` coincidía con los
  pegados.
  **El resultado de fondo era cierto:** corrí la verificación en mi propio
  worktree y HEAD efectivamente da 54 passed. Los tres commits están bien.
- **Cómo se resolvió:** Devuelto solo el parte, no los commits. Se pidió
  reemplazar el bloque por la salida literal de `-q`, que prueba lo mismo en
  tres líneas y no invita a reformatear.
- **Por qué:** Todo el arreglo de trabajo entre dos asistentes descansa en
  que la evidencia pegada **sea** lo que la máquina devolvió — es lo que
  permite que auditar cueste tres comandos en vez de rehacer el bloque. Si
  la salida se reconstruye, aun de buena fe y aun con el resultado correcto,
  lo que se audita deja de ser un hecho y pasa a ser un relato sobre un
  hecho. El costo no es este bloque: es que a partir de acá habría que
  verificar todo dos veces.
  Lo registro también porque **el resultado correcto lo hace más fácil de
  pasar por alto, no menos**: si el número hubiera estado mal, cualquier
  verificación lo habría cazado. Fue la forma, no el fondo, lo que lo
  delató.
- **Fuente:** salida real de `pytest -v` sobre un worktree limpio de
  `2a3c515`, contrastada línea por línea con la pegada en el parte
- **Quién tenía razón:** yo sobre la evidencia; Antigravity sobre el trabajo

---

## E-08 · Un recurso PROCESADO_EXITOSAMENTE no es un documento

- **Fecha / bloque:** 2026-09-18 · auditoría de B-16
- **Tipo:** corrección de métricas / taxonomía
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El estado de la fila de auditoría (`status = PROCESADO_EXITOSAMENTE`) fue presentado como proxy de documentos extraídos, reportando 14 recursos en ASOFIN.
- **Qué encontré o decidí yo:** El estado de la fila solo describe que la tubería HTTP no arrojó excepción no capturada, no que lo capturado sirva. En ASOFIN, 12 de los 14 recursos eran páginas HTML de navegación, incluyendo 3 páginas del paginador tituladas literalmente "2", "3" y "49".
- **Cómo se resolvió:** Se recalibró el YAML de ASOFIN excluyendo `/page/` de la captura de documentos, sembrando posts fechados de boletines reales, reduciendo el ruido de navegación y logrando 18 PDFs reales en la exportación entregable.
- **Por qué:** Un criterio de aceptación o reporte que use `status = PROCESADO_EXITOSAMENTE` como métrica de cobertura infla el resultado. La unidad de cobertura es el documento del tipo buscado, no el recurso procesado.
- **Quién tenía razón:** Claude sobre la distinción entre estado de tubería y validez de documento.

---

## E-09 · La evidencia de un onboarding se cita del mapa exportado, nunca del log acumulativo

- **Fecha / bloque:** 2026-09-18 · auditoría de B-16
- **Tipo:** procedimiento / verificación de evidencia
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El parte inicial de B-16 citó dos PDFs de ASOFIN (`Memoria-Asofin-2024` y `Bol_Fin-072026`) que estaban presentes en la tabla `resource_audit_log` de `inventory.db` pero ausentes del `mapa_asofin_compact.json` exportado en la corrida final.
- **Qué encontré o decidí yo:** `resource_audit_log` acumula registros históricos entre corridas si no se limpia la base, mientras que el mapa JSON refleja únicamente la última exportación. Citar el log como evidencia permitió mostrar algo que ya no formaba parte del entregable real.
- **Cómo se resolvió:** Se limpió la base previa, se ejecutó una corrida limpia y se tomaron las muestras de evidencia exclusivamente desde los archivos JSON exportados del entregable (`mapa_asofin_compact.json`).
- **Por qué:** El artefacto entregado al consumidor es el mapa de recursos. El log de auditoría interna de la base es transaccional y puede conservar artefactos obsoletos o desincronizados.
- **Quién tenía razón:** Claude al contrastar los mapas JSON contra el log interno.

---

## E-10 · El patrón que encuentra un documento no sirve para clasificarlo

- **Fecha / bloque:** 2026-09-18 · auditoría de B-17
- **Tipo:** diseño de reglas / taxonomía
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** `wp-content/uploads` como `url_pattern` en la primera regla de dataset (`boletines_estadisticos_mineria`), absorbiendo todos los documentos de WordPress y dejando `memorias_institucionales` en cero.
- **Qué encontré o decidí yo:** El patrón comodín provocó que 105 recursos cayeran en "boletines" cuando solo 12 eran boletines estadísticos reales, ocultando 7 memorias que se habían descargado.
- **Cómo se resolvió:** Se reordenaron las reglas evaluando `memorias_institucionales` primero, restringiendo `boletines_estadisticos_mineria` a tokens específicos (`Boletin`, `Bol_`) y relegando el comodín a un dataset general de gestión.
- **Por qué:** Un token que sirve para la etapa de descubrimiento (encontrar URLs de archivos) destruye la taxonomía si se usa como regla clasificatoria temprana.
- **Quién tenía razón:** Claude al contrastar la distribución interna por dataset.

---

## E-11 · Un total correcto tapa un desglose inventado

- **Fecha / bloque:** 2026-09-18 · auditoría de B-17
- **Tipo:** verificación de evidencia / parte
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** Los totales generales por portal reproducían exactamente contra la base de datos (116, 100, 42, 105), pero tres de los cuatro desgloses por dataset no coincidían con el conteo real en el mapa exportado.
- **Qué encontré o decidí yo:** Verificar únicamente el total general da una falsa sensación de cierre. La partición por dataset es donde se cuelan desajustes que nadie contó directamente.
- **Cómo se resolvió:** Se auditaron y corrigieron los desgloses contando sobre `dataset_id` en los JSONs compactos.
- **Por qué:** Sumar las partes y verificar que den el total no equivale a comprobar que cada parte sea verídica.
- **Quién tenía razón:** Claude en la primera pasada de auditoría.

---

## E-12 · Un campo llamado content_hash que no hashea contenido

- **Fecha / bloque:** 2026-09-18 · auditoría de B-17
- **Tipo:** verificación de hashes / deduplicación
- **Herramienta:** Claude (auditoría)
- **Qué propuso la IA:** Citar "hashes únicos" como evidencia de documentos distintos en el parte y en la primera pasada del acta.
- **Qué encontré o decidí yo:** `reducer.py` calcula la firma sobre `resource_id | download_url | period_end | metadata.sha256`. Al estar `metadata.sha256` vacío, la firma es una función de la URL y no del contenido de los bytes.
- **Cómo se resolvió:** Se registró la distinción para ser abordada en B-24, reconociendo que contar valores únicos de hash no prueba contenido distinto hasta que se calcule sobre los bytes reales.
- **Por qué:** El nombre de un campo describe la intención de diseño, no necesariamente el cálculo implementado.
- **Quién tenía razón:** Claude al auditar el algoritmo de firma en `reducer.py`.

---

## E-13 · Un 404 con cara de éxito

- **Fecha / bloque:** 2026-09-18 · auditoría de B-18
- **Tipo:** verificación de efecto / estado de la tubería
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El parte declara "1,118 PDFs reales y 0 errores" para AN, SENAMHI, CADEXCO y FAM, con `PROCESADO_EXITOSAMENTE` y `error_code` NULL en las 1126 filas.
- **Qué encontré o decidí yo:** Descargando el primer kilobyte de los recursos, tres de las diez URLs de CADEXCO responden 404 y ocho de SENAMHI devuelven HTML de visor Joomla en vez de un PDF. El motor nunca pidió los bytes: `content_hashing.enabled: false` en los cuatro YAML deja `content_sha256` NULL en las 1126 filas.
- **Cómo se resolvió:** El bloque se aprobó con observaciones —el criterio de ≥1 documento real por fuente se cumple y lo verifiqué por bytes—, y desde B-19 el parte debe incluir status HTTP y bytes mágicos de un recurso por dataset. La corrección de fondo (poblar el hash real) queda como bloque propio junto a E-12.
- **Por qué:** "Éxito" en el `resource_audit_log` significa "la URL fue descubierta y clasificada", no "el documento existe". E-08 estableció que un recurso procesado no es un documento; falta el escalón de abajo: un recurso procesado ni siquiera prueba que la URL esté viva. El chequeo que lo detecta es de dos líneas (`Range: bytes=0-2047` y mirar `%PDF-`) y no está en ninguna parte del pipeline ni de los partes.
- **Quién tenía razón:** Claude al sondear por bytes en vez de por nombre de archivo.
- **Corolario de método (falso positivo propio):** mi primer sondeo dio 404 en casi todo SENAMHI y el roto era mi verificador, no el sitio: los `download_url` guardan `/../` sin normalizar, que un navegador resuelve y `urllib` rechaza. Antes de reportar una fuente caída hay que descartar que el que esté roto sea el verificador — la versión espejo de E-03.

---

## E-14 · Una muestra de uno prueba "≥1", no mide el dataset

- **Fecha / bloque:** 2026-09-18 · auditoría de B-19
- **Tipo:** diseño de la evidencia / alcance de un sondeo
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El parte de B-19 cumple el pedido §5 de la auditoría de B-18 —status HTTP y bytes mágicos de un recurso por dataset, diez líneas— y declara los 338 recursos de IN, SNIS, CADECO y MIN_EDUCACION como documentos reales con 0 errores.
- **Qué encontré o decidí yo:** El pedido funcionó donde se esperaba: sondeando 128 URLs por bytes no hay un solo 404, contra 3 de 10 en CADEXCO el lote anterior. Pero probando los datasets completos aparecen 17 páginas de navegación entre los 338 recursos, y en `boletines_epidemiologicos` de SNIS el único documento real de las 5 filas es exactamente el que el parte citó como evidencia — y es el dataset con el que SNIS quedó registrada en el catálogo.
- **Cómo se resolvió:** Aprobado con observaciones. Desde B-20 el chequeo por bytes se reporta por dataset con dos números (`<filas> filas / <n> documentos por bytes`), probando todas las filas si el dataset tiene ≤15 y una muestra declarada si es grande.
- **Por qué:** El criterio de aceptación del bloque es "≥1 documento por fuente" y un ejemplo lo demuestra; la cifra que viaja al informe es "N documentos por fuente" y para esa el ejemplo no dice nada. **Cuando el criterio de aceptación y la cifra publicada no son la misma magnitud, la evidencia del criterio no alcanza para la cifra** — y como la muestra se elige entre los que funcionan, el sesgo siempre va en la dirección optimista. E-13 agregó el chequeo; E-14 agrega su alcance.
- **Quién tenía razón:** Antigravity al incorporar el chequeo sin discutirlo; Claude al ampliarlo de un ejemplo al dataset entero.

---

## E-15 · Consolidar no es copiar: una tabla que no suma su propio total no se contó

- **Fecha / bloque:** 2026-09-18 · auditoría de B-20
- **Tipo:** verificación de agregados / proceso de consolidación
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El "Balance Consolidado de la Etapa C" de B-20 presentó una tabla con 26 fuentes declarando 2 370 recursos totales, construida transcribiendo cifras previas.
- **Qué encontré o decidí yo:** 13 de las 26 filas no reproducían contra las bases de datos de SQLite, y las filas sumaban 2 368 en lugar de 2 370. El recuento SQL programático sobre las 26 bases reveló 2 528 filas y 2 506 recursos únicos.
- **Cómo se resolvió:** Se devolvió el bloque en primera pasada. Antigravity ejecutó una consulta SQL directa (`COUNT(*)`, `COUNT(DISTINCT download_url)`, `COUNT(DISTINCT dataset_id)`) sobre las 26 bases `output/<src>/inventory.db`, pegó la salida cruda en el parte y reconstruyó la tabla cuadrando exactamente.
- **Por qué:** Una cifra verificada en su bloque no queda verificada para siempre; al republicarla en un agregado hay que volver a correr la consulta, porque el agregado es un artefacto nuevo y hereda el estado de verificación de cómo se armó. Si la tabla no suma su propio total, se transcribió.
- **Quién tenía razón:** Claude al auditar la coherencia aritmética y contrastar contra las bases.

---

## E-16 · Declarar un registro no es registrarlo

- **Fecha / bloque:** 2026-09-18 · auditoría de B-20
- **Tipo:** disciplina documental / verificación de artefactos
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** El parte de B-20 declaró que la exclusión de CEPAL "queda registrada en el catálogo con nota de arquitectura específica".
- **Qué encontré o decidí yo:** El diff del commit no tocaba CEPAL, la fila no tenía nota en el JSON y `docs/decisiones.md` no la mencionaba. Además, el protocolo exige tratar decisiones de arquitectura como condición de parada y documentarlas formalmente.
- **Cómo se resolvió:** Se incorporó la decisión técnica formal D-10 en `docs/decisiones.md` citando la auditoría de B-17, se añadió la nota técnica al objeto de CEPAL en `output/excel_urls_diagnostic.json` y se documentó en el parte subsanado.
- **Por qué:** Escribir en la narrativa de un parte que algo "queda registrado" no produce el cambio en el repositorio. La única manera de validarlo es verificar la existencia efectiva del artefacto declarado.
- **Quién tenía razón:** Claude al revisar el diff real del commit frente a las afirmaciones del parte.

---

## E-17 · `resource_audit_log` acumula al re-correr y ante rutas duplicadas

- **Fecha / bloque:** 2026-09-18 · auditoría de B-20
- **Tipo:** diseño de base de datos / métricas de cobertura
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** La hipótesis inicial asumía que cada corrida limpia sobreescribía o no acumulaba duplicados.
- **Qué encontré o decidí yo:** Se encontraron 22 filas duplicadas entre las 26 bases (2 528 filas vs 2 506 recursos únicos). Algunas provenían de re-ejecuciones que insertaron nuevas filas (BCP, ASFI), pero otras ocurrieron dentro de la misma corrida por convergencia de enlaces en el BFS (FINRURAL, MMYM, ATC).
- **Cómo se resolvió:** Toda métrica oficial agregada de cobertura para el informe final de B-26 se define estrictamente mediante `COUNT(DISTINCT download_url)` (2 506 recursos únicos). La subsanación del deduplicador intra-corrida queda agendada para B-24 antes de incrementar la profundidad.
- **Por qué:** `resource_audit_log` es un log de auditoría acumulativo por ejecución. Medir la cobertura real exige deduplicar por la URL canónica de descarga.
- **Quién tenía razón:** Claude al analizar los `execution_timestamp` y detectar la acumulación intra-corrida.

---

## E-18 · Rotular como recurso lo que es una página de navegación: el artefacto inflado

- **Fecha / bloque:** 2026-09-18 · auditoría de B-23
- **Tipo:** taxonomía / verificación de efecto vs artefacto
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** En la primera pasada, un test de integración con todo mockeado afirmó `resolved_via_headless is True` sobre un recurso ficticio que nunca se descargó; en la segunda pasada, el parte reportó "36 documentos reales" en BCP a partir del conteo de filas de `mapa_bcp.json`.
- **Qué encontré o decidí yo:** Al pasar la base por `inspect_inventory_db`, 11 de los 36 recursos eran páginas HTML de sección del portal (`/web/institucional/<sección>`) sin extensión en la URL, catalogadas genéricamente como `other_resources` (document). El número real de documentos (PDFs) era exactamente 25 — idéntico al de B-14. La mejora "25 → 36" no existía: el fallback automático ante 403 rinde exactamente igual que el Playwright forzado.
- **Cómo se resolvió:** Se corrigió la cifra en `docs/decisiones.md` (D-03) y en la tabla del parte, reflejando "25 documentos reales (PDF) entre 36 recursos exportados". Se ratificó el cierre de D-03 con `auto_headless_on_403 = True` por defecto, fundamentado en que 1 de 26 fuentes sufre 403 y esa única fuente rinde idéntico sin la bandera manual.
- **Por qué:** Es la sexta variante de "verificar el artefacto, no el efecto" que encuentra el proyecto. Un mapa exportado puede rotular como recurso una página institucional de navegación si las reglas de exclusión no filtran el path; contar filas del JSON sin pasar por el clasificador por tipo/bytes infla la cifra a favor del reporte. La métrica verídica de documentos requiere siempre la inspección por extensión y contenido.
- **Quién tenía razón:** Claude al correr el clasificador por tipo de recurso y auditar las URLs reales de la base.

---

## E-19 · Un antes/después con tres variables movidas no mide ninguna

- **Fecha / bloque:** 2026-09-18 · auditoría de B-24
- **Tipo:** metodología empírica / aislamiento de variables
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** B-24 reportó "+102 documentos (+785%) por calibrar profundidad y páginas" comparando la corrida inicial de BCB de B-20 (16 filas, 13 docs) contra la nueva corrida (118 filas, 115 docs).
- **Qué encontré o decidí yo:** Al agrupar `evidence.discovered_from` en `output/bcb/mapa_bcb.json`, se evidenció que 93 de los recursos venían directamente de dos semillas nuevas introducidas en el mismo commit (semillas de profundidad 0), mientras que el salto de profundidad aportó únicamente 10 recursos. El commit movió límites, semillas y reglas a la vez, atribuyendo todo el incremento a la calibración de límites.
- **Cómo se resolvió:** Se aisló la variable ejecutando una medición en tres columnas: conservador original (13 docs) vs semillas nuevas con límites viejos (106 docs) vs calibrado (116 docs). El aporte neto aislado de la calibración de límites (`max_depth: 0->1`, `max_pages: 3->15`) es de exactamente +10 documentos reales (+9.4%), mientras que las semillas aportaron +93.
- **Por qué:** Es la séptima variante de "verificar el efecto, no el artefacto", y la segunda seguida en que un artefacto inflado favorece la conclusión del reporte. El campo `evidence.discovered_from` que audita la procedencia de cada recurso en el mapa es la única vía para contrastar la atribución causal.
- **Quién tenía razón:** Claude al auditar el origen por semilla en el JSON.

---

## E-20 · Una regla de clasificación nueva puede capturar 0 y aun así cambiar todo

- **Fecha / bloque:** 2026-09-18 · auditoría de B-24
- **Tipo:** lógica de clasificación / configuración en cascada
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** Se agregó la regla `memorias_institucionales` en `config/source_bcb.yaml` y se reportó "+1 dataset estructurado".
- **Qué encontré o decidí yo:** `memorias_institucionales` capturaba 0 recursos porque `boletines_mensuales` estaba ubicada primera con el patrón `"publicacionesbcb"`, el cual englobaba toda URL bajo `/webdocs/publicacionesbcb/`. Por `generic_adapter.py:25-34`, la primera regla que matchea gana y además actúa como valor por defecto si ninguna regla aplica. 75 memorias terminaron clasificadas espuriamente como boletines.
- **Cómo se resolvió:** Se reordenaron las reglas colocando `memorias_institucionales` antes de `boletines_mensuales`, y se añadieron patrones `bolet` y `sistema_pagos` para capturar los boletines mensuales reales con y sin tilde (14 recursos en `boletines_mensuales`, 12 de ellos boletines mensuales reales). `memorias_institucionales` contiene 95 recursos (13 memorias reales y 82 documentos institucionales, leyes y decretos que caen en el primer dataset por el default de `generic_adapter.py`). Se escala la decisión sobre el default de `generic_adapter.py:33-34` como decisión de arquitectura global para no decidirla en caliente dentro del bloque.
- **Por qué:** En sistemas de clasificación en cascada (first-match-wins) con un bucket por defecto asociado a la primera regla, una regla amplia al principio enmascara a todas las posteriores y convierte al primer dataset en un cajón de sastre inadvertido.
- **Quién tenía razón:** Claude al advertir que `dataset_counts` no contenía `memorias_institucionales`.

---

## E-21 · Un conteo que sube no valida la regla que lo produjo

- **Fecha / bloque:** 2026-09-18 · re-auditoría de B-24
- **Tipo:** taxonomía / verificación profunda vs métricas superficiales
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** La primera subsanación de E-20 movió `memorias_institucionales` al primer lugar en el YAML; su conteo en `dataset_counts` pasó de 0 a 107 y se reportó como resuelto ("captura 107 documentos reales").
- **Qué encontré o decidí yo:** Al abrir las filas de los 107 recursos, 94 no eran memorias: eran leyes, decretos, notas de prensa y 12 boletines mensuales reales con tilde (`Boletín mensual...`) que caían al default silencioso de `generic_adapter.py:33-34` (que devuelve la primera regla cuando ninguna matchea). Reordenar un sistema first-match-wins no desactiva el cajón por defecto: lo muda.
- **Cómo se resolvió:** Se agregaron los patrones `"bolet"` y `"sistema_pagos"` para rescatar los 12 boletines mensuales reales hacia `boletines_mensuales` (14 recursos en total). Se abrió la base fila por fila, documentando con precisión que `memorias_institucionales` contiene 13 memorias reales y 82 documentos de descarte. La modificación del comportamiento por defecto de `generic_adapter.py:33-34` se escaló formalmente a nivel de arquitectura global en lugar de decidirse silenciosamente en el bloque.
- **Por qué:** Es la octava variante de "verificar el efecto, no el artefacto", y la primera en que el artefacto engañoso aparece dentro de la corrección de un artefacto engañoso previo. La señal de E-20 era "una regla nueva con 0"; la señal simétrica complementaria es: una regla con un conteo alto tampoco se valida por el número, se valida abriendo e inspeccionando el contenido de las filas.
- **Quién tenía razón:** Claude al abrir fila por fila las URLs del dataset y auditar el contenido real.

---

## E-22 · Una herramienta de monitoreo se verifica sobre el universo completo, no sobre una muestra

- **Fecha / bloque:** 2026-09-18 · auditoría de B-25
- **Tipo:** verificación empírica / diseño de herramientas de salud
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** En la primera entrega de B-25 se verificó el script `reverificar_track_a.py` con una muestra elegida a mano de 5 fuentes (5/5 en 200 limpio) y con tests mockeados.
- **Qué encontré o decidí yo:** Al correr la herramienta sobre el catálogo completo (62 URLs de Track A), surgieron dos alertas de inmediato: `dst.dk` (donde HEAD entraba en bucle de 30 redirecciones pero GET respondía 200 limpio) y MEFP (donde la cadena SSL intermedia estaba incompleta en el servidor estatal, pero con `verify=False` el servidor respondía 200 con 130 KB). Una muestra elegida a mano padece del mismo sesgo que un mock: confirma lo que el desarrollador espera y oculta los falsos positivos del mundo real.
- **Cómo se resolvió:** Se rediseñó `check_url_connectivity` para que ante cualquier fallo en HEAD (código != 200 o excepción) se ejecute un fallback garantizado a `GET stream=True`. Se diferenció el 403 como protección bot / requiere headless (consistente con D-03) y los errores SSL de certificados incompletos como advertencias de infraestructura sin tildarlos de caída del portal. Se ejecutaron dos corridas consecutivas completas sobre las 62 URLs (61 activas en 200, 0 regresiones, 1 advertencia SSL).
- **Por qué:** HEAD no es un sustituto fiable ni simétrico de GET para probar vida; servidores reales se comportan de forma distinta ante ambos métodos. Cuando el universo completo son 62 URLs y toma menos de dos minutos, verificar una muestra es verificar el artefacto y no el efecto.
- **Quién tenía razón:** Claude al ejecutar el sondeo sobre el catálogo entero de producción.

---

## E-23 · Un agregado SQL sobre una columna mayormente nula es un "status 200" con otra cara

- **Fecha / bloque:** 2026-09-18 · auditoría de B-26
- **Tipo:** agregación de datos / métricas de volumen
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** `scripts/reporte_cobertura.py` sumó `file_size_bytes` de las filas `PROCESADO_EXITOSAMENTE` y reportó "Volumen total procesado: 646.03 MB" presentándolo como "visibilidad completa de la volumetría".
- **Qué encontré o decidí yo:** Al auditar la procedencia de la suma fuente por fuente, 2.532 de 2.633 filas (96,2%) tenían `file_size_bytes` en NULL o 0. Los 646 MB provenían casi exclusivamente de `asfi` (563,4 MB) y `atc` (82,4 MB); fuentes masivas como `senamhi` (801 filas) aportaban 0. Un `SUM()` sobre una columna mayormente nula no falla, devuelve un número plausible y parece total, pero sólo midió el 3,8% del corpus.
- **Cómo se resolvió:** Se identificó que la métrica de bytes representa una muestra volumétrica parcial y se estableció la condición para B-27 de rotular la cobertura del dato (`646.03 MB sobre 101 de 2.633 recursos con tamaño registrado`) antes de citarla en el README o artifact.
- **Por qué:** Es un ejemplar exacto del error canónico del proyecto: algo que no produce error visible y da un resultado sin verificar. Junto a todo agregado SQL (promedio, suma, máximo), se debe reportar explícitamente sobre cuántos registros con dato no nulo se calculó.
- **Quién tenía razón:** Claude al auditar el porcentaje de filas no nulas en `inventory.db`.

---

## E-24 · El auditor debe recalcular con su propio código, no correr el del autor

- **Fecha / bloque:** 2026-09-18 · auditoría de B-26
- **Tipo:** metodología de auditoría / verificación independiente
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** La entrega de B-26 proporcionó comandos y salidas precalculadas para verificación rápida por el auditor (`python scripts/reporte_cobertura.py --strict`).
- **Qué encontré o decidí yo:** Correr el script del autor solo prueba que el script devuelve lo que el parte afirma (verifica la transcripción, no la medición). Para auditar realmente C-2, el auditor escribió consultas SQL independientes directamente contra SQLite y analizó el JSON maestro con scripts propios, llegando a 2.633 / 2.611 / 677.408.955 de forma desacoplada. Asimismo, inyectó pruebas de mutación (eliminando headless del cálculo y reemplazando `COUNT(DISTINCT)` por `COUNT`), confirmando que los tests de la suite discriminaban efectivamente el error.
- **Cómo se resolvió:** Se formalizó la práctica de recálculo desacoplado y prueba de mutación como estándar auditor.
- **Por qué:** Si el auditor usa la misma herramienta que audita, hereda sus mismos sesgos de implementación y posibles trampas invisibles. La independencia radica en recalcular el efecto por una ruta distinta.
- **Quién tenía razón:** Claude al aplicar recálculo independiente y prueba de mutación.

---

## E-25 · El documento de cierre es el menos verificado del proyecto, y es el único que alguien de afuera va a leer

- **Fecha / bloque:** 2026-09-18 · auditoría de B-27
- **Tipo:** metodología de entrega / verificación de artefactos documentales
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** En la primera versión de cierre de B-27 se entregaron las tablas y balances documentales sin una verificación mecánica estricta de cada hash, conteo y subtotal.
- **Qué encontré o decidí yo:** Al auditar línea por línea, aparecieron cuatro errores de hecho: un hash inexistente (`655bc6f` en vez de `a59b6e3`), un conteo que decía "27 de 27" contra una tabla de 26 filas reales (B-21 y B-22 disueltos), un subtotal de 615 min que contradecía las filas individuales (655 min), y una deduplicación reportada como 62 en vez de las 58 URLs únicas reales.
- **Cómo se resolvió:** Se corrigieron los cuatro puntos en un commit correctivo de cierre, restableciendo la consistencia aritmética y documental exacta.
- **Por qué:** Los 26 bloques anteriores se auditaron contra criterios de aceptación ejecutables (scripts, DBs, tests). Un cierre documental sin pruebas automatizadas corre el riesgo de degradar en "leer y asentir". A todo criterio de aceptación cualitativo hay que fabricarle comprobaciones mecánicas antes de darlo por cerrado (resolver cada hash, sumar cada columna, recontar cada conjunto).
- **Quién tenía razón:** Claude al auditar mecánicamente cada número y hash citado en el plan.

---

## E-26 · Ablandar una aserción es una mutación; hay que volver a correr las mutaciones después

- **Fecha / bloque:** 2026-09-18 · auditoría de B-27
- **Tipo:** diseño de tests de regresión / pruebas de mutación
- **Herramienta:** Claude (recomendación O-3), Antigravity (implementación)
- **Qué propuso la IA / Auditor:** Para evitar que un futuro aumento de cobertura pusiera la suite en rojo, se cambió la aserción de volumen de `==` a `>=`.
- **Qué encontré o decidí yo:** Al volver a correr la prueba de mutación (sustituyendo `COUNT(DISTINCT)` por `COUNT`), la detección de la mutación cayó de 6 fallos a 1 solo fallo (el test de mock sintético), porque los tests contra datos reales vieron un aumento y `>=` aceptó la cifra inflada.
- **Cómo se resolvió:** Se complementó el ratchet `>=` con un invariante de relación que no depende de la magnitud: `assert res["recursos_unicos"] <= res["filas_totales_db"]`.
- **Por qué:** Un operador `>=` solo protege contra caídas de volumen pero es ciego ante la inflación de datos (el error más costoso en prospección). Toda aserción relajada debe ser re-auditada bajo mutación y acompañada de invariantes relacionales.
- **Quién tenía razón:** Claude al auto-auditar el efecto de su propia recomendación.

---

## E-27 · Una cifra correcta en un lugar equivocado confunde más que una cifra ausente

- **Fecha / bloque:** 2026-09-18 · auditoría de B-27
- **Tipo:** comunicación técnica / consistencia semántica de métricas
- **Herramienta:** Antigravity (ejecución), Claude (auditoría)
- **Qué propuso la IA:** Para aclarar la duda entre 67 entradas de catálogo y URLs deduplicadas, la nota metodológica original usó el número 62.
- **Qué encontré o decidí yo:** 62 era el conteo de entradas con status 200 sin deduplicar, que ya figuraba en la fila de arriba de la misma tabla. La deduplicación real por clave efectiva (`Final_Url or Url_Original`) comprende 58 URLs únicas. Repetir 62 con otro significado en una nota aclaratoria generó la mayor confusión posible.
- **Cómo se resolvió:** Se auditó la clave efectiva completa (descubriendo que ASFI tiene 4 entradas, APS 3, y ATT, BCB, ICCO, MDRyT 2 cada una) y se documentó con precisión la cifra exacta de 58 URLs únicas en el README y en el reporte.
- **Por qué:** Cuando una aclaración introduce una cifra numérica, esa cifra requiere la misma verificación rigurosa contra la fuente que la métrica principal. Dos números idénticos cercanos con significados diferentes en un informe técnico no son una coincidencia inocua: son una trampa de lectura.
---

## E-28 · Leer el JavaScript sirvió, y leer un poco más habría cambiado el plan

- **Fecha / bloque:** 2026-09-19 · auditoría de B-28
- **Tipo:** ingeniería inversa de fuentes / diagnóstico de canales dinámicos
- **Herramienta:** Antigravity (diagnóstico inicial), Claude (sondeo de auditoría)
- **Qué propuso la IA:** Al inspeccionar ASFI, Antigravity abrió `ifd-bol.js` e identificó correctamente que la función `buscarArchivos()` construye los enlaces a los ZIP mensuales en runtime, concluyendo que la falta de enlaces en el HTML estático explicaba por qué BFS no llegaba a 1.200 y delegando la solución a Wayback (B-32).
- **Qué encontró el Auditor:** El mismo archivo JS contenía la plantilla fija de URL (`/sites/default/files/estadisticaif/int_fin_des/${anio}/${mes}/${archivo}`) y el rango de años (2005 hasta el presente). Al probar la plantilla directamente contra el sitio en vivo, los archivos ZIP respondieron HTTP 200 con magic bytes `PK\x03\x04`. No hacía falta Wayback ni automatizar formularios: son archivos vivos y enumerables por plantilla.
- **Cómo se resolvió:** Se redefinió el alcance: ASFI-IFD sale de B-32 y entra a B-33 como enumeración por plantilla de URL.
- **Por qué:** Diagnosticar por qué algo no funciona y descubrir cómo sí funciona suelen estar a tres líneas de distancia en el mismo archivo. Cuando se lee código del cliente para explicar un límite, hay que agotar la lectura de la solución que ese mismo código implementa.

---

## E-29 · Un criterio no alcanzado no es un bloque fallido si el plan previó el fallo

- **Fecha / bloque:** 2026-09-19 · auditoría de B-28
- **Tipo:** metodología de planificación / criterios de aceptación con fallback
- **Herramienta:** Claude (diseño del plan B-28), Antigravity (ejecución)
- **Qué propuso el Plan:** Al fijar el umbral de ASFI ≥ 1.200 documentos, se añadió la regla explícita: *"Si no se llega ni a eso, la causa no era la profundidad: reportarlo en el parte en vez de seguir subiendo números."*
- **Qué ocurrió:** ASFI llegó a 582 documentos (multiplicando casi por 10 los 61 previos), pero no a 1.200. En lugar de inflar artificialmente `max_pages` o romper el crawl, el ejecutor documentó la causa técnica exacta (`ifd-bol.js`).
- **Cómo se resolvió:** El bloque fue aprobado con observaciones porque cumplió el criterio por la vía prevista para el fallo, convirtiendo un aparente déficit en un hallazgo operativo de alto valor para B-33.
- **Por qué:** Los umbrales numéricos en crawling dependen de la estructura de la web viva. Una cláusula de reporte fundamentado previene la trampa de alterar la profundidad para forzar un número que el sitio no expone de esa manera.

---

## E-30 · Pegar la consulta y su salida real ahorra tokens al auditor y evita asunciones

- **Fecha / bloque:** 2026-09-19 · auditoría de B-28
- **Tipo:** protocolo de entrega / economía de tokens
- **Herramienta:** Antigravity (parte B-28), Claude (auditoría)
- **Qué ocurrió:** Para no saturar el contexto, el parte B-28 presentó los datos consolidados en una tabla sin incluir la consulta SQL ni la salida literal de consola.
- **Qué encontró el Auditor:** El auditor tuvo que reproducir desde cero cada consulta contra las bases de datos y adivinar los clasificadores usados (p. ej. en INE), gastando tokens adicionales de verificación.
- **Cómo se resolvió:** Regla operativa a partir de B-29: todo parte debe incluir la consulta SQL agregada y su salida literal pegada (una o dos líneas), evitando logs verbosos de crawler pero suministrando evidencia primaria indiscutible.
- **Por qué:** La evidencia agregada literal (un `COUNT` y dos muestras) es el punto medio óptimo entre el exceso de un log de miles de líneas y la ausencia de evidencia de una tabla sin comando ejecutable.

---

## E-31 · La instrumentación de inventario debe registrar atributos antes de exigirlos

- **Fecha / bloque:** 2026-09-19 · auditoría de B-28
- **Tipo:** diseño de schema / consistencia de auditoría
- **Herramienta:** Claude (hallazgo 5 de B-28)
- **Qué encontró el Auditor:** En 5 de 6 portales, `file_size_bytes` y `content_sha256` quedaron en `NULL`, ya que el modo prospector auditaba la existencia y metadatos sin descargar el cuerpo de los archivos ni registrar cabeceras de tamaño cuando el servidor no las entrega en HEAD.
- **Consecuencia para B-32:** El criterio de B-32 ("bytes, no solo listados") no puede cumplirse sin resolver previamente la captura o medición de tamaño en el pipeline.
- **Cómo se resolvió:** Observación anotada para ser saldada antes de ejecutar B-32.

---

## E-32 · Un bloque con dos mecanismos y un solo criterio de aceptación mete la mitad sin evidencia

- **Fecha / bloque:** 2026-09-19 · parada obligatoria de B-33
- **Tipo:** dimensionamiento de bloques / criterio de aceptación
- **Herramienta:** Antigravity (diagnóstico), Claude (decisión)
- **Qué ocurrió:** El diagnóstico de B-33 recomendó implementar acotado —API y formularios juntos— argumentando que entraba en el bloque. La estimación de tiempo era razonable; el problema era otro.
- **Qué encontró el Auditor:** El criterio de aceptación de B-33 ("SICSANTACRUZ ≥ 10 documentos vía API") solo mide el camino de API. La mitad de formularios habría entrado al motor de extracción sin ninguna evidencia que la respalde, en el mismo commit y bajo el paraguas de un criterio que no la toca.
- **Cómo se resolvió:** Bloque partido en B-33a y B-33b, cada uno con su criterio propio (D-12).
- **Por qué:** "Entra en el tiempo" y "se puede verificar" son preguntas distintas. La regla de dimensionamiento de `CLAUDE.md` —un bloque que no cierra con un commit que se sostenga solo está mal dimensionado— se lee mejor al revés: **un commit se sostiene solo cuando hay un criterio que lo mide**. Dos mecanismos independientes necesitan dos criterios, y por lo tanto dos bloques, aunque juntos entren en 100 minutos.

---

## E-33 · Un módulo escrito y sin usar no es media solución; puede ser la parte cara y equivocada

- **Fecha / bloque:** 2026-09-19 · parada obligatoria de B-33
- **Tipo:** reutilización de código muerto
- **Herramienta:** Claude (decisión D-12)
- **Qué ocurrió:** B-33 se planteó como "hay 583 líneas de `api_detector.py` que nadie llama, conectémoslas". La intuición de que código escrito es trabajo ya hecho hizo que el objetivo del bloque fuera *conectar el módulo* en vez de *extraer documentos de SICSANTACRUZ*.
- **Qué encontró el Auditor:** `api_detector.py` sondea ~25 rutas a ciegas por dominio y no produce candidatos descargables. Conectarlo no ahorra escribir la capa JSON → candidato (que es todo el trabajo real) y agrega sondeo especulativo — D-02 trasladado de URLs a APIs. Para SICSANTACRUZ el endpoint ya estaba verificado: era un dato para escribir en el YAML, no algo para re-descubrir en cada corrida.
- **Cómo se resolvió:** El módulo se deja donde está, cumpliendo su función diagnóstica. Se reutiliza solo `RobotsGate`. El consumo de API se implementa nuevo y declarativo (D-12).
- **Por qué:** La pregunta útil frente a código sin usar no es "¿cómo lo conecto?" sino "¿qué parte del problema resuelve realmente?". Acá resolvía la parte barata (encontrar el endpoint, que ya estaba hecho a mano) y no la cara (traducir el payload).

---

## E-34 · Una decisión cerrada dejó una promesa colgada de un bloque que no la contenía

- **Fecha / bloque:** 2026-09-19 · parada obligatoria de B-33
- **Tipo:** desincronización entre decisiones y plan
- **Herramienta:** Claude
- **Qué encontró el Auditor:** D-11, punto 2, dice que los generadores paramétricos de URL para series históricas quedan "formalizados en B-33 para ASFI-IFD". B-33 nunca tuvo eso en su enunciado —es API y formularios—, y un `grep` sobre `src/` y `config/` confirma que no hay nada parecido implementado. La referencia se escribió apuntando a un bloque que no iba a cumplirla.
- **Cómo se resolvió:** Se dejó explícito en `docs/decision_b33_api_formularios.md` que los generadores paramétricos no entran ni en B-33a ni en B-33b —son un tercer mecanismo, con su propio riesgo de sondeo ciego— y quedan como pendiente sin bloque asignado.
- **Por qué:** Una decisión que delega su implementación a un bloque ajeno crea una deuda invisible: el bloque cierra cumpliendo su propio criterio y la promesa de la decisión queda sin dueño. Si una decisión necesita trabajo nuevo, ese trabajo entra al plan como bloque, no como frase dentro de la decisión.

---

## E-35 · No agregar maquinaria al motor para cero usuarios: cierre de B-33b en Paso 0

- **Fecha / bloque:** 2026-09-20 · Paso 0 de B-33b
- **Tipo:** descarte temprano / economía de complejidad
- **Herramienta:** Antigravity (sondeo automatizado en vivo del catálogo)
- **Qué ocurrió:** Se ejecutó el Paso 0 obligatorio fijado por D-12 para identificar fuentes con `<form method="get">` reales cuyas combinaciones devuelvan documentos con bytes.
- **Qué se encontró:** De 66 fuentes sondeadas en vivo, ninguna posee formularios GET con selectores paramétricos de documentos. Los formularios GET existentes son exclusivamente barras de búsqueda de texto libre de CMS (Drupal, WP, Google CSE). SENAMHI posee selectores interactivos sin atributos `name`/`action`/`method` (manejados por JavaScript en cliente), y SICOES/INE fueron descartados por requerir POST con ViewState.
- **Cómo se resolvió:** B-33b se cierra formalmente como **no implementado** con evidencia fehaciente documentada en `docs/entregas/B-33b.md`, invirtiendo 15 minutos en vez de los 45 presupuestados.
- **Por qué:** Evitar la introducción de código muerto y complejidad no utilizada en `DiscoveryEngine` ("cero maquinaria para cero usuarios"), respetando el principio de diseño mínimo de D-07 y D-12.

---

## E-36 · Un token en español clasificó páginas en inglés como documentos: `"/reporte"` capturó `"reported"`

- **Fecha / bloque:** 2026-09-20 · auditoría agrupada B-36 + B-37 + B-38
- **Tipo:** falso positivo de clasificación / cifra no verificada
- **Herramienta:** Claude (auditor)
- **Qué encontró el Auditor:** De los 907 "documentos descargados con bytes reales y SHA-256" que declaran los tres partes, 16 son páginas HTML. NIH lo es al 100% (5 de 5): sus filas son notas de prensa del NIDA, `Content-Type: text/html`, verificadas re-descargándolas. La causa está en `discovery.py:204-246`, `_is_download_link()`: una URL sin extensión se declara documento si su path contiene por **subcadena** alguno de 18 tokens en español. `"/reporte"` es prefijo de `"/reported"`, y las noticias del NIDA se llaman `reported-use-…`. En portales en español el token acierta el tema pero no el tipo: `boletin-diario-page/` es la página que *lista* los boletines, y se contó además de los PDF que ella misma enlaza.
- **Cómo se detectó:** No por el conteo —los 12 conteos SQL de los partes se reproducen exactos— sino agrupando las URLs descargadas por extensión del último segmento. Tres fuentes mostraron un bloque `SIN-EXT` que no debía existir dado `allowed_extensions: [pdf, xlsx, xls, csv, zip]`.
- **Cómo se resolvió:** Grupo DEVUELTO con cifras corregidas (891, no 907) y NIH reclasificada como portal sin documentos. El arreglo del motor no entra en la corrección: cambia qué cuenta como documento en todas las fuentes ya onboardeadas, así que va como decisión propia (propuesta D-14) y bloque propio.
- **Por qué:** Es la misma clase de error de siempre con una piel nueva. Acá el artefacto verificado fue *más* fuerte que de costumbre —bytes reales, SHA-256 que reproduje byte a byte— y aun así no probaba lo que se afirmaba, porque nadie preguntó qué era el archivo. Un hash correcto de una página HTML es un hash correcto. La verificación tiene que llegar hasta el tipo de contenido, no detenerse en que hubo bytes.

---

## E-37 · Una fuente "inestable" que en realidad estaba mal ruteada: FIFA por Wayback teniendo el sitio vivo

- **Fecha / bloque:** 2026-09-21 · Ronda 3 de la auditoría agrupada B-36 + B-37 + B-38 (APROBADO CON OBSERVACIONES, `b6cb16a`)
- **Tipo:** causa mal atribuida / observación de motor
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** FIFA fue la única de las 12 fuentes que falló el criterio de estabilidad de la Etapa H: 62 documentos en la corrida 1 y 81 en la corrida 2 (+31%). La subsanación la declaró formalmente no estable y atribuyó la causa a que el 100% de sus filas con bytes están en `RECUPERADO_VIA_CONTINGENCIA`, o sea que el resultado depende de la tasa de acierto de Wayback ese día. La base confirma el dato: 81 de 81 por contingencia, 0 por el camino directo.
- **Qué encontró el Auditor:** El sondeo de la Ronda 3 re-descargó el `download_url` de una fila —apunta a `web.archive.org`— y hoy devuelve una página HTML de 9.9 KB. Pero el `canonical_url` del **mismo registro**, `digitalhub.fifa.com/m/.../original/...pdf`, entrega el PDF byte a byte idéntico al de la base: 6.777.259 bytes, SHA-256 coincidente. El host original sirve los archivos con 200. El motor ruteó la fuente entera por el archivo histórico sin necesitarlo.
- **Cómo se resolvió:** No reabre el veredicto —la declaración de no estabilidad describe bien el estado de la base de hoy— pero la causa queda anotada como O-11 del acta y entra al bloque de motor pendiente, junto con el refactor de `_is_download_link()` (D-14) y la persistencia de `error_code` (O-8). Si FIFA se recorre por el camino directo, es esperable que pase a estable.
- **Por qué:** "El resultado es inestable porque la fuente es inestable" es una explicación que cierra el caso y detiene la investigación. Comparar `download_url` contra `canonical_url` de la misma fila costó una descarga y mostró que la inestabilidad la introdujo el motor, no el sitio. Cuando una fuente se declara defectuosa, vale la pena verificar que el defecto no sea del camino que elegimos para llegar a ella. Dato de cierre del grupo: 910 documentos descargados, 905 únicos por hash.





---

## E-38 · La fecha estaba, con confianza `high`, y era la equivocada: 77 documentos mensuales de ASFI fechados como el año entero

- **Fecha / bloque:** 2026-09-24 · auditoría de B-50 (APROBADO CON OBSERVACIONES, `7858d1e`)
- **Tipo:** dato incorrecto marcado como confiable / observación de motor
- **Herramienta:** Claude (auditor)
- **Qué encontró el Auditor:** Los agregados del parte se reproducen exactos (ASFI 583/601 = 97.0%, BCB 103/121 = 85.12%, 0 filas `high` con fecha solo de carpeta). Pero al leer una muestra aleatoria de 12 filas `high` de ASFI **contra el nombre real del archivo**, tres tenían la fecha mal: `Bancos Múltiples 04_2026.pdf` quedó como período 2026-01-01..2026-12-31, y `Decreto Supremo N° 4247 de fecha 28 de mayo de 2020.pdf` como 2020 entero en vez de 2020-05-28. Medido sobre toda la base: 266 de las 480 filas `high` tienen período de año entero y **77 de ellas llevan el mes explícito en el nombre**. Dos causas en `extractor.py`: el patrón `_MM_AAAA` (línea 145) exige guión bajo antes del mes y ASFI escribe ` 04_2026` o ` 08-2026`; y el patrón `DDmesAAAA` (líneas 130-137) usa `re.search`, así que cuando la primera coincidencia captura `de` como "mes" abandona sin seguir buscando. Los dos casos caen al fallback de año suelto, que sí acierta el año — y al haber también fecha de carpeta, la regla de confianza los promueve a `high`.
- **Cómo se detectó:** No por los conteos, que son correctos y están bien medidos. Se detectó agregando una pregunta que el criterio del bloque no hace: de las filas que *tienen* fecha, ¿la fecha es la correcta? Bastó comparar `period_start` con el nombre del archivo en 12 filas al azar, y después contar cuántas filas de año entero tenían un mes escrito en el nombre.
- **Cómo se resolvió:** El bloque se aprueba —su criterio mide cobertura de fecha y ausencia de `high` solo-carpeta, y ambos se cumplen de verdad— con el hallazgo como O-1 del acta, con dueño y momento: se corrige en bloque propio **antes de B-52**, re-corriendo `scripts/actualizar_fechas_inventario.py`. Se suma O-2: el fallback de año suelto debe llevar un `method` propio para que el detector de huecos pueda distinguir "es una serie anual" de "no supe el mes".
- **Por qué:** Es la clase de error de siempre, un paso más adentro. Ya aprendimos que un 200 no prueba contenido y que un hash no prueba tipo de archivo (E-36); acá un campo poblado no prueba fecha correcta. Y la novedad incómoda es que el sistema marca estos 77 casos con su nivel de confianza **más alto**, porque la regla de confianza mide *cuántas fuentes de fecha coincidieron*, no *qué tan precisa* es la fecha resultante. Un dato equivocado con etiqueta `high` es peor que uno ausente: B-52 y B-53 van a leer una serie mensual como anual y no van a reportar ningún hueco — justamente lo que el plan advierte en B-51 ("una fecha inventada es peor que ninguna"). Regla que deja: cuando un bloque produce un campo nuevo, el criterio de aceptación tiene que incluir una muestra leída contra la fuente, no solo el porcentaje de cobertura.


---

## E-39 · La cifra que cumple el criterio era la que un fallback silencioso podía estar inflando

- **Fecha / bloque:** 2026-09-24 · auditoría de B-51 (APROBADO CON OBSERVACIONES, `465ce4e`)
- **Tipo:** verificación de origen de una métrica / observación de motor
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** B-51 rompió el 99.3% de INE en un solo dataset y lo repartió en 8, con máxima concentración 26.19% (116/443) — criterio cumplido con holgura, y las cifras del parte se reproducen exactas contra `inventory.db`.
- **Qué encontró el Auditor:** `GenericSourceAdapter.classify_dataset()` (`generic_adapter.py:33-34`) tiene un fallback silencioso: lo que no coincide con ninguna regla cae en `dataset_rules[0]`. En el YAML nuevo `dataset_rules[0]` es `cuentas_nacionales_pib` — **el dataset más grande, o sea justamente la cifra que decide si el criterio se cumple**. Un 26.19% construido con filas huérfanas sería un 99.3% disfrazado. Medido fila por fila contra qué patrón concreto coincide cada URL: **0 filas caen al fallback**; las 116 vienen de cuatro carpetas reales del portal (`insumo-producto` 56, `cuentas-economicas` 29, `pib-y-cuentas` 26, `cuentas-consolidadas` 5). La clasificación es genuina. También se verificó D-06 corriendo los 5 casos del test contra el extractor de `7858d1e`: los dos primeros devuelven `None` y los otros tres fallan sus aserciones, así que el test no es tautológico.
- **Cómo se resolvió:** APROBADO CON OBSERVACIONES. O-8 del acta deja el fallback anotado como trampa latente (que devuelva `sin_clasificar` en vez de la primera regla, en bloque de motor propio). La deuda de B-50 bajó de 77 a 3 filas (`Marzo__2026`: el patrón `[-_]?` de `extractor.py:185` admite un separador y ASFI escribe dos) y se abrió O-2: `resource_audit_log` **no tiene columna `method`**, así que el `url_year_fallback` que B-50 pidió no llega a la base que B-53 va a leer.
- **Por qué:** La pregunta que sirvió no fue "¿el número es correcto?" —lo era, reproducido dígito a dígito— sino "¿de dónde sale cada fila que forma el número?". Un default silencioso puesto en el primer lugar de una lista convierte "no supe clasificar" en "clasificado como X" sin producir ningún error, y el X de turno era el que cumplía el criterio. Regla que deja: cuando un bloque cumple su criterio con una métrica agregada, verificar que el agregado no lo produzca la rama por defecto del código que lo calcula — sobre todo si esa rama apunta a la categoría más grande.


---

## E-40 · Densidad temporal baja: la regla que devolvió el bloque habría arruinado cuatro declaraciones correctas

- **Fecha / bloque:** 2026-09-24 · re-auditoría de B-52 (APROBADO CON OBSERVACIONES, `60a84bf`; primera entrega `ea6fea8` DEVUELTA)
- **Tipo:** regla de auditoría que no generaliza / decisión de criterio
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** La primera acta de B-52 devolvió el bloque con una regla implícita: si un dataset declarado como serie tiene densidad temporal baja, la declaración está mal y va a `eventual`. Aplicada a `instituciones_financieras_desarrollo` (ASFI) era correcta —24 filas en 180 meses, 13 de ellas páginas de navegación sin fecha, y los 5 documentos "mensuales" todos del mismo mes— y la re-entrega la corrigió bien, igual que los dos cajones de fallback (ASFI 35/386 filas coinciden con sus propios patrones, BCB 13/95).
- **Qué encontró el Auditor:** Al medir los 18 datasets uno por uno para ver qué más atrapaba la regla, apareció `bcb/deuda_externa`: declarado `semestral`, **3 filas** —una página de navegación, un reglamento de 2022 y un único `DEPEX jun26.pdf`— sobre un lapso de 2022 a 2026. Es exactamente la forma del contraejemplo que el criterio del plan escribe ("3 documentos en 5 años"). Y sin embargo la declaración está bien: el BCB publica DEPEX semestralmente de verdad. Lo que está mal no es la periodicidad, es que el crawler cosechó 1 de ~10 informes. Lo mismo en `reservas_internacionales`, `estabilidad_financiera` y `escala_salarial`. Si el retorno se hubiera extendido "a todas las periodicidades de serie" como pedía su propio C-3, el resultado habrían sido cuatro `eventual` equivocados.
- **Cómo se resolvió:** APROBADO CON OBSERVACIONES, con la distinción escrita en §4 del acta: densidad baja tiene dos causas y hay que separarlas antes de tocar la declaración. **No hay serie** (mayoría sin fecha o páginas de navegación, o coincidencia baja con los propios patrones = cajón de fallback) → `eventual`. **Hay serie mal cosechada** (las filas fechadas son documentos reales de la serie) → se mantiene la periodicidad, y que B-53 reporte el hueco es el comportamiento deseado. Consecuencia: el umbral de densidad **no** se generaliza; lo que sí se generaliza a toda periodicidad de serie es el control de heterogeneidad (≥40% de coincidencia con los patrones del dataset), hoy limitado a `anual`. El alcance de test que queda (5 datasets `trimestral`/`semestral` sin rama de contraste) pasa a B-53 con esa distinción ya decidida.
- **Por qué:** La lección no es sobre periodicidades, es sobre retornos de auditoría. Una devolución que nombra un caso concreto y bien medido tiende a venir con una regla generalizada de propina, y la regla no se verifica con el mismo rigor que el caso: acá el caso estaba impecable y la generalización habría metido cuatro errores nuevos, borrando además la señal de cobertura que el bloque siguiente existe para detectar. Regla que deja: antes de pedir "aplicá esta corrección a todos los casos análogos", medir los casos análogos — un `eventual` de más no produce ningún error visible, solo apaga un hueco que había que ver. Es la misma clase de error tabulada en `CLAUDE.md`, esta vez introducida por el auditor y no por la entrega. Segundo hallazgo del sondeo, este de ejecución: el test devuelto **sí** atrapa el caso por el que se devolvió el bloque, pero eso no se pudo leer del parte —su corrida en rojo pega otro caso, porque `dataset_rules[0]` falla primero y aborta el bucle— y hubo que revertir esa única declaración en un worktree desechable para verlo fallar. Cuando un retorno nombra un caso, la corrida en rojo tiene que aislar ese caso.


---

## E-41 · `rendicion_cuentas` del INE era anual con dos actos, no semestral: 8 huecos fantasma eliminados

- **Fecha / bloque:** 2026-09-24 · B-54 (Ronda 2 de auditoría)
- **Tipo:** decisión de diseño / corrección de periodicidad de dataset
- **Herramienta:** Claude (auditor) + Antigravity
- **Qué ocurrió:** En B-52, `rendicion_cuentas` del INE se declaró `semestral` suponiendo que las audiencias `inicial` y `final` correspondían al primer (S1) y segundo (S2) semestre. Esa declaración provocó que B-53 detectara 8 huecos fantasma `YYYY-S2` (de 2018 a 2025).
- **Qué encontró el Auditor y confirmó el inventario:** En `output/ine/inventory.db` existen 83 registros de `rendicion_cuentas` (83 URLs canónicas distintas, 57 desde 2018). Desde 2013, toda gestión anual tiene documentos `inicial` y `final` bajo la misma carpeta anual (`rendicion-publica-de-cuentas-YYYY`), todos con `period_start = YYYY-01-01`. Para la gestión 2026 (a septiembre), el inventario muestra `inicial=2, final=0`. No se trata de una serie económica semestral, sino de dos actos (apertura y cierre) de la gestión anual obligatoria por normativa de control social y transparencia en Bolivia.
- **Cómo se resolvió:** Conforme a la Decisión 1 de Claude en la Ronda 2 de B-54, se modificó `config/source_ine.yaml:83` pasando `periodicity` de `semestral` a `anual`. Al re-ejecutar `scripts/detectar_huecos.py`, `rendicion_cuentas` pasa de 14 huecos a 0 huecos (`AL_DIA`), los datasets `AL_DIA` suben de 11 (61.1%) a 12 (66.7%) y los datasets `CON_HUECOS` descienden de 6 (33.3%) a 5 (27.8%).
- **Por qué:** Mapear la nomenclatura semántica superficial (`inicial` / `final`) directamente a intervalos temporales artificiales (`S1` / `S2`) inventa huecos donde hay cobertura completa. La estructura real de las publicaciones institucionales debe prevalecer sobre suposiciones nominales.


---

## E-42 · Un `skip` es una subsanación sospechosa por defecto; y el fondo se arregló tres veces mientras la forma reincidía

- **Fecha / bloque:** 2026-09-24 · B-54 (Ronda 3 de auditoría — APROBADO CON OBSERVACIONES, commit `13d6a4d`)
- **Tipo:** lección de auditoría / método de verificación
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** La ronda 2 devolvió B-54 porque un test nuevo (`test_recovery_ladder_real_recoveries_not_in_inventory`) dejaba HEAD en rojo en un checkout limpio: afirmaba `assert db_path.exists()` sobre `output/bcb/inventory.db`, que no está versionado. La subsanación fue reemplazar esa aserción por un `pytest.skip`. Correcto en el resultado —verifiqué con el comando del protocolo que las 4 fallas bajaron a 3 y que las 3 restantes son las preexistentes de `test_reporte_cobertura.py`—, pero un `skip` que tapa la única aserción del test es **indistinguible de haberlo borrado, y no produce ningún error**.
- **Qué hizo el sondeo:** En vez de leer el diff, correr el test en las dos condiciones y meterle un control positivo. Con `output/` presente da `.....` (cinco puntos, ninguna `s`: el cuerpo se ejecuta); en el worktree limpio da `....s` (el guard actúa). Y reproduciendo su consulta con una URL del mismo dataset que **sí** está cosechada (`DEPEX jun26.pdf` → `True`, contra las tres recuperadas → `False`), queda probado que la aserción discrimina y que el test todavía puede fallar por la razón por la que existe. Sin ese control, el skip habría pasado como arreglo sin que nadie supiera si quedaba algo adentro.
- **El segundo hallazgo, no pedido:** el JSON de la corrida trae `elapsed_seconds: 43.64` contra los **169 s** de la ronda 2. O sea que la periodicidad mal declarada de `rendicion_cuentas` (E-41) no solo inventaba 8 huecos: hacía que la escalera gastara un tercio largo de su corrida persiguiéndolos. Cierra con cifra el O-8 de B-53.
- **Por qué:** Dos reglas. La primera: **cuando una corrección hace que algo deje de ejecutarse —un `skip`, un guard, un early-return—, hay que probar que todavía puede ejecutarse y fallar donde corresponde.** Es la misma familia que D-08 (un mock que parece interceptar y no intercepta) y que la lección de la ronda 2 sobre el escalón 1 (un guard puesto en el lugar equivocado que dejó la función incapaz de devolver nada). La segunda es sobre la serie B-52/B-53/B-54 completa: **lo que reincidió no fue el criterio técnico sino la presentación de la evidencia** — hash del commit ausente 3 veces, salida pegada que no corresponde al comando que la encabeza 4 veces (en esta ronda, `5 passed` bajo el título del worktree cuando el real es `4 passed, 1 skipped`, contradicho por el propio parte tres líneas más abajo). El fondo se arregló rápido cada vez. La causa probable es que el parte se escribe después y desde la memoria en vez de desde la terminal; la contramedida acordada es redirigir cada comando a un archivo durante la ejecución y armar el parte pegando esos archivos.



---

## E-43 · La subsanación era correcta; sus tests parcheaban la función que decían verificar

- **Fecha / bloque:** 2026-09-24 · B-54b ronda 2 (APROBADO CON OBSERVACIONES, commit `67456a9`; R1 `664c123` DEVUELTA)
- **Tipo:** lección de auditoría / calidad de la prueba de una subsanación
- **Herramienta:** Claude (auditor) + Antigravity
- **Qué ocurrió:** La R1 devolvió B-54b porque el escalón 5 admitió 4 páginas HTML de navegación del INE como «recuperaciones verificadas». La subsanación agregó cuatro guardarraíles (tipo documental en HEAD, rechazo de `text/html` en la descarga, D-01 con fronteras de palabra más rechazo por bytes mágicos de HTML, y correspondencia con el período) y cinco tests, con su corrida en rojo y en verde pegada en el parte.
- **Qué encontró el sondeo:** El arreglo es genuino y más robusto de lo que el parte reclama —pasé las **mismas 4 URLs** de la R1 por cada compuerta por separado y **las cuatro rechazan las cuatro**, sin depender unas de otras—. Pero dos de los cinco tests nuevos parchean con `patch.object` justamente la función cuyo comportamiento afirman verificar (`_verify_period_correspondence` con `return_value=False`, `_check_head` con `return_value=False`), y un tercero solo ejercita un `set`. Consecuencia: en la corrida en rojo esos tests fallaban **porque el atributo todavía no existía** y `patch.object` levanta `AttributeError`, no porque el defecto estuviera presente. El rojo era real y no probaba nada del defecto. La lógica de años y semestres de H-3 quedó sin ninguna cobertura.
- **El segundo hallazgo, no pedido:** el `166 passed` que el parte pega como verificación contra HEAD limpio no se reproduce — el worktree da `3 failed, 155 passed, 8 skipped`, y las 3 fallas dependen de `output/`, que está gitignoreado. Lo verifiqué también sobre `771fa63`, el último commit aprobado: las mismas tres. O sea que **el comando de `protocolo_equipo.md` §«Verificación contra HEAD limpio» no puede dar verde en este repositorio**, y todo parte que lo copie tiene que pegar 3 fallas o inventarse un verde. Quinta reincidencia del patrón de E-42 (salida pegada que no corresponde al comando que la encabeza), pero esta vez con causa estructural en el protocolo, no solo en cómo se escribe el parte.
- **Por qué:** Un retorno de auditoría que nombra un caso concreto y verificable deja el listón puesto: si el auditor pudo probar el defecto contra las URLs reales, **el test de la subsanación tiene que poder ejercitar la función nueva, no parchearla**. Parchear la función bajo prueba produce un test que pasa siempre después y falla siempre antes —por la razón equivocada— y es indistinguible de uno bueno leyendo el parte. Misma familia que D-08 y que E-42: la prueba parece interceptar el comportamiento y solo intercepta su propia existencia. Corolario para el protocolo: cuando la verificación contra HEAD limpio no puede dar verde por razones de entorno, hay que arreglar el comando —marcar los tests que dependen de datos gitignoreados, con control positivo (E-42)— en vez de dejar que cada parte resuelva la contradicción por su cuenta.


---

## E-44 · Herencia institucional: la generalización de D-01 a citas legales y la necesidad de procedencia de bytes (C-1)

- **Fecha / bloque:** 2026-09-24 · B-55 (Búsqueda de herencia institucional — Decisión D-18)
- **Tipo:** decisión de diseño / generalización de D-01 / verificación probatoria
- **Herramienta:** Claude (auditor) + Antigravity
- **Qué ocurrió:** En B-55 se diseñó e implementó el evaluador de herencia institucional (`InheritanceEvaluator`) para detectar cuándo una serie migró a otra entidad pública (ej. SPVS a ASFI/APS, SBEF a ASFI, SUPTRANS a ATT). El diagnóstico inicial planteó cuatro compuertas, pero admitía que el modelo pudiera sugerir la base legal del traspaso.
- **Qué encontró el Auditor y la verificación empírica:**
  1. *La forma nueva del error de D-01: evidencia inventada, no dominio equivocado.* Hasta B-54b el proyecto verificaba dominios contra contenido. La herencia introduce un segundo objeto verificable —la cita legal— que tiene toda la apariencia de evidencia dura y ninguna de sus propiedades si nadie la descargó. Una cita de decreto inventada por un LLM se lee igual que una cierta, y nadie la abre para comprobarla. La condición C-1 generaliza D-01: no importa qué se afirma, importa de qué bytes descargados y verificables salió (`evidence_url`, `http_status`, `content_sha256`, `fetched_at`, `snippet`, `matched_pattern`).
  2. *Discrepancia documental sin cita verificable:* Dos documentos del repositorio discrepaban sobre la base legal de la herencia SPVS (`DS 29894` en el diagnóstico vs `Ley 365/2013 + DS 0071/2009` en el catálogo maestro). Ninguno traía un snippet verificable de bytes descargados. La compuerta 2 con C-1 exige producir el dato desde descargas reales, no heredarlo de un texto.
  3. *Insumo empírico:* La cola `docs/entregas/cola_herencia_b55.json` no contenía candidatos generados por B-54b. Al correr `scripts/evaluar_herencia.py` sobre los registros de procedencia del catálogo (`output/excel_urls_diagnostic.json`), los 3 candidatos (`SPVS-APS`, `SPVS-ASFI`, `SUPTRANS`) fueron rechazados honestamente: apuntaban a URLs raíz institucionales (HTML de portada) sin binarios documentales (C-4) ni texto de transferencia en el HTML.
- **Cómo se resolvió:** Se formalizó D-18 con cuatro compuertas copulativas estrictas: continuidad temporal como falsador (C-2), respaldo legal con procedencia obligatoria de bytes (C-1), formato documental sobre binarios D-14 (.pdf, .xlsx, .zip) nunca HTML (C-4), e identidad del destino bajo D-01 con descarte de domain parking (C-3). El evaluador genera propuestas en `docs/entregas/propuestas_herencia.json` sin tocar jamás `inventory.db` ni configuraciones (C-5).
- **Por qué:** Automatizar la herencia sin procedencia estricta es repetir el error de D-01 a escala institucional y con apariencia de rigor jurídico. Exigir que cada pieza de evidencia venga de bytes descargados convierte el juicio institucional en una verificación mecánica y deja la decisión final en manos humanas.


---

## E-45 · Una batería de casos negativos no detecta una compuerta que rechaza todo

- **Fecha / bloque:** 2026-09-24 · auditoría de B-55 (`0a2010a`), veredicto DEVUELTO (`docs/auditorias/B-55.md`)
- **Tipo:** método de prueba / control positivo / D-01
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** El acta de diseño de B-55 fijó seis casos de prueba obligatorios, y cinco de los seis eran casos que **deben rechazarse** (N-1 a N-4, más P-1 que solo exige no crashear). Antigravity los implementó, los seis pasaron, y la corrida real sobre el catálogo dio 3 de 3 rechazadas — un resultado que el propio acta había declarado válido de antemano por C-6. Leído así, el bloque cerraba.
- **Qué encontró el sondeo:** Cuatro candidatos escritos contra el código, con el mismo `patch.object` que usan los tests del bloque, mostraron que **las cuatro compuertas no discriminan**. El caso que lo resume: un PDF alojado en `deportes.gob.bo` cuyo cuerpo completo es «sistema de campeonatos deportivos. Referencia historica a la spvs.» sale `PROPUESTA` con las cuatro compuertas en `VERDADERA` y con evidencia acreditada, sha256 incluido, declarando origen SBEF y destino ASFI. La identidad del destino se acredita con `any()` sobre las palabras de más de 3 letras del nombre institucional, así que basta «sistema» para ser ASFI o «seguros» para ser APS; y el respaldo legal se acredita contra una lista global cableada (`\bsbef\b`, `\bspvs\b`, `\bsuptrans\b`), así que una herencia de SBEF queda acreditada por la mención de SPVS. Tres de las cinco condiciones BLOQUEANTE —C-2 invertida, C-3 vacua, C-4 reducida a un chequeo de extensión de archivo— no estaban implementadas como se aprobaron, y **ninguno de los seis tests podía notarlo**.
- **Por qué:** Una batería compuesta casi enteramente de casos negativos es satisfacible por un evaluador que rechace todo, y por lo tanto no distingue un filtro correcto de un filtro roto en la dirección permisiva. El «3 de 3 rechazadas» se leyó como prudencia del evaluador cuando era, en parte, incapacidad de aceptar. Misma familia que el control positivo de E-42 y que el `patch.object` sobre la función bajo prueba de E-43: la prueba parece medir el comportamiento y mide otra cosa. **Regla que queda:** por cada compuerta, además del caso que la ataca por el lado restrictivo, uno que la ataque por el lado permisivo —un candidato que *debería* pasarla y otro apenas fuera de rango que no—. Sin ese par, «cero aceptadas» no es evidencia de rigor. Corolario para las actas de diseño futuras: cuando el acta enumera los casos exigibles, tiene que exigir el par, porque lo que el acta no pide no se escribe.


---

## E-46 · Publicar el sondeo lo convierte en el examen que se estudia

- **Fecha / bloque:** 2026-09-24 · re-entrega de B-55 (`8fb20e0`), veredicto APROBADO CON OBSERVACIONES (`docs/auditorias/B-55.md`)
- **Tipo:** método de auditoría / control positivo
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** El acta de E-45 publicó los cuatro sondeos que devolvieron B-55, con su script reproducible. La re-entrega los incorporó como tests (S1 a S4), los seis controles negativos se vieron fallar neutralizando su guarda, y los cuatro casos pasaron. Auditar con esos mismos casos habría dado verde limpio. Tres casos nuevos, escritos contra el código entregado y no contra la lista de hallazgos, mostraron que una de las condiciones BLOQUEANTE sigue a medias: la compuerta de «identidad estructural» acredita que un documento es la continuación de una serie estadística con la presencia de **una** palabra de un vocabulario financiero genérico (`cartera`, `credito`, `deuda`…), y el diccionario `KNOWN_ORIGIN_SCHEMAS` —que existe para comparar contra el origen— solo se consulta como bandera de «origen conocido». Consecuencia medida: un reglamento jurídico de ASFI que dice explícitamente que no contiene datos sale `PROPUESTA`, y un documento de cartera bancaria sale propuesto como heredero de una serie de flujo de pasajeros de SUPTRANS.
- **Por qué:** Un sondeo publicado deja de medir la capacidad discriminante del código y pasa a medir si el parche cubre su propio caso — es la versión de auditoría del «código escrito contra el test». No es razón para no publicarlo: el sondeo publicado se volvió suite de regresión, que es su mejor destino. La regla que queda es que **el sondeo de cada vuelta se construye contra el código de esa vuelta**, nunca contra los hallazgos de la anterior. Y el corolario de veredicto: la primera vuelta fue DEVUELTO porque un destino institucionalmente equivocado salía aceptado —la falla D-01, la que el proyecto ya cometió cuatro veces—; la segunda cierra con observaciones porque lo que queda ya no produce una identidad equivocada, solo una propuesta débil, y el evaluador propone sin admitir y no escribe en `inventory.db` ni en las configs. El umbral quedó escrito: el día que una corrida real produzca una propuesta, el cotejo de C-4 tiene que ser real antes de que esa propuesta se use.


---

## E-47 · Un cero que esconde la invariante que dice probar

- **Fecha / bloque:** 2026-09-25 · B-56, ronda 1 DEVUELTO (`c7b09b1`), ronda 2 APROBADO CON OBSERVACIONES (`455ee5b`) — `docs/auditorias/B-56.md`
- **Tipo:** lectura de evidencia / rama no ejercida / D-06
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** B-56 asigna a cada dataset uno de cuatro estados de ciclo de vida, con la regla inviolable de que nadie pasa a `HISTORICO` por silencio: hace falta que la escalera de recuperación de B-54 se haya agotado y que quede registrado qué se intentó. El reporte de la primera entrega mostraba `HISTORICO: 0` sobre 21 datasets, y eso se lee como la invariante funcionando. Era lo contrario: `load_recovery_logs()` leía la clave `recovered_periods`, que no existe en ningún artefacto de B-54 —la real es `recoveries`—, así que los 21 registros tenían el log de intentos vacío; y por si eso se arreglaba, la misma función escribía `success: True` fijo, mientras que la condición de agotamiento exige que todos los intentos hayan fallado. Con cualquiera de los dos defectos por separado, **la rama `HISTORICO` era inalcanzable desde datos reales**. El `0` no era el resultado de una evaluación que pudo dar otro número: era el único número posible.
- **Qué lo hizo visible:** contar sobre el artefacto commiteado en vez de leer la columna del reporte — `sum(1 for x in datasets if x['recovery_attempts_log'])` dio `0`. El `try/except` de la función nunca saltaba, porque el JSON parsea perfecto: solo devuelve una lista vacía. Los siete tests del bloque pasaban con la función completamente rota, porque ninguno tocaba el script. En la misma vuelta, `transition_date` resultó ser la fecha de la corrida y no la del cambio de estado: re-correr el script sin tocar nada movía las 21 fechas y ningún estado (`git diff --numstat` → `22 22`).
- **Cómo se resolvió:** la re-entrega lee `recoveries`, deriva `success` de `status == "RECOVERED"`, persiste el estado previo para conservar la fecha, y agrega un test que carga los **JSON reales** de B-54 en vez de un mock. Verificado por efecto: el log de `bcb/deuda_externa` trae sus 3 intentos y la re-corrida mueve 1 sola línea, el `timestamp` de cabecera. Y lo que no se pudo arreglar quedó escalado en el parte en vez de disimulado: B-54/B-54b solo persisten `status: RECOVERED` —lo confirmé, `Counter({'RECOVERED': 3})` en los dos artefactos—, así que `HISTORICO` sigue siendo una rama probada solo en test hasta que la escalera emita los fallos de los escalones 1..4.
- **Por qué:** es la forma más difícil de ver de la clase de error que persigue este proyecto. No hay un artefacto que falte ni un status equivocado: hay **un número correcto por la razón equivocada**, y encima en la dirección segura —archiva de menos, no de más—, que es la que no genera ninguna queja. La regla que queda: **un contador en cero sobre una regla de exclusión no es evidencia de que la regla discrimina, hasta que se muestre que el camino al valor distinto de cero existe y se puede recorrer con los datos que hay.** Es el simétrico de E-45: allá una batería de casos negativos no distinguía un filtro correcto de uno que rechaza todo; acá un agregado en cero no distingue una invariante que se respeta de una rama que nadie puede alcanzar. Corolario para las auditorías: cuando el criterio de aceptación es «X nunca pasa automáticamente», el sondeo tiene que preguntar primero **si X puede pasar**.

---

## E-48 · Una clave de cotejo puede vaciar la categoría que el bloque existe para producir, sin fallar

- **Fecha / bloque:** 2026-09-25 · parada de decisión de diseño de B-57 (`docs/auditorias/B-57_decision_diseno.md`)
- **Tipo:** diseño de clave de cotejo / efecto verificado
- **Herramienta:** Claude (decisión D-19)
- **Qué ocurrió:** El diagnóstico inicial de B-57 proponía emparejar catálogos con prioridad por `content_hash` SHA-256 cuando exista. Como un recurso modificado es, por definición, el mismo recurso con otro hash, esa clave lo parte en dos filas disjuntas —`SOLO_INTERNO` y `SOLO_EXTERNO`— y la categoría `DISCORDANCIA_CONTENIDO` sale vacía en cero. El script corre, escribe su JSON, los totales cuadran, no hay errores y el resultado analítico es falso.
- **Cómo se detectó:** Razonando sobre la semántica estricta de la categoría, no leyendo código: es la misma forma de error que `mailto:` en `discovery.py` (D-06) y que un mock que no intercepta (D-08) —artefacto correcto, efecto nulo, cero mensajes de error—.
- **Cómo se resolvió:** Se formalizó la condición BLOQUEANTE C-1 en D-19: cotejo en 3 pasadas donde la identidad primaria es la URL canónica normalizada. El hash actúa como comparador sobre las URLs emparejadas, y solo opera como clave de rescate en la segunda pasada para detectar `URL_CAMBIADA` entre no emparejados.
- **Por qué:** En sistemas de integración de datos, emparejar por el atributo que se desea comparar destruye la señal de cambio. La identidad del recurso debe descansar en su localizador estable, no en el estado mutable de su contenido.

---

## E-49 · El cuello de botella de la Fase 4 se movió y ningún documento lo había registrado

- **Fecha / bloque:** 2026-09-25 · parada de decisión de diseño de B-57
- **Tipo:** medición empírica vs suposición documental
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** El plan y la §2 del documento de arquitectura repetían que el período estaba vacío en el 97% de BCB y el 99.5% de INE. Medido el 2026-09-25 tras B-50/B-51, la cobertura de período se elevó al 71.2% global (829 de 1.165 filas). En cambio, el hash SHA-256 —que ningún documento señalaba como faltante— solo existía en el 4.9% de las filas (57 de 1.165, todas en ASFI y 0 en BCB/INE), porque los tres YAML llevaban `content_hashing: enabled: false` en contra de D-13.
- **Cómo se detectó:** Al medir directamente sobre `output/{bcb,ine,asfi}/inventory.db` antes de dictaminar la clave de cotejo, en lugar de confiar en las cifras repetidas en los documentos.
- **Cómo se resolvió:** Se estableció la condición C-8: el exportador declara qué filas están verificadas con bytes y cuáles no (`VERIFICADO_CON_HASH` vs `CATALOGADO_SIN_BYTES`), y las dimensiones no medibles por falta de hashes se reportan abiertamente como tales bajo C-2 y C-10.
- **Por qué:** La cifra que un plan repite de memoria es la que nadie vuelve a medir. Los supuestos técnicos deben revalidarse contra las bases vivas en cada hito arquitectónico.

---

## E-50 · Un cruce con 1 coincidencia en 818 gritaba un defecto de clave que nadie escuchó

- **Fecha / bloque:** 2026-09-25 · B-57 (Cruce con el crawler interno — D-19 / C-3)
- **Tipo:** síntoma de clave no validada vs brecha real
- **Herramienta:** Claude (decisión) + Antigravity (análisis forense)
- **Qué ocurrió:** Desde B-45, `docs/diff_brecha_rolando_b45.json` registraba 1 coincidencia entre 818 URLs internas de Rolando y 121 de nuestro crawler en BCB, y la cifra quedó archivada como si fuera una brecha masiva del interno. Una tasa de coincidencia cercana a cero (0.83%) casi nunca significa que dos sistemas sean disjuntos; significa que la clave o el foco de catalogación es divergente.
- **Qué encontró el análisis forense:** Rolando extrajo 810 planillas estadísticas (`.xlsx` y `.ods`) y 1 solo `.pdf`, mientras que nuestro inventario catalogó 111 `.pdf` de publicaciones institucionales y solo 5 `.xlsx`. No era un fallo de scraping, sino una divergencia de dominios temáticos entre los crawlers.
- **Cómo se resolvió:** Se instituyó la condición BLOQUEANTE C-3 con un umbral del 10%: si la coincidencia en un portal queda por debajo del 10% del lado menor, el portal entero se marca `CLAVE_NO_VALIDADA` (938 entidades puestas en cuarentena) y se prohíbe emitir reportes de brecha hasta validar la clave y el alcance.
- **Por qué:** Es la diferencia fundamental entre entregar «al interno le faltan 817 documentos de BCB» (una falsedad que alguien repetirá en una reunión de DataX) y entregar con honestidad técnica «no logramos emparejar las URLs de BCB por divergencia de tipos documentales y cobertura».

---

## E-51 · Una aserción que suma sus propios términos no prueba nada, y un centinela se disfraza de dato ausente

- **Fecha / bloque:** 2026-09-25 · B-57, ronda 1 DEVUELTO, ronda 2 RE-ENTREGA (`docs/auditorias/B-57.md`)
- **Tipo:** invariante tautológica / valores centinela en agregación / auditoría D-06
- **Herramienta:** Claude (auditor) + Antigravity (implementación)
- **Qué ocurrió:** En la primera entrega de B-57 (R1, `7afe87b`), la aserción de totalidad C-10 no calculaba ninguna unión: comparaba `total_classified = sum(len(items) for items in results.values())` contra la suma explícita de las nueve categorías de `results`, que son exactamente las mismas nueve claves (`CATEGORIAS_VALIDAS`). Es decir, `sum(todas)` contra `sum(todas)`: verdadera para cualquier resultado posible, incluido uno que perdiera o duplicara la mitad de las entidades. Lo mismo valía para la aserción de la rama `CLAVE_NO_VALIDADA`. Era una tautología disfrazada de invariante. Al mismo tiempo, el conciliador aceptaba `"No disponible"` o cadenas no canónicas en `period_label` y pretendía derivar períodos de `fecha_actualizacion` (que era la fecha del scraper de Rolando, no la del dato financiero).
- **Cómo se detectó:** Claude auditó la fórmula de la aserción y descubrió que sus dos lados recorrían el mismo diccionario, así que no había cálculo independiente contra el cual contrastar. En los períodos, inspeccionó el artefacto JSON y vio `"No disponible"` categorizado como dato de período y 250 filas clasificadas en `INDETERMINADO_POR_CONFIANZA` cuando el insumo interno no tenía períodos ni niveles de confianza.
- **Cómo se resolvió:** Se reformuló C-10 con cálculo de unión formalmente independiente: `expected_union = len(valid_ext_urls | valid_int_urls) - len(results["URL_CAMBIADA"]) + unkeyed_ext + unkeyed_int`. Se agregó un gancho `_hook_before_assert` y una prueba de mutación con falla inducida (`test_c10_assertion_catches_dropped_entity`) que demuestra que si se sustrae una entidad, la aserción explota con `AssertionError`. Para los períodos, se prohibió terminantemente deducir cobertura de la fecha de rastreo, se filtró estrictamente con `is_valid_period_label()`, y las 323 coincidencias pasaron limpias a `INDETERMINADO_POR_DATO_AUSENTE` con declaración explícita de categorías inalcanzables.
- **Por qué:** Una prueba que no puede fallar ante un defecto es peor que ninguna prueba, porque otorga falsa seguridad matemática. Y en reconciliación de catálogos, atribuir significado analítico a metadatos de recolección (como la fecha de corrida del bot) corrompe la semántica temporal del dominio financiero.
- **Corrección posterior (auditoría R2, O-11):** la versión original de esta entrada describía el defecto de R1 con identificadores (`union_expected`, `expected_entities`) que **no existen en `7afe87b`** —`git grep` sobre ese commit no los encuentra—. El defecto real era peor que el relatado: no había ningún cálculo de unión, ni siquiera uno mal hecho. La corrección aplicada seguía siendo la correcta, pero un razonamiento escrito sobre código inventado no le sirve a quien lea este registro en seis meses. Reescrito arriba contra el código real del commit.

---

## E-52 · Un contador que nunca corre publica su valor por defecto, y encima arrastra el del portal anterior

- **Fecha / bloque:** 2026-09-25 · B-57, ronda 2 (hallazgo H-5 de `docs/auditorias/B-57.md`)
- **Tipo:** cero que parece un resultado / estado compartido entre iteraciones
- **Herramienta:** Claude (auditor)
- **Qué ocurrió:** La observación O-9 de R1 pedía medir cuántos registros se colapsan al compartir URL canónica. La subsanación agregó `duplicate_urls_ext/int`, pero los calcula **después** de la compuerta C-3, dentro de la rama `VALIDADA`; la rama `CLAVE_NO_VALIDADA` retorna antes. Y `conciliar_crawler_interno.py:136` crea **una sola** instancia de `InternalReconciler` fuera del bucle de portales, con los contadores inicializados sólo en `__init__`. Resultado: un portal en cuarentena publica lo que dejó el portal anterior.
- **Cómo se detectó:** No leyendo el código sino invirtiendo el orden de los portales. Con el orden de producción (BCB primero) BCB informa `Ext=0, Int=0`, que además coincide con el valor verdadero —121 URLs únicas sobre 121 filas—, así que nada se ve. Corriendo `asfi` antes que `bcb`, BCB informa `dup_ext=5 dup_int=11`, que son de ASFI.
- **Cómo se resolvió:** Anotado, no corregido en B-57: el número publicado hoy coincide con el real y ninguna cifra del entregable depende de él. La corrección —resetear los contadores al entrar en `reconcile()` en vez de en `__init__`, y calcularlos antes de la compuerta C-3— queda para B-58.
- **Por qué:** Es exactamente la clase de error que encabeza `CLAUDE.md` —verificar el artefacto y no el efecto— y llegó **dentro de la corrección de una observación que pedía medir**. Un contador que devuelve su valor por defecto es indistinguible de una medición que dio cero; lo único que los separa es correr el caso donde deberían diferir. Vale como recordatorio de que un estado guardado en `self` y reusado a través de un bucle de portales es, por construcción, un canal por el que un portal contamina al siguiente.


