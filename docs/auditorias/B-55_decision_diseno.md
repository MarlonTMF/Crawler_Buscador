# Acta de decisión de diseño — B-55 · Búsqueda de herencia institucional

- **Decisor:** Claude (auditor y decisor técnico del bucle)
- **Fecha:** 2026-09-24
- **Documento evaluado:** `docs/diagnosticos/B-55_diagnostico_herencia.md` (Antigravity, 128 líneas)
- **Parada:** de diseño obligatoria (`docs/plan_bloques_fase4.md`, B-55)
- **Veredicto:** **APROBADO CON CONDICIONES** — se puede implementar, con las
  siete condiciones C-1 a C-7 de la sección 3 incorporadas antes de escribir
  código ejecutor.

> El diagnóstico acierta en lo esencial: la herencia es el caso en que D-01
> puede romperse a escala, y por eso ninguna se admite sola. Las cuatro
> compuertas son el marco correcto y se aprueban.
>
> **Lo que falta es de dónde sale la evidencia.** Las tres compuertas de
> contenido (continuidad, base legal, estructura) están definidas por lo que
> hay que probar, no por quién tiene derecho a probarlo. Tal como están, un
> agente que devuelva «DS 29894, Disposición Transitoria Primera» las satisface
> las tres sin que nadie descargue un byte. Eso es exactamente D-01 trasladado
> del dominio a la cita legal: antes aceptábamos un dominio porque respondía
> 200; ahora aceptaríamos una herencia porque un modelo escribió un número de
> decreto. **La condición C-1 cierra eso y no es negociable.**
>
> El propio diagnóstico ya muestra el síntoma: cita `DS 29894 (2009)` como causa
> de extinción de la SPVS, mientras que el catálogo de este repositorio
> (`output/excel_urls_diagnostic.json`, registro `SPVS-APS`) dice
> `Ley 365 (23/04/2013) y DS 0071 (09/04/2009)`. Dos documentos del proyecto
> discrepan hoy sobre la base legal de la misma herencia, y **ninguno de los dos
> trae una cita verificable**. No dictamino cuál tiene razón —no me consta— y
> ese es el punto: la compuerta 2 tiene que producir el dato, no heredarlo.
>
> La segunda corrección de fondo es de dirección: la compuerta 2 prueba que el
> destino menciona al **predecesor**. No prueba que el destino **sea quien dice
> ser**. Una página de parking que copie texto institucional pasa esa compuerta.
> Falta verificar la identidad del destino bajo D-01 (condición C-3).

---

## 1. Qué revisé

1. `docs/diagnosticos/B-55_diagnostico_herencia.md` completo.
2. `docs/plan_bloques_fase4.md` — alcance, criterio de aceptación de B-55 y su
   encadenamiento con B-54b (escalón 5) y B-56 (estado `MIGRADO`).
3. `docs/decisiones.md` — D-01, D-02, D-14, D-17 y el formato canónico de las
   decisiones, para dictaminar la redacción de D-18.
4. `src/crawler/core/recovery_ladder.py` — lo que B-54b **ya implementó** de
   herencia: `inheritance_candidates`, `save_inheritance_candidates()`
   (líneas 600-610), el desvío por dominio no autorizado en
   `_try_rung_5_agent_gemini()` (líneas 677-700), `_verify_institution_content()`
   (515-538) y `_verify_period_correspondence()` (540-598).
5. `output/excel_urls_diagnostic.json` — los registros `SPVS-APS`, `SPVS-ASFI` y
   `SUPTRANS`, que son herencias ya catalogadas y verificadas por contenido.
6. `docs/entregas/recuperaciones_b54b.json` y `docs/auditorias/B-54B.md`.

### Sondeo: ¿con qué insumo real arranca B-55?

Con ninguno. El diagnóstico habla de evaluar candidatos de herencia, pero la
cola que los alimentaría está vacía:

