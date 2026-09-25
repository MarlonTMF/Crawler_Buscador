# Acta de decisión de diseño — B-57 · Cruce con el crawler interno

- **Decisor:** Claude (auditor y decisor técnico del bucle)
- **Fecha:** 2026-09-25
- **Documentos evaluados:**
  - `docs/diagnosticos/B-57_diagnostico_cruce_interno.md` (Antigravity, 89 líneas)
  - `docs/arquitectura_integracion.md` §5 (levantado el 2026-09-23)
- **Parada:** de decisión obligatoria (`docs/plan_bloques_fase4.md`, B-57, parada 2)
- **Veredicto:** **APROBADO CON CONDICIONES** — se ratifica la **Opción A** y se
  puede implementar con las diez condiciones C-1 a C-10 de la sección 4
  incorporadas antes de escribir el conciliador. Cinco son **BLOQUEANTES**.

> El diagnóstico acierta en lo grande: la Opción A es la correcta, la
> conciliación no hay que diseñarla porque ya existe del otro lado, y la
> taxonomía de cuatro categorías cubre la pregunta de la reunión.
>
> **Lo que está mal es la clave de cotejo, y está mal de dos formas distintas.**
>
> Primera, es imposible hoy. El diagnóstico propone «prioridad por `content_hash`
> SHA-256 cuando exista». Medido hoy sobre las tres bases: **57 de 1.165 filas
> tienen `content_sha256`** —0 en BCB, 0 en INE, 57 en ASFI—, porque los tres
> YAML llevan `content_hashing: enabled: false`
> (`config/source_bcb.yaml:49`, `source_ine.yaml:41`, `source_asfi.yaml:88`),
> en contra de lo que D-13 declaró obligatorio. Una clave cuyo insumo falta en el
> 95% de los casos no decide: sortea. Es la misma objeción que la condición C-2
> de B-55, y por la misma razón.
>
> Segunda, y más grave: **aunque el hash existiera, ponerlo primero rompe la
> categoría que el bloque existe para producir.** Un recurso `MODIFICADO` es, por
> definición, el mismo recurso con hash distinto. Si el cotejo empareja por hash,
> ese recurso no empareja con nada: sale del diff partido en dos filas
> —`SOLO_INTERNO` y `SOLO_EXTERNO`— y la categoría `DISCORDANCIA` queda vacía sin
> que nada falle ni avise. Es exactamente la clase de error que el CLAUDE.md
> describe: no produce ningún error visible y da un resultado plausible.
>
> La tercera observación de fondo no está en el diagnóstico: **el cruce ya se
> corrió una vez y su resultado es sospechoso.** `docs/diff_brecha_rolando_b45.json`
> dice que en BCB, de 818 URLs del interno y 121 nuestras, **coinciden 1**. Un
> cruce donde casi nada empareja casi nunca significa que los dos sistemas son
> disjuntos; significa que la clave está mal. Eso se diagnostica antes de
> publicar 817 `SOLO_INTERNO`, no después (C-3).

---

## 1. Qué revisé, y con qué no pude contar

### Revisado

1. `docs/diagnosticos/B-57_diagnostico_cruce_interno.md` completo.
2. `docs/arquitectura_integracion.md` §§1-8, con foco en §5 (dónde vive cada
   capacidad y las tres opciones de puente) y §7 (correspondencia de campos).
3. `docs/plan_bloques_fase4.md` — alcance, criterio de aceptación y
   encadenamiento de B-57 con B-58.
4. `docs/decisiones.md` — D-01, D-13, D-14, D-16, D-17, D-18 y el formato
   canónico de las decisiones, para dictaminar la redacción de D-19.
5. `scripts/diff_brecha_rolando.py` completo y `tests/test_diff_brecha_rolando.py`
   — el comparador contra el volcado interno **que ya existe** desde B-41/B-45.
6. `src/crawler/core/canonicalizer.py:38-53` — `generate_resource_key()`.
7. `src/crawler/core/exporter.py` — los tres formatos de mapa ya emitidos.
8. `dashboard_server.py:835` — el puerto del dashboard.
9. Las tres bases reales: `output/{bcb,ine,asfi}/inventory.db`.
10. `config/source_{bcb,ine,asfi}.yaml` — bloque `content_hashing`.

### Lo que no pude verificar en esta sesión

**No tuve acceso a `../Prospector-Externo` ni a `../prospector_interno`**: el
entorno de esta sesión está limitado a `crawler_finrural` y los intentos de
listar los repositorios hermanos fueron rechazados. En consecuencia:

- Todo lo que esta acta afirma sobre `DuckDBDiffEngine`, el esquema de
  `DiscoveredResourceItem`, los endpoints de la Catalog API y el puerto 8000 del
  externo **está tomado de `docs/arquitectura_integracion.md` tal como se
  escribió el 2026-09-23, no reverificado hoy contra el código de esos repos.**
- Tampoco pude confirmar que exista el volcado interno
  `Elecciones De Crawler por URL/Rolando/extracted/output` que
  `diff_brecha_rolando.py` consume, ni los archivos `Crawler_BCB/crawler_data.sqlite`
  y `Crawler_BCB/mapa_global_bcb.json` que el diagnóstico menciona en su §1.4.

Esto no bloquea la decisión de arquitectura —que se toma sobre acoplamiento y
riesgo, no sobre esas cifras— pero sí convierte en **condición de cierre** que la
implementación declare y evidencie con qué insumo interno corrió (C-2).

