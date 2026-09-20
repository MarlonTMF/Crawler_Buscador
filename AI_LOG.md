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