```
$ ls -la docs/entregas/ | grep -i "heren\|b54b"
-rw-r--r-- 1 ELITEBOOK 197121  1987 Sep 24 23:11 recuperaciones_b54b.json
        (no existe docs/entregas/cola_herencia_b55.json)

$ head docs/entregas/recuperaciones_b54b.json
  "total_recovered": 3,
  "gemini_calls_count": 10,
  "gemini_budget_exhausted": true,
  "inheritance_candidates_count": 0,
```

`save_inheritance_candidates()` solo escribe si hay candidatos
(`recovery_ladder.py:825`), y la corrida real de B-54b produjo **0**. Esto tiene
una consecuencia de diseño, no solo de dato: **B-55 no puede depender de que el
agente le traiga el caso.** El caso de prueba sale del catálogo, que ya tiene
tres herencias reales documentadas (sección 4).

**No verifiqué por red ninguna de las afirmaciones empíricas del diagnóstico**
(el sondeo con `curl` no fue autorizado en esta sesión). Todo lo que sigue sobre
Caso A y Caso B es dictamen de diseño, no confirmación de sus cifras; la
verificación es trabajo de la implementación y es condición de cierre (C-6).

---

## 2. Respuesta a las tres preguntas de la sección 6 del diagnóstico

| Pregunta | Dictamen |
|---|---|
| 1. ¿Son admisibles los 4 criterios de evidencia? | **Sí, con enmiendas.** Compuerta 2 se promueve a condición necesaria con regla de procedencia (C-1). Compuerta 1 se reformula como falsador, no como empalme exigido (C-2). Compuerta 3 se acota a recursos documentales bajo D-14 (C-4). Compuerta 4 se extiende a tres artefactos más y a la identidad del destino (C-3, C-5). |
| 2. ¿Se ratifica la redacción de D-18? | **No la del diagnóstico; sí la de la sección 5 de esta acta.** El borrador omite cuatro de las siete secciones que exige el formato del proyecto y no fija la procedencia de la evidencia. La redacción de la sección 5 se copia **verbatim** a `docs/decisiones.md` en el commit de B-55. |
| 3. ¿Se aprueba implementar `InheritanceEvaluator`? | **Sí**, como módulo nuevo que propone y nunca admite, con las condiciones C-1 a C-7 y el alcance de la sección 6. |

---

## 3. Condiciones de aprobación (C-1 a C-7)

### C-1 · Procedencia de la evidencia — el agente propone el candidato, nunca la evidencia · BLOQUEANTE

Ninguna de las tres evidencias de contenido puede originarse en la salida de un
modelo, en una investigación externa, ni en el conocimiento del asistente que
redacta. Cada evidencia se acredita con bytes efectivamente descargados:

- `evidence_url` — la URL de la que salió, en dominio oficial del destino (o de
  la gaceta oficial, para la cita legal).
- `http_status`, `content_sha256`, `fetched_at`.
- `snippet` — el texto literal encontrado, con su desplazamiento en el cuerpo.
- `matched_pattern` — la expresión que lo encontró.

Si un campo de evidencia no puede llenar esos cinco datos, **vale como ausente**,
no como «evidencia débil». Un LLM puede sugerir *dónde mirar*; lo que valida es
el `grep` sobre la respuesta real, igual que en D-01.

**Por qué es bloqueante.** Es el único punto del diseño donde el error de D-01
puede reaparecer sin dejar rastro. Un número de decreto inventado se lee igual
que uno cierto, y a diferencia de un dominio equivocado, nadie lo va a abrir
para comprobarlo.

### C-2 · La compuerta 1 se reformula: falsador temporal, no empalme exigido · BLOQUEANTE

El diagnóstico exige que el último período del origen empalme con el primero del
destino. **Se rechaza esa formulación por dos razones concretas.**

Primera, el dato no existe. Medido el 2026-09-23 y escrito en
`docs/plan_bloques_fase4.md`: BCB tiene período resuelto en el 3% de sus filas e
INE en el 0,5%. Una compuerta cuyo insumo es `unknown` en el 97% de los casos no
decide: sortea.