---

## 2. Mediciones propias, hechas hoy

Todas sobre `output/<portal>/inventory.db`, 2026-09-25. Son el insumo real del
exportador de la Opción A y ninguna de ellas aparece en el diagnóstico.

| Medición | BCB | INE | ASFI | Total |
|---|---:|---:|---:|---:|
| Filas en `resource_audit_log` | 121 | 443 | 601 | **1.165** |
| Estado `PROCESADO_EXITOSAMENTE` | 121 | 443 | 601 | 1.165 |
| Con `content_sha256` | **0** | **0** | 57 | **57 (4,9%)** |
| Con `file_size_bytes > 0` | **0** | **0** | 582 | **582 (50,0%)** |
| Con `period_start` resuelto | 39 | 309 | 481 | **829 (71,2%)** |

**Confianza de la fecha** (`date_confidence_score`):

| | `high` | `medium` | `low` | `unknown` |
|---|---:|---:|---:|---:|
| BCB | 11 | 28 | 64 | 18 |
| INE | 151 | 158 | 2 | 132 |
| ASFI | 480 | 1 | 102 | 18 |

**Forma del período en las 829 filas fechadas** (clasificando el par
`period_start`/`period_end`):

| Forma | Filas | `period_label` canónico |
|---|---:|---|
| Un día (`period_start == period_end`) | **58** | `YYYY-MM-DD` — **no está en el diagnóstico** |
| Un mes exacto | 266 | `YYYY-MM` |
| Un trimestre exacto | 25 | `YYYY-Qn` |
| Un semestre exacto | **0** | `YYYY-Sn` (definido, nunca ejercitado) |
| Un año exacto | 453 | `YYYY` |
| Rango multianual (ej. `2021-01-01`→`2025-12-31`) | **27** | **no tiene etiqueta única** |

### Las tres cosas que estas mediciones cambian del diseño

1. **El período ya no es el cuello de botella que decía el plan.** El plan de
   fase habla del 3% en BCB y 0,5% en INE; después de B-50/B-51 la cobertura real
   es 71,2% global (BCB 32,2%, INE 69,8%, ASFI 80,0%). El campo bisagra del
   contrato **sí tiene dato** para la mayoría de las filas.
2. **El hash sí es el cuello de botella**, y es de configuración, no de motor:
   los tres YAML tienen `content_hashing` apagado, lo que D-13.4 solo permite
   como «excepción justificada por escrito» y en estos tres casos no está
   justificada en ninguna parte. Además, bajo D-13.2, BCB e INE no tienen **ni una
   sola fila** que cuente como documento verificado (`file_size_bytes > 0`).
3. **El diagnóstico no cubre dos de las seis formas de período que existen en la
   base**: el día (58 filas) y el rango multianual (27 filas). Sin regla para
   ellas, el exportador o inventa una etiqueta o las deja fuera en silencio.

---

## 3. Dictamen sobre las cuatro propuestas de la §5 del diagnóstico

| # | Propuesta | Dictamen |
|---|---|---|
| 1 | Ratificar **Opción A** como mecanismo oficial de cruce | **Sí, ratificada**, con el destino corregido: la Opción A produce un **archivo en el formato del contrato**, y ese archivo lo consume `Prospector-Externo` como publicador. Ver la discrepancia de dirección abajo. |
| 2 | Clave de cotejo: `content_hash` primero, `(url_canonica, period_label)` como fallback | **Rechazada tal como está.** Se invierte: la clave de emparejamiento es la identidad (URL canónica); el hash es **comparador**, no clave, y habilita una segunda pasada para `URL_CAMBIADA`. Condición C-1, bloqueante. |
| 3 | Crear `scripts/conciliar_crawler_interno.py` y `src/crawler/core/internal_reconciler.py` integrando `DuckDBDiffEngine` | **Sí a los dos módulos; no a «integrando `DuckDBDiffEngine`».** No se importa código de un repositorio hermano ni se agrega DuckDB como dependencia para cruzar 1.165 filas. Condiciones C-6 y C-7. |
| 4 | Emitir `docs/entregas/conciliacion_interno_externo.json` sobre BCB, INE y ASFI | **Sí**, con el desglose y las declaraciones de no-medible de C-4, C-5 y C-10. |

### La discrepancia de dirección entre los dos documentos, resuelta

Los dos documentos llaman «Opción A» a dos cosas distintas:

- `docs/arquitectura_integracion.md` §5: `crawler_finrural` → **`Prospector-Externo`**
  («exportador», el diagrama dice `F -->|A · exportador| E`).
- `docs/diagnosticos/B-57_diagnostico_cruce_interno.md` §2: `crawler_finrural` →
  **`prospector_interno`** (el diagrama dice `F -->|Opción A| I`, y la fila de la
  tabla remata «`DuckDBDiffEngine` o el script conciliador lo ingiere
  directamente»).

No es un detalle de dibujo: son dos contratos con dos dueños distintos. **Se
ratifica la versión de §5** y se fija así:

1. El artefacto que produce la Opción A es **un archivo en el formato
   `ResourceCandidate`**, cuyo consumidor oficial es `Prospector-Externo`, que es
   quien sirve la Catalog API. `crawler_finrural` no le habla al interno: no es su
   proveedor y no debe convertirse en uno.
