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