Segunda, y más grave: una compuerta que **debe** pasar para que la propuesta
exista crea presión para producir el período que falta. Ya vimos esa forma exacta
de error en la R1 de B-54b, cuando cuatro páginas de navegación del INE entraron
como recuperaciones verificadas. No se repite.

Formulación aprobada:

- **Falsa (rechaza)** si origen y destino publican datos oficiales contradictorios
  para el mismo corte sin explicación, o si el destino no cubre el período que se
  está buscando.
- **Verdadera (corrobora)** si hay empalme o solapamiento explicable, evaluada
  **solo** sobre documentos con `period_start`/`published_at` de confianza
  `medium` o superior.
- **`INDETERMINADO`** si no hay período confiable en alguno de los dos lados. No
  rechaza ni aprueba: marca la propuesta como `EVIDENCIA_INCOMPLETA` y la
  sostiene la compuerta 2.

### C-3 · Verificar también la identidad del destino, no solo la mención del predecesor · BLOQUEANTE

La compuerta 2 prueba que el destino habla del predecesor. Falta probar que el
destino es la institución sucesora. Son cosas distintas y `sicsantacruz.com` es
la prueba: un dominio de parking responde 200 y puede contener cualquier texto.

Se exige una verificación D-01 del destino con palabras clave de la **entidad
sucesora**, más el descarte de las marcas de parking ya conocidas en el proyecto.
`_verify_institution_content()` (`recovery_ladder.py:515`) no sirve tal cual:
está indexada por el portal de origen (`bcb`, `ine`, `asfi`) y una herencia es,
por definición, un destino que no está en ese diccionario. Hay que pasarle las
palabras clave del destino, no las del portal.

### C-4 · La compuerta 3 se evalúa sobre documentos D-14, nunca sobre HTML · BLOQUEANTE

La identidad estructural se compara entre recursos documentales bajo D-14
(extensión o MIME de `.pdf`, `.xlsx`, `.xls`, `.csv`, `.zip`), leyendo campos
—cartera, mora, activo, período—; nunca entre páginas de aterrizaje.

Si el lado origen ya no es descargable —que es el caso normal, por eso hay
herencia—, se compara contra lo que ya tenemos de esa serie en `inventory.db`. Si
no tenemos nada del origen, la compuerta queda `INDETERMINADO` (mismo tratamiento
que C-2), no se da por buena.

**No se acepta la periodicidad como evidencia estructural.** Casi toda serie
institucional boliviana es mensual o anual; coincidir en eso no distingue nada.

### C-5 · La compuerta 4 protege tres artefactos más, y registra los rechazos

La regla inmutable del diagnóstico nombra `inventory.db` y `source_<portal>.yaml`.
Se extiende a:

- `config/moved_urls.json` — **el más importante de los tres**: es literalmente
  el archivo donde un cambio de dominio se materializa. Una herencia que escriba
  ahí sin persona de por medio anula D-01 entera.
- `output/excel_urls_diagnostic.json` — el catálogo de Track A.
- `output/url_resolution_log.json` — se escribe, pero solo como registro de
  intento, nunca como resolución aceptada.

Y las propuestas **rechazadas se persisten** con su motivo y su fecha. Sin eso, el
mismo candidato se vuelve a proponer en cada corrida y vuelve a gastar cuota —el
error de D-08, que ya se cometió una vez.

### C-6 · Al menos una propuesta con las tres evidencias descargadas, o el reporte honesto de por qué no

El criterio de aceptación del plan («al menos un caso propuesto con su evidencia
completa — aceptado o rechazado») se interpreta así: **completa significa con los
cinco campos de C-1 llenos y reproducibles**, no con las tres casillas marcadas.

Si al correrlo resulta que ninguna de las tres herencias del catálogo puede
acreditar la cita legal con un `snippet` descargado, **ese es un resultado válido
y se reporta con la medición**: significa que la compuerta 2 no es automatizable
hoy y que la herencia queda como flujo asistido, no automático. Lo que no se
acepta es llenar `evidencia_legal` con una cita que nadie descargó.