2. Para **medir B-57** —que es lo que el bloque tiene que entregar— nuestro propio
   conciliador lee ese mismo archivo y lo cruza contra el volcado del catálogo
   interno disponible localmente. Eso es un **instrumento de medición de brecha**,
   no un canal de integración, y el reporte tiene que decirlo con esas palabras.
3. `crawler_finrural` **no escribe nada** dentro de `../Prospector-Externo` ni de
   `../prospector_interno`. Son repositorios de otros equipos, clonados para
   leerlos (C-9).

### Por qué se rechazan B y C, para que queden cerradas

- **B (portar el motor)** — Fuera de alcance por costo y riesgo, como dicen los dos
  documentos. Se agrega la razón que ninguno menciona: portar 31 módulos borraría
  la trazabilidad de las 19 decisiones que este repositorio acumuló, que es el
  activo real del prototipo. Queda abierta como camino futuro; la Opción A no la
  cierra.
- **C (exponer una Catalog API propia)** — Se rechaza por una razón más fuerte que
  la colisión de puertos: **dos sistemas diciendo ser «el prospector externo» es
  un problema de identidad, no de red.** El interno resolvería por configuración a
  cuál le cree, y esa configuración vive en otro repositorio. La colisión con el
  dashboard (`dashboard_server.py:835`, `127.0.0.1:8000`) existe y está bien
  señalada, pero es el síntoma menor.

---

## 4. Condiciones de aprobación (C-1 a C-10)

### C-1 · La clave de emparejamiento es la identidad, no el hash · BLOQUEANTE

El cotejo se hace en tres pasadas, en este orden, y cada recurso se resuelve en
la primera que lo empareja:

1. **Identidad primaria: URL canónica normalizada.** Una sola función de
   normalización, compartida con `diff_brecha_rolando.py` y con
   `Canonicalizer.canonicalize()` (C-7).
2. **Comparación de contenido sobre los emparejados.** Con las dos URLs ya
   emparejadas, se comparan `content_hash` y `period_label`. Aquí —y solo aquí—
   nace `DISCORDANCIA`.
3. **Segunda pasada por hash, solo entre los no emparejados.** Mismo hash y URL
   distinta ⇒ `URL_CAMBIADA`, que es la categoría que el interno ya modela
   (`arquitectura_integracion.md` §2) y que la reunión pidió explícitamente.

**`resource_key` no se usa como clave de cruce, nunca.**
`Canonicalizer.generate_resource_key()` (`canonicalizer.py:38-53`) compone
`source_id:dataset_id:period_token:file_type` **y cae a un fallback basado en el
nombre del archivo cuando no hay `period_end`**. Dos consecuencias: (a) depende de
nuestro `dataset_id`, que es una invención de este repositorio y no existe del
otro lado; (b) **la clave de una fila cambia cuando su período se resuelve**, así
que el mismo recurso aparecería como nuevo entre dos corridas. La §7 del documento
de arquitectura afirma que `resource_id → resource_key` es «directo (mismo
formato)»; **esa afirmación no está verificada y esta acta no la avala**.

**Por qué es bloqueante.** Con el hash como clave, `DISCORDANCIA` sale vacía y el
reporte igual se ve bien. Es la forma exacta del error más caro del proyecto:
artefacto correcto, efecto nulo, cero mensajes de error.

### C-2 · Declarar y evidenciar el insumo interno antes de cruzar · BLOQUEANTE

B-55 se planificó como consumidor de una cola que estaba vacía y nadie lo notó
hasta abrir el JSON. No se repite. Antes de la primera corrida, el parte declara,
por cada uno de los tres portales:

- Qué archivo o base concreta es el lado interno, con ruta y fecha de
  modificación.
- Cuántos registros trae.
- **Una matriz de disponibilidad de campos medida, no supuesta**: de esos
  registros, cuántos traen URL, cuántos hash, cuántos período.

Esto importa porque el único insumo interno que este repositorio tiene cableado
hoy —el volcado que lee `diff_brecha_rolando.py:73`— trae `url_descarga`,
`tipo_archivo` y `descripcion`, y **ni hash ni período**
(`tests/test_diff_brecha_rolando.py:25-38`). Si el insumo que se use resulta ser
ese, entonces `DISCORDANCIA_PERIODO` y `DISCORDANCIA_CONTENIDO` son **no
medibles**, y el reporte lo dice con el número de filas afectadas. Lo que no se
acepta es rellenar esas categorías por inferencia, ni dejarlas en cero como si se
hubieran evaluado.

### C-3 · Un cruce donde casi nada coincide es un defecto de clave hasta que se pruebe lo contrario · BLOQUEANTE

`docs/diff_brecha_rolando_b45.json` mide, en BCB: 818 URLs del interno, 121
nuestras, **1 común**. En ASFI: 2.428 / 596 / 223 comunes. El caso de BCB no es
un resultado, es un síntoma.

Antes de publicar ninguna cifra de brecha, la implementación tiene que resolver
esa tasa de emparejamiento y dejarlo escrito: **si tras normalizar la coincidencia
en un portal queda por debajo del 10% del lado menor, el cruce de ese portal se
declara `CLAVE_NO_VALIDADA` y no se reporta como brecha.** Se investiga, con
ejemplos concretos pegados en el parte, si la causa es `http`/`https`, `www.`,
mayúsculas, `%20` contra espacio, barra final, o parámetros de cache-busting
(`?x16877`, ya conocidos en `canonicalizer.py`).