### C-7 · Presupuesto y respeto al portal

El evaluador comparte el tope de llamadas al agente por corrida con la escalera
(`max_gemini_calls`, hoy 10 y ya agotado en la corrida de B-54b) y lo registra en
su parte. Las descargas de evidencia acatan el `rate_limit_per_second` de la
fuente (D-17.4).

---

## 4. Casos concretos de prueba

Dictamen sobre los dos casos del diagnóstico: **Caso A se acepta como candidato
pero no como evidencia ya reunida** —sus cifras («SBEF concluye en febrero de
2009; ASFI arranca en marzo de 2009») no están verificadas contra ninguna fuente
descargada, y CLAUDE.md prohíbe escribir en el repositorio una cifra no
verificada—. **Caso B se acepta, pero es insuficiente como control negativo**:
BCB→BCP falla las tres compuertas a la vez, así que no prueba que las compuertas
discriminen; solo prueba que rechazan lo obvio. Lo que hay que atajar es el casi
acierto.

Batería aprobada, y las seis son exigibles:

| # | Caso | Insumo | Resultado esperado | Qué compuerta lo tiene que atajar |
|---|---|---|---|---|
| **P-1** | **SPVS → ASFI (valores) y SPVS → APS (pensiones/seguros)** | Registros `SPVS-ASFI` y `SPVS-APS` de `output/excel_urls_diagnostic.json` | `ACEPTADA` o `EVIDENCIA_INCOMPLETA`, con los `snippet` que se hayan podido descargar | Caso positivo real y ya catalogado: el evaluador tiene que **re-derivarlo desde evidencia**, no leerlo del catálogo. De paso resuelve la discrepancia `DS 29894` vs `Ley 365 / DS 0071` con una cita. |
| **P-2** | **SBEF → ASFI** (Caso A del diagnóstico) | Serie de boletines | `ACEPTADA` solo si la cita legal y la mención «Boletines Históricos SBEF» salen de bytes descargados de `asfi.gob.bo`; si no, `EVIDENCIA_INCOMPLETA` | Compuertas 1 a 3 con C-1. Las fechas de febrero/marzo de 2009 **no entran al repositorio hasta medirlas**. |
| **N-1** | BCB deuda externa → BCP (Caso B) | Candidato sintético | `RECHAZADA` | Las tres. Control trivial, se conserva como piso. |
| **N-2** | **Casi acierto: página HTML de `asfi.gob.bo` que sí menciona «ex-Superintendencia de Bancos»** (noticia o página institucional) | Candidato real del propio dominio | `RECHAZADA` | Compuerta 3 bajo C-4 / D-14. **Es la forma exacta del defecto que devolvió B-54b en R1** (páginas de navegación admitidas como documentos). Obligatorio. |
| **N-3** | **Cita legal que solo existe en la respuesta del modelo** y no aparece en el cuerpo descargado del destino | Gemini mockeado devolviendo «DS 29894, Disposición Transitoria Primera» | `RECHAZADA` por procedencia | C-1. Es el test que prueba que C-1 es código y no una frase del acta. |
| **N-4** | Destino que responde 200 con las palabras clave dentro de una página de parking | HTML de parking (el patrón `<!-- Send the parked domain's origin as the referrer -->` ya registrado en el proyecto) | `RECHAZADA` | C-3. Es el caso `sicsantacruz.com`. |

**Disciplina de test (D-06, no negociable):** las seis se ven fallar antes del
arreglo y la corrida en rojo se pega en `docs/entregas/B-55.md`. Un test de
regresión no vale hasta verlo fallar.

---

## 5. Redacción ratificada de D-18

Se copia **verbatim** a `docs/decisiones.md`, a continuación de D-17, dentro del
commit de B-55. Reemplaza al borrador de la sección 5 del diagnóstico, que omite
las secciones *Alternativas descartadas*, *Consecuencia*, *Umbral que la
reabriría* y *Verificado el* que exige el formato del proyecto.

```markdown
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
```

---

## 6. Alcance aprobado de la implementación

**Sí:**
- Módulo nuevo `src/crawler/core/inheritance_evaluator.py` con
  `InheritanceEvaluator`: lee candidatos, descarga evidencia, evalúa las cuatro
  compuertas y escribe `docs/entregas/propuestas_herencia.json`.
- Script de línea de comandos, en la línea de `scripts/recuperar_periodos.py`.
- Tests en `tests/test_inheritance_evaluator.py`, con los seis casos de la
  sección 4.
- Lectura de `docs/entregas/cola_herencia_b55.json` **si existe** — hoy no
  existe, y el evaluador tiene que funcionar igual con los registros del catálogo
  como entrada.

**No, sin plan aprobado aparte (CLAUDE.md):**
- Tocar `orchestrator.py` o `discovery.py`.
- Modificar `_try_rung_5_agent_gemini()` más allá de pasarle el destino de la
  cola. El escalón 5 quedó auditado en B-54b y no se reabre acá.
- Ampliar el alcance más allá de BCB, INE y ASFI. D-18 es política del proyecto
  entero; la implementación y las pruebas de B-55 se corren sobre los tres
  portales de la Fase 4 y nada más.

**Nombres de artefactos.** Se conservan los dos y no se unifican:
`cola_herencia_b55.json` es la **entrada** (candidatos crudos del escalón 5,
ya implementada en B-54b) y `propuestas_herencia.json` es la **salida**
(propuestas evaluadas con evidencia y dictamen). Renombrar la existente
rompería `save_inheritance_candidates()` sin ganar nada.

---

## 7. Qué se le devuelve a Antigravity

El bloque **no está devuelto** —era una parada de diseño, no una entrega—. Para
implementarlo:

1. Incorporar C-1 a C-7. Las cinco marcadas BLOQUEANTE son condición de
   aceptación del bloque, no sugerencias.
2. Copiar D-18 de la sección 5 **sin cambios** a `docs/decisiones.md`. Si algo de
   esa redacción no se puede sostener al implementarla, se escala; no se ajusta
   el texto para que encaje con el código.
3. Las seis pruebas de la sección 4, vistas fallar primero, con la corrida en
   rojo en el parte.
4. En `docs/entregas/B-55.md`: cuántas propuestas se evaluaron, cuántas quedaron
   `EVIDENCIA_INCOMPLETA` y por qué compuerta, y el `snippet` con su URL de cada
   evidencia acreditada. **Cero propuestas aceptadas es un resultado válido y
   reportable**; una propuesta aceptada con evidencia que nadie descargó, no.
5. Actualizar `docs/plan_bloques_fase4.md` (columna **Real** de B-55) y anotar en
   `AI_LOG.md` el aprendizaje de la sección 8.

---

## 8. Anotaciones para `AI_LOG.md`

1. **La forma nueva del error de D-01: evidencia inventada, no dominio
   equivocado.** Hasta acá el proyecto verificaba *dominios* contra contenido.
   La herencia introduce un segundo objeto verificable —la cita legal— que tiene
   toda la apariencia de evidencia dura y ninguna de sus propiedades si nadie la
   descargó. La regla de procedencia (C-1) es la generalización de D-01: no
   importa qué se afirma, importa de qué bytes salió.
2. **Dos documentos del repositorio discrepan sobre la base legal de la herencia
   SPVS** —`DS 29894` en el diagnóstico de B-55, `Ley 365/2013 + DS 0071/2009` en
   el catálogo— y ninguno trae cita verificable. Se detectó leyendo los dos
   juntos, no auditando ninguno por separado. Queda como tarea de P-1.
3. **La cola que iba a alimentar B-55 está vacía** (`inheritance_candidates_count:
   0` en la corrida real de B-54b). Un bloque planificado como consumidor de la
   salida de otro se quedó sin insumo y nadie lo notó hasta abrir el JSON. Vale
   como recordatorio de la regla general del proyecto: verificar el efecto, no el
   artefacto.