**Por qué es bloqueante.** Es la diferencia entre entregar «al interno le faltan
817 documentos de BCB» y entregar «no logramos emparejar las URLs de BCB». La
primera es una cifra falsa que alguien va a repetir en una reunión.

### C-4 · Formato canónico de `period_label`: completo, sin centinelas y validado · BLOQUEANTE

Se ratifican las cuatro formas del diagnóstico y se agregan las dos que faltan,
medidas hoy en la base:

| Granularidad | Formato | Filas medidas |
|---|---|---:|
| Diaria | `YYYY-MM-DD` | 58 |
| Mensual | `YYYY-MM` | 266 |
| Trimestral | `YYYY-Q1`..`YYYY-Q4` | 25 |
| Semestral | `YYYY-S1` / `YYYY-S2` | 0 |
| Anual | `YYYY` | 453 |
| Rango multianual | **sin etiqueta** (campo ausente) | 27 |
| Sin período resuelto | **sin etiqueta** (campo ausente) | 336 |

Tres reglas, y las tres son verificables por test:

1. **Se emite etiqueta solo si el par `period_start`/`period_end` coincide
   exactamente con un cubo canónico.** Un rango `2021-01-01`→`2025-12-31` no es
   «2021»: es un documento que cubre cinco años, y etiquetarlo con el primero
   fabrica un dato. Si no hay cubo exacto, el campo se omite y la razón se
   registra (`RANGO_MULTIANUAL`, `SIN_PERIODO`) **en el sidecar, no en el campo
   del contrato**.
2. **Prohibido el valor centinela.** Ni `"SIN_PERIODO"`, ni `"unknown"`, ni cadena
   vacía dentro de `period_label`: el campo se omite o va `null`. Un centinela
   viaja por el contrato como si fuera un período y del otro lado nadie sabe que
   no lo es. El diagnóstico lo deja a elección («`None` o `SIN_PERIODO`») y esa
   elección se cierra acá: **`null`**.
3. **Un único validador.** Una expresión regular y una función que traduce
   `(period_start, period_end)` → etiqueta, con test propio por cada una de las
   siete filas de la tabla, incluidas las dos que devuelven `null`.

### C-5 · La confianza viaja con la etiqueta, y la etiqueta floja no genera discordancias · BLOQUEANTE

`date_confidence_score` no tiene destino en el contrato
(`arquitectura_integracion.md` §7). Hasta que el externo lo adopte:

- El exportador emite el `period_label` **y** su confianza en el sidecar de
  nuestra propia salida, no dentro del objeto del contrato.
- **Una `DISCORDANCIA_PERIODO` solo se declara si los dos lados tienen período
  con confianza `medium` o superior.** Si alguno es `low` o `unknown`, la fila cae
  en `INDETERMINADO_POR_CONFIANZA`.

La razón es aritmética: 453 de las 829 filas fechadas tienen forma anual y el
método dominante es `url_year_fallback`, que es adivinar el año por la ruta. En
BCB, 82 de 121 filas son `low` o `unknown`. Sin este filtro, el reporte se llena
de discordancias de período que son artefactos de nuestra propia inferencia, y es
la misma trampa que la condición C-2 de B-55: una compuerta alimentada con datos
inciertos no discrimina, decora.

### C-6 · Sin dependencias nuevas y sin importar código de los repos hermanos

- **No se agrega DuckDB.** No está en las dependencias del proyecto y el
  problema es un join de 1.165 filas contra unos pocos miles: un `dict` y dos
  `set` de la biblioteca estándar, como ya hace `diff_brecha_rolando.py`.
  «Conciliación vectorizada» a esta escala es complejidad sin contraparte.
- **No se importa `DuckDBDiffEngine`.** Vive en `prospector_interno`, que es un
  clon para leer, no un paquete instalado. Un `import` que atraviesa repositorios
  rompe la suite en cualquier máquina donde el clon no esté al lado, y hace que
  nuestros tests dependan del árbol de trabajo de otro equipo.
- Lo que sí se hace: **replicar la taxonomía** del interno (`CONFIRMED`, `NEW`,
  `MODIFIED`, `URL_CHANGED`) para que los nombres coincidan, documentando la
  correspondencia en el reporte.

### C-7 · Una sola normalización de URL, compartida

Hoy conviven dos: `normalizar_url_comparacion()`
(`diff_brecha_rolando.py:121-132`) y `Canonicalizer.canonicalize()`
(`canonicalizer.py:20-36`), que no hacen lo mismo —la primera no toca el
cache-busting, la segunda sí—. El conciliador **no escribe una tercera**: usa la
del `Canonicalizer`, y si eso cambia las cifras de `diff_brecha_rolando.py`, se
reporta el cambio en lugar de mantener dos verdades. Dos normalizaciones
distintas significan que la misma URL empareja o no según qué script la mire.

### C-8 · El exportador declara qué está verificado y qué no

Bajo D-13.2, un documento cuenta cuando tiene `file_size_bytes > 0` y
`content_sha256`. Hoy eso se cumple en 57 filas de 1.165. Por lo tanto:

- Cada objeto exportado lleva un estado de verificación explícito
  (`VERIFICADO_CON_HASH` / `CATALOGADO_SIN_BYTES`) y los contadores del reporte
  van desglosados por ese estado.
- **1.108 filas sin hash no se presentan como recursos verificados** en un
  artefacto con formato de contrato. Publicarlas sin marca es exactamente lo que
  D-13 se escribió para impedir.
- Se registra como hallazgo que los tres YAML llevan `content_hashing:
  enabled: false` sin la justificación escrita que D-13.4 exige. Y no es solo la
  justificación que falta: **D-13.3 declara que «todas las fuentes activas se
  actualizan con `content_hashing: enabled: true`»**, y BCB, INE y ASFI —los tres
  portales que B-57 tiene que cruzar— están en `false`. La decisión se escribió el
  2026-09-20 y su punto 3 nunca se ejecutó sobre estos tres. **Encenderlo y
  re-descargar 1.165 documentos no es trabajo de B-57** —son horas de red y
  cambia las tres bases—: se deja propuesto para B-58 o un bloque propio, con la
  medición de lo que costaría.

### C-9 · Aislamiento de los repositorios hermanos y del puerto

- Cero escrituras en `../Prospector-Externo` y `../prospector_interno`. Solo
  lectura, y las rutas llegan por parámetro de línea de comandos, nunca
  hardcodeadas.
- **B-57 no levanta ningún servidor y no usa ningún puerto.** La Opción A es por
  lote; la colisión del 8000 que señala §5 queda como deuda del día en que se
  integre de verdad, no de este bloque.

### C-10 · La exhaustividad se prueba con una aserción, no con una frase

El criterio del plan —«ninguna diferencia queda sin clasificar»— se implementa
como invariante en el código: **la suma de las filas de todas las categorías es
igual al tamaño de la unión de claves de los dos lados**, verificada con `assert`
en cada corrida y con un test que la ve fallar. El diagnóstico lo promete en su
§4 («Garantía del criterio»); una garantía que no es código no es una garantía.

Categorías admitidas, y son cerradas:

| Categoría | Significado | Equivalente en el interno |
|---|---|---|
| `CONFIRMADO` | Empareja por URL y coincide en todo lo comparable | `CONFIRMED` |
| `SOLO_EXTERNO` | Lo tenemos nosotros, no el interno | `NEW` |
| `SOLO_INTERNO` | Lo tiene el interno, no nosotros | (no existe allá: es la brecha) |
| `DISCORDANCIA_PERIODO` | Empareja por URL, `period_label` distinto, ambos lados con confianza ≥ `medium` | — |
| `DISCORDANCIA_CONTENIDO` | Empareja por URL, hash distinto | `MODIFIED` |
| `URL_CAMBIADA` | Mismo hash, URL distinta | `URL_CHANGED` |
| `INDETERMINADO_POR_DATO_AUSENTE` | Empareja, pero un lado no tiene el campo | — |
| `INDETERMINADO_POR_CONFIANZA` | Empareja, período distinto, confianza insuficiente (C-5) | — |
| `CLAVE_NO_VALIDADA` | Portal entero con tasa de emparejamiento bajo el umbral (C-3) | — |

Las tres últimas **son clasificaciones honestas, no un cajón de sastre**: cada
una se cuenta y se explica en el reporte. El criterio de aceptación del plan se
lee satisfecho cuando toda diferencia cae en una categoría nombrada, y las tres
categorías de negocio que pidió la reunión (`SOLO_INTERNO`, `SOLO_EXTERNO`,
`DISCORDANCIA_PERIODO`) se reportan por separado de las de indeterminación.

---

## 5. Batería de pruebas exigible

Las nueve son condición de aceptación. **Disciplina D-06: se ven fallar antes del
arreglo y la corrida en rojo se pega en `docs/entregas/B-57.md`.**

| # | Caso | Insumo | Resultado esperado | Qué atrapa |
|---|---|---|---|---|
| **P-1** | Misma URL, mismo hash, mismo período en los dos lados | Par sintético | `CONFIRMADO` | Piso. |
| **P-2** | URL solo en el interno | Caso real de `diff_brecha_rolando_b45.json` (`asfi.gob.bo/node/498`) | `SOLO_INTERNO` | La categoría que es la brecha. |
| **P-3** | URL solo nuestra | Fila real de `output/asfi/inventory.db` | `SOLO_EXTERNO` | — |
| **P-4** | Misma URL, `period_label` distinto, ambos `high` | Par sintético | `DISCORDANCIA_PERIODO` | — |
| **N-1** | **Misma URL, hash distinto** | Par sintético | `DISCORDANCIA_CONTENIDO` — **una sola fila**, nunca `SOLO_INTERNO` + `SOLO_EXTERNO` | **C-1.** Es el test que prueba que la clave no es el hash. Obligatorio. |
| **N-2** | Misma URL, período distinto, un lado `url_year_fallback` con confianza `low` | Fila real de BCB (64 filas `low`) | `INDETERMINADO_POR_CONFIANZA`, no discordancia | C-5: no fabricar discordancias con datos inciertos. |
| **N-3** | Mismo hash, URL distinta | Par sobre las 57 filas de ASFI que sí tienen hash | `URL_CAMBIADA` | La segunda pasada de C-1. |
| **N-4** | `period_start=2021-01-01`, `period_end=2025-12-31` | **Fila real de `output/ine/inventory.db`** (27 filas así) | `period_label` ausente, razón `RANGO_MULTIANUAL`. **Nunca `"2021"`** | C-4.1: no inventar granularidad. |
| **N-5** | Lado interno sin campo de hash en ningún registro | Volcado tipo Rolando (`url_descarga` solamente) | Todas las filas emparejadas caen en `INDETERMINADO_POR_DATO_AUSENTE` en la dimensión de contenido; **cero** `DISCORDANCIA_CONTENIDO`; la no-medibilidad queda declarada | C-2: el hueco se reporta, no se rellena. |
| **N-6** | Totalidad: entrada con URL vacía, con `null` y duplicada | Sintético | La aserción de C-10 se cumple; ninguna fila se pierde en silencio | C-10. |

---

## 6. Alcance aprobado de la implementación

**Sí:**

- `src/crawler/core/internal_reconciler.py` — el motor de cotejo de tres pasadas
  (C-1), sin dependencias nuevas.
- `scripts/conciliar_crawler_interno.py` — línea de comandos, en la línea de
  `scripts/recuperar_periodos.py` y `scripts/detectar_huecos.py`, con las rutas
  del lado interno por parámetro.
- Extensión de `src/crawler/core/exporter.py` con un método que emite el formato
  `ResourceCandidate` (el mapeo de §7 más `period_label` de C-4 y el estado de
  verificación de C-8). **Método nuevo, sin tocar los tres existentes**, que
  alimentan el dashboard y las auditorías previas.
- El traductor `(period_start, period_end, periodicity)` → `period_label`, con su
  validador y sus siete tests (C-4).
- `docs/entregas/conciliacion_interno_externo.json` y `docs/entregas/B-57.md`.
- `tests/test_internal_reconciler.py` con los nueve casos de la sección 5.

**No, sin plan aprobado aparte (CLAUDE.md):**

- Tocar `orchestrator.py` o `discovery.py`.
- Encender `content_hashing` en los tres YAML y re-correr los portales (C-8).
- Levantar cualquier servidor HTTP, o mover el puerto del dashboard.
- Escribir una sola línea dentro de `../Prospector-Externo` o
  `../prospector_interno`.
- Ampliar el cruce más allá de BCB, INE y ASFI.

---

## 7. Qué se le devuelve a Antigravity

El bloque **no está devuelto** —era una parada de decisión, no una entrega—.
Para implementarlo:

1. Incorporar C-1 a C-10. Las cinco BLOQUEANTES (C-1, C-2, C-3, C-4, C-5) son
   condición de aceptación, no sugerencias.
2. Copiar D-19 de la sección 8 **sin cambios** a `docs/decisiones.md`. Si algo de
   esa redacción no se sostiene al implementarla, se escala; no se ajusta el texto
   para que encaje con el código.
3. Las nueve pruebas de la sección 5, vistas fallar primero, con la corrida en
   rojo en el parte.
4. En `docs/entregas/B-57.md`: la declaración de insumo interno de C-2 con su
   matriz de campos, la tasa de emparejamiento por portal de C-3, el conteo por
   categoría de C-10 y la lista explícita de lo que **no** se pudo medir.
   **Que `DISCORDANCIA_CONTENIDO` salga en cero porque no tenemos hashes es un
   resultado válido y reportable**; que salga en cero sin decir por qué, no.
5. Actualizar la columna **Real** de B-57 en `docs/plan_bloques_fase4.md` y anotar
   en `AI_LOG.md` los tres aprendizajes de la sección 9.

---

## 8. Redacción ratificada de D-19

Se copia **verbatim** a `docs/decisiones.md`, a continuación de D-18, dentro del
commit de B-57. Reemplaza al borrador de la §5 del diagnóstico, que omite las
secciones *Alternativas descartadas*, *Razón*, *Consecuencia*, *Umbral que la
reabriría* y *Verificado el* que exige el formato del proyecto, y cuya clave de
cotejo se rechaza por C-1.

```markdown
## D-19 · El puente al prospector externo es un exportador al contrato (Opción A), y el cruce empareja por identidad con el hash como comparador

**Contexto.** `docs/arquitectura_integracion.md` estableció el 2026-09-23 que son
tres sistemas y no dos: `crawler_finrural` es el motor y el laboratorio,
`Prospector-Externo` es el prospector entregado a DataX y el que sirve la Catalog
API, y `prospector_interno` es la plataforma de ingesta que concilia con
`DuckDBDiffEngine`. Entre el primero y el segundo no hay canal: todo lo que la
Fase 4 construyó acá —fechas B-50/B-51, periodicidad B-52, huecos B-53,
recuperación B-54/B-54b, herencia B-55, ciclo de vida B-56— no llega a producción
por sí solo. B-57 exige elegir cómo se cierra ese puente y con qué clave se cruzan
los dos catálogos. Medido el 2026-09-25 sobre las tres bases (1.165 filas): el
período está resuelto en el 71,2%, pero `content_sha256` existe en 57 filas
(4,9%) y `file_size_bytes > 0` en 582, porque los tres YAML llevan
`content_hashing: enabled: false` sin la justificación escrita que D-13.4 exige.

**Alternativas descartadas.**
1. *Portar las 31 capacidades del motor a la arquitectura hexagonal de
   `Prospector-Externo` (Opción B).* Descartada por costo y riesgo de regresión
   fuera de alcance de la Fase 4, y porque borraría la trazabilidad de las
   decisiones D-01 a D-18, que es el activo real del prototipo. No queda cerrada
   como camino futuro: la Opción A no la impide.
2. *Levantar en `crawler_finrural` una Catalog API propia para que el interno nos
   consuma por REST (Opción C).* Descartada, y no principalmente por la colisión
   de puertos con `dashboard_server.py` (127.0.0.1:8000): dos sistemas que dicen
   ser «el prospector externo» es un problema de identidad, y cuál de los dos
   resulta autoritativo terminaría decidido por una variable de entorno en un
   repositorio ajeno.
3. *Emparejar los catálogos con `content_hash` como clave primaria y
   `(url_canonica, period_label)` como respaldo.* Descartada por dos razones
   independientes. Es imposible hoy: el hash falta en el 95% de nuestras filas, y
   una clave cuyo insumo no existe no decide, sortea. Y es contraproducente aunque
   existiera: un recurso modificado es el mismo recurso con hash distinto, así que
   emparejar por hash lo parte en dos filas —`SOLO_INTERNO` y `SOLO_EXTERNO`— y
   vacía la categoría de discordancia sin que nada falle ni avise.
4. *Usar `resource_key` como clave de cruce.* Descartada: `generate_resource_key()`
   compone `source_id:dataset_id:period_token:file_type` con un `dataset_id` que
   es una invención de este repositorio, y **cambia de valor cuando el período de
   una fila se resuelve**, de modo que el mismo recurso aparecería como nuevo
   entre dos corridas.
5. *Incorporar DuckDB e importar `DuckDBDiffEngine` del clon de
   `prospector_interno`.* Descartada: un join de 1.165 filas no justifica una
   dependencia nueva, y un `import` que atraviesa repositorios hace que la suite
   de este proyecto dependa del árbol de trabajo de otro equipo.

**Decisión.**
1. **Opción A, con dueño y dirección explícitos.** El puente es un **exportador a
   formato de contrato**: `crawler_finrural` emite desde `inventory.db` un archivo
   con el esquema `ResourceCandidate` (`resource_key`, `url`, `source_id`,
   `title`, `file_extension`, `content_type`, `content_length_bytes`,
   `period_label`, `content_hash`). Su consumidor oficial es `Prospector-Externo`,
   que es quien sirve la Catalog API. `crawler_finrural` **no es proveedor del
   prospector interno** y no se convierte en uno.
2. **El cruce que B-57 produce es un instrumento de medición de brecha, no un
   canal de integración**, y el reporte lo declara con esas palabras.
3. **Aislamiento de los repositorios hermanos.** `crawler_finrural` no escribe
   nunca dentro de `Prospector-Externo` ni de `prospector_interno`; los lee, con
   las rutas recibidas por parámetro. Tampoco importa su código ni levanta
   servidores o puertos para este cruce.
4. **Clave de cotejo en tres pasadas, en este orden:** (a) identidad por URL
   canónica normalizada, con **una sola** función de normalización compartida en
   todo el repositorio; (b) sobre los emparejados, comparación de `content_hash` y
   `period_label` —el hash es comparador, no clave—; (c) entre los no emparejados,
   segunda pasada por hash idéntico para detectar `URL_CAMBIADA`.
5. **Formato canónico de `period_label`:** `YYYY-MM-DD` (diaria), `YYYY-MM`
   (mensual), `YYYY-Qn` (trimestral), `YYYY-Sn` (semestral), `YYYY` (anual). Se
   emite **solo** si el par `period_start`/`period_end` coincide exactamente con un
   cubo canónico; un rango multianual o un período sin resolver **omite el campo**.
   **Prohibido todo valor centinela** (`SIN_PERIODO`, `unknown`, cadena vacía): el
   campo va ausente o `null`, porque un centinela viaja por el contrato con
   apariencia de período.
6. **La confianza acompaña a la etiqueta y la etiqueta floja no genera
   discordancias.** Mientras el contrato no adopte `date_confidence_score`, la
   confianza viaja en la salida propia y no dentro del objeto del contrato. Una
   `DISCORDANCIA_PERIODO` solo se declara si **ambos** lados tienen período con
   confianza `medium` o superior; si no, la fila es `INDETERMINADO_POR_CONFIANZA`.
7. **Clasificación total, probada por aserción.** La suma de las filas de todas
   las categorías es igual al tamaño de la unión de claves de los dos lados, y eso
   se verifica con una aserción en cada corrida y un test que la ve fallar. Las
   categorías son cerradas: `CONFIRMADO`, `SOLO_EXTERNO`, `SOLO_INTERNO`,
   `DISCORDANCIA_PERIODO`, `DISCORDANCIA_CONTENIDO`, `URL_CAMBIADA`,
   `INDETERMINADO_POR_DATO_AUSENTE`, `INDETERMINADO_POR_CONFIANZA` y
   `CLAVE_NO_VALIDADA`.
8. **Umbral de validez de la clave.** Si tras normalizar, la coincidencia en un
   portal queda por debajo del 10% del lado menor, ese portal se marca
   `CLAVE_NO_VALIDADA` y **no se reporta su brecha**: se investiga la
   normalización primero. Medido el 2026-09-25 en
   `docs/diff_brecha_rolando_b45.json`, BCB coincide en 1 de 121 filas contra 818
   del lado interno, y eso es un defecto de clave hasta que se demuestre lo
   contrario.
9. **Nada se exporta como verificado sin bytes.** Cada objeto exportado declara su
   estado de verificación (`VERIFICADO_CON_HASH` o `CATALOGADO_SIN_BYTES`) y los
   conteos van desglosados por ese estado. Publicar sin marca filas sin hash en un
   artefacto con formato de contrato es precisamente lo que D-13 prohíbe.
10. **Los huecos se declaran, no se rellenan.** Si el lado interno no trae hash o
    no trae período, las categorías que dependen de ese campo se reportan como no
    medibles, con el número de filas afectadas. Un cero explicado es un resultado;
    un cero sin explicación es un reporte falso.

**Razón.** Las dos mitades de esta decisión responden al mismo error, que es el
que más ha costado en este proyecto: verificar el artefacto en lugar del efecto.
La Opción A lo evita en la arquitectura, porque un archivo en disco se puede abrir
y contar, mientras que un servicio que responde 200 no prueba que nadie lo
consuma. La clave por identidad lo evita en el dato: con el hash como clave, el
diff corre, escribe su JSON y deja `DISCORDANCIA` en cero —el artefacto perfecto
y el efecto nulo, sin un solo mensaje de error—. Y el umbral del punto 8 existe
porque la cifra más peligrosa de esta fase no es la que falta: es «al interno le
faltan 817 documentos de BCB», que suena a hallazgo y puede ser nuestra
normalización de URLs.

**Consecuencia.** Conviven dos formatos en disco por portal —el mapa propio y el
del contrato— y eso es deliberado: el primero alimenta el dashboard y las
auditorías, el segundo es lo único que cruza la frontera. El cruce queda por lote
y reproducible, sin red ni puertos. El costo asumido es que el puente no está
integrado en producción: alguien tiene que llevar el archivo al externo, y hasta
que `content_hashing` se encienda en los tres portales, la dimensión de contenido
del cruce es estructuralmente no medible en BCB e INE.

**Umbral que la reabriría.** La Opción B se reconsidera si DataX adopta el motor
como el prospector externo oficial. La Opción C, solo si el interno acepta más de
un proveedor de catálogo con precedencia explícita. Los puntos 4, 5.3 (prohibición
de centinelas), 7 y 9 no se reabren: son D-13 y la regla del efecto verificado
aplicadas al contrato de integración.

**Verificado el.** 2026-09-25, parada de decisión de B-57 sobre el diagnóstico de
Antigravity y la §5 del documento de arquitectura, decidido por Claude Opus 5
para aprobación de Marlon. Las cifras de 1.165 filas, 57 hashes, 582 filas con
bytes, 71,2% de período y la distribución de formas de período se midieron ese día
contra `output/{bcb,ine,asfi}/inventory.db`. **Las afirmaciones sobre
`DuckDBDiffEngine`, el esquema de `DiscoveredResourceItem` y el puerto 8000 del
externo provienen de `docs/arquitectura_integracion.md` (2026-09-23) y no se
reverificaron en esta sesión**, que no tuvo acceso a los repositorios hermanos.
```

---

## 9. Anotaciones para `AI_LOG.md`

1. **Una clave de cotejo puede vaciar la categoría que el bloque existe para
   producir, sin fallar.** El diagnóstico proponía emparejar por `content_hash`.
   Como un recurso modificado es el mismo recurso con otro hash, esa clave lo
   parte en `SOLO_INTERNO` + `SOLO_EXTERNO` y `DISCORDANCIA` sale en cero. El
   script corre, escribe su JSON, los totales cuadran y el resultado es falso. Se
   detectó razonando sobre la definición de la categoría, no leyendo código: es la
   misma forma de error que `mailto:` en `discovery.py` (D-06) y que un mock que
   no intercepta (D-08) —artefacto correcto, efecto nulo, cero mensajes—.
2. **El cuello de botella de la Fase 4 se movió y ningún documento lo había
   registrado.** El plan y la §2 del documento de arquitectura dicen que el
   período está vacío en el 97% de BCB y el 99,5% de INE. Medido hoy, tras
   B-50/B-51, la cobertura es del 71,2% global. En cambio el hash, que ningún
   documento señalaba, está en el 4,9%, porque los tres YAML llevan
   `content_hashing: enabled: false` en contra de D-13. Se encontró al medir para
   dictaminar la clave de cotejo, no auditando los YAML: **la cifra que un plan
   repite es la que nadie vuelve a medir.**
3. **El cruce ya se había corrido y su resultado gritaba un defecto de clave que
   nadie escuchó.** `diff_brecha_rolando_b45.json` registra 1 coincidencia entre
   818 URLs internas y 121 nuestras en BCB, y el número quedó ahí desde B-45 como
   si fuera una brecha. Una tasa de emparejamiento cercana a cero casi nunca
   significa que dos sistemas sean disjuntos; significa que la clave está mal. De
   ahí el umbral del 10% y la categoría `CLAVE_NO_VALIDADA`: un cruce tiene que
   poder decir «no pude emparejar» en lugar de emitir una brecha inventada.
4. **Dos documentos del repositorio llamaban «Opción A» a dos puentes distintos**
   —`arquitectura_integracion.md` §5 apunta a `Prospector-Externo`, el diagnóstico
   de B-57 apunta a `prospector_interno`— y ambos la recomendaban. Se detectó
   leyendo los dos juntos, igual que la discrepancia legal de SPVS en B-55.
   Empieza a ser un patrón: **las contradicciones de este proyecto no aparecen
   dentro de un documento, aparecen entre dos.**
