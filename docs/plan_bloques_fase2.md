# Plan de bloques — Fase 2: superar el benchmark y cobertura casi total

Continuación de `docs/plan_bloques.md` (bloques B-01 a B-27, cerrados). Este
documento cubre **B-28 a B-40**. Las convenciones de bloque, commit y
criterio de aceptación son las de aquel archivo y no se repiten acá.

Aprobado por Marlon el 2026-09-19. Vista de aprobación:
`https://claude.ai/artifact/QEeKa3XnZpCENiz3Zghzij`

---

## Por qué existe esta fase

`docs/comparativa_vs_benchmark.md` midió el resultado del proyecto contra los
tres crawlers del benchmark. Superamos a Rolando en 12 de 22 portales
comunes, pero él sigue arriba en el total (5.403 contra 1.864 en esos
portales). El objetivo de esta fase no es empatar: es **más documentos por
portal y documentos en casi todas las fuentes que responden**.

### Objetivos medibles

| # | Objetivo | Hoy | Meta |
|---|---|---:|---:|
| 1 | Documentos totales | 2.357 | **> 6.000** |
| 2 | Fuentes con al menos un documento | 26 | **≥ 60** de 64 accesibles |
| 3 | Portales donde igualamos o superamos a Rolando | 12 de 22 | **20 de 22** |
| 4 | Errores de recurso | 0 | **0** (no negociable) |

Referencia: Rolando obtuvo 5.902 documentos sobre 52 fuentes, de los cuales
1.893 salían de descomprimir ZIP.

---

## Las siete palancas (todas ya implementadas, ninguna en uso pleno)

Verificado el 2026-09-19 sobre los 28 YAML de `config/`:

```
use_sitemaps                 activada en  2 de 28
use_wayback                  activada en  1 de 28
use_search_dorking           activada en  0 de 28
use_subdomain_enumeration    activada en  1 de 28
use_playwright               activada en  0 de 28
use_async_fetcher            activada en  1 de 28
```

| # | Palanca | Estado | Retorno estimado |
|---|---|---|---|
| 1 | Profundidad de rastreo | 6 portales en `max_depth: 0` | ≈ +3.500 docs |
| 2 | Fuentes sin corrida | 29 responden 200 y nunca se crawlearon | ≈ +1.500 docs |
| 3 | Wayback | 1 de 28 | alto en portales con serie histórica |
| 4 | Sitemaps | 2 de 28 | alto y barato |
| 5 | Headless | 0 de 28, pese a B-13 | desbloquea BCP y BCRP |
| 6 | Extracción de ZIP | implementada, sin evidencia de disparo real | hasta +1.800 docs |
| 7 | API y formularios | `api_detector.py` y `form_automator.py` fuera del pipeline | desbloquea SICSANTACRUZ, SICOES, INE |

**Las estimaciones de documentos son estimaciones, no mediciones.** Salen de
comparar con lo que Rolando obtuvo en cada portal. Si una palanca rinde
menos, el número que va al informe es el medido.

---

## Etapa F — Cerrar la brecha conocida

Tres bloques, 3 h 20 estimadas. Cambios de configuración sobre fuentes que
ya funcionan: la mejor relación esfuerzo/resultado del plan.

### B-28 · Calibrar los 6 portales en profundidad 0 — Antigravity — 90 min

**Objetivo.** ASFI y ADA concentran el 97% de la brecha con Rolando y siguen
leyendo solo las páginas semilla.

**Entradas.** `config/source_{asfi,ada,aps,dgac,ine,seprec}.yaml`, hoy todos
en `max_depth: 0` con `max_pages` entre 5 y 10.

**Pasos.**
1. Explorar cada sitio y elegir profundidad y páginas **por portal**, no un
   número común. Punto de partida: `max_depth: 2`, `max_pages: 150`.
2. Correr cada uno aislado y contar documentos sobre `inventory.db`.
3. Donde el descubrimiento traiga ruido de navegación, la respuesta es
   `excluded_path_keywords`, **no bajar la profundidad**. INE ya mostró ese
   patrón en B-14: a profundidad 1 descubría 1.643 candidatos.

**Criterio de aceptación.** ASFI ≥ 1.200 documentos y ADA ≥ 500, con 0
errores. Es la mitad de lo que logró Rolando en cada uno. Si no se llega ni a
eso, la causa no era la profundidad: **reportarlo en el parte en vez de
seguir subiendo números**.

**Commit.** `feat: calibra profundidad real en los 6 portales que quedaron en depth 0`

---

### B-29 · Activar headless en BCP y BCRP — Antigravity — 50 min

**Objetivo.** B-13 implementó y verificó el renderizado con navegador real
(403 → 200) y la bandera quedó apagada en todos los YAML.

**Pasos.** `use_playwright: true` en ambos portales y volver a correr.
Recordar D-03: `wait_until="domcontentloaded"`, nunca `"networkidle"`.

**Criterio de aceptación.** BCP supera sus 25 documentos actuales **y** BCRP
pasa de no tener corrida a tener documentos. Pegar el conteo antes y después
de cada uno.

**Commit.** `fix: activa el renderizado en los dos portales que lo requieren`

---

### B-30 · Verificar que la extracción de ZIP dispara — Antigravity — 60 min

**Objetivo.** 1.893 de los 5.902 documentos de Rolando venían de comprimidos.
Nuestro motor lo implementa y se verificó en B-07 con un fixture, pero nadie
comprobó que haya disparado en una corrida real.

**Criterio de aceptación.** Al menos un recurso en `inventory.db` marcado
como extraído de un archivo comprimido, con su contenedor identificable. Si
ningún portal publica ZIP, decirlo **con la consulta SQL que lo demuestra**:
es un resultado válido y cierra la pregunta.

**Commit.** `test: verifica la extraccion de comprimidos sobre corridas reales`

---

## Etapa G — Encender los canales dormidos

Tres bloques, 3 h 30 estimadas. Descubrimiento que no depende de seguir
enlaces.

### B-31 · Sitemaps en todos los portales — Antigravity — 60 min

**Pasos.** Activar `use_sitemaps` en los 28 YAML y medir cuáles portales
publican uno realmente.

**Criterio de aceptación.** Tabla de qué portales tienen sitemap y cuántas
URL aportó cada uno, más el delta de documentos en al menos 3 portales. Si
activarlo no cambia nada en ninguno, eso también se reporta.

**Commit.** `feat: habilita descubrimiento por sitemap en todos los portales`

---

### B-32 · Wayback para archivo histórico — Antigravity — 90 min

**Objetivo.** Hipótesis más fuerte sobre cómo Rolando llegó a 1.606
documentos en ASFI-FINRURAL: series mensuales de años anteriores que ya no
están enlazadas desde el sitio vivo.

**Pasos.** Activar `use_wayback` en los portales con serie temporal: ASFI,
FINRURAL, BCB, ASOFIN, INE, SENAMHI.

**Cuidado.** Wayback devuelve URLs que pueden estar muertas hoy. Un documento
que solo existe en el archivo histórico es un resultado legítimo, pero
**tiene que quedar distinguible en el inventario**, no mezclado con los
vigentes.

**Criterio de aceptación.** ASFI o FINRURAL suman ≥ 200 documentos históricos
verificados como descargables — bytes, no solo listados (D-01 aplicado a
documentos) — y el inventario distingue vigente de histórico.

**Commit.** `feat: descubrimiento por archivo historico en portales con series temporales`

---

### B-33 · Conectar API y formularios al pipeline — PARTIDO en B-33a y B-33b

**Parada obligatoria resuelta el 2026-09-19.** Antigravity entregó el
diagnóstico (`docs/diagnostico_b33_api_formularios.md`) y Claude decidió
**partir el bloque** (`docs/decision_b33_api_formularios.md`, cerrada como
D-12). Las pautas de implementación de ambos sub-bloques están en el documento
de decisión; lo de abajo es solo el resumen ejecutable.

Dos cosas cambian respecto del enunciado original: `api_detector.py` **no** se
conecta al pipeline (sondeo ciego = D-02 aplicado a APIs; solo se reutiliza
`RobotsGate`), y SICOES e INE **dejan de ser casos objetivo** porque usan POST
con `__VIEWSTATE`, que `FormAutomator` no puede expresar.

---

#### B-33a · Consumo declarativo de endpoints JSON — Antigravity — 70 min

**Objetivo.** Sección nueva `crawl.api_endpoints` en el YAML, módulo nuevo
`src/crawler/core/api_consumer.py` y un único enganche en `DiscoveryEngine`,
con el mismo patrón que wayback. Sin la sección, comportamiento idéntico al
actual.

**Criterio de aceptación.** SICSANTACRUZ pasa de 0 a ≥ 10 documentos
descargados vía la API, contados **leyendo `inventory.db`** y con los primeros
bytes de 3 archivos verificados. Más las dos pruebas nuevas vistas en rojo
antes del fix, una de ellas la de no-regresión (YAML sin `api_endpoints` ⇒ 0
peticiones).

**Commit.** `feat: consumo declarativo de endpoints json en el descubrimiento`

---

#### B-33b · Expansión de formularios GET — Antigravity — 45 min — CONDICIONADO

**Paso 0 obligatorio (15 min).** Encontrar en el catálogo al menos una fuente
con `<form method="get">` real cuyas combinaciones devuelvan documentos. Si no
aparece ninguna, el bloque cierra como **no implementado** con esa evidencia
—resultado válido— y se registra en `AI_LOG.md`.

**Criterio de aceptación.** La fuente hallada en el Paso 0 pasa de N a > N
documentos verificados por bytes, **y** una fuente sin formularios no cambia su
conteo entre dos corridas. Detrás de `crawl.expand_get_forms: false` por
defecto, con las URLs generadas contando contra `max_pages`.

**Commit.** `feat: expansion de formularios get en el descubrimiento`

---

## Etapa H — Cobertura total

Cinco bloques, ~95 min cada uno. Las 29 fuentes que responden 200 y nunca se
crawlearon — 12 con documento ya detectado por el diagnóstico ligero.

**Lote 1 (B-34), las 12 con documento detectado:** BBV, CEPAL, BM, ICCO, ITU,
MDRyT, MDRyT/OAP, UNDATA, Statistics Denmark, SIGMA, FDTA-Valles, OTROS
HISTORICOS.

**Lotes 2 a 5 (B-35 a B-38), las 17 restantes:** BCB_BRASIL, BCCH, CEPROBOL,
DOLARBLUEBOLIVIA, Data.Gov, FEGASACRUZ, FIFA, MHE, NIH, OBA, OMC, SABSA,
SICOES, SICSANTACRUZ, SISPAM, TRANSTATS, VIPFE. Acá el diagnóstico no detectó
documentos y puede que legítimamente no los haya.

**Dos correcciones respecto de los lotes de la Etapa C:** arrancar en
profundidad 2 (no 0) y con sitemaps y wayback ya activados desde el primer
intento.

**Criterio de aceptación por portal.** Ya no es "≥ 1 documento" — esa fue la
lección E-14 de B-15, donde un umbral pensado como prueba de humo se usó como
meta de cobertura. Es: **profundidad calibrada al sitio y resultado estable
entre dos corridas**. Un portal sin documentos cierra con la evidencia de por
qué no los tiene, no con un número bajo sin explicar.

**Tarea menor a incluir en B-34.** La entrada `MEFP` del catálogo tiene
corrida (`output/mefp/`) pero le falta `crawler_source`. Es la única entrada
en esa situación y hace que cualquier conteo automático la cuente como
pendiente.

**Commit por lote.** `feat: onboarding lote N — portales A, B, C, D, E, F`

---

## Etapa I — Medir y cerrar

### B-39 · Comparativa automatizada contra el benchmark — Antigravity — 70 min

**Objetivo.** Un comando que produzca la tabla portal por portal contra los
tres crawlers, con el mapeo explícito de las entradas consolidadas.

**Por qué explícito.** La comparación de `docs/comparativa_vs_benchmark.md`
la hice a mano y el primer intento estuvo mal: el emparejamiento por prefijo
confundió `anapo` con `an` (Aduana) y contó ASFI cuatro veces. El mapeo va
curado en un diccionario, no inferido.

**Criterio de aceptación.** Reproduce exactamente las cifras de
`docs/comparativa_vs_benchmark.md` sobre el estado actual del repositorio. Si
no reproduce un número ya verificado, el comparador no sirve para medir el
resultado final.

**Commit.** `feat: comparador reproducible contra el benchmark de los 3 crawlers`

---

### B-40 · Corrida completa y cierre — Claude — 60 min

Correr todos los portales de punta a punta, medir con el comparador de B-39,
actualizar `docs/comparativa_vs_benchmark.md` y `docs/bitacora_equipo.md`.

**Criterio de aceptación.** Los cuatro objetivos de esta fase, medidos y
pegados literales. Si alguno no se alcanzó, se reporta el número real con la
causa. **No se ajusta la meta para que dé.**

**Commit.** `docs: resultado final medido contra el benchmark`

---

## Seguimiento

| Bloque | Responsable | Estimado | Real | Estado |
|---|---|---:|---:|---|
| B-28 Profundidad en 6 portales | Antigravity | 90 min | 45 min | ✅ Aprob. c/obs (`da93ca9`) |
| B-29 Headless BCP/BCRP | Antigravity | 50 min | 40 min | ✅ Aprob. c/obs (`141582b`) |
| B-30 Verificar ZIP | Antigravity | 60 min | 40 min | ✅ Aprob. c/obs (`172b76c`) |
| B-31 Sitemaps | Antigravity | 60 min | 45 min | ✅ Aprob. c/obs (`dddb969`) |
| B-32 Wayback | Antigravity | 90 min | 150 min | ✅ Aprob. c/obs (`ee1f183`) |
| B-33a API declarativa + SICSANTACRUZ | Antigravity | 70 min | 70 min | ✅ Aprob. c/obs (`bd13515`) |
| B-33b Formularios GET | Antigravity | 45 min | 15 min | ✅ Cerrado s/impl (Paso 0, D-12) |
| B-34 Lote 1 (12 con doc) | Antigravity | 95 min | 75 min | ✅ Aprob. c/obs (`ac89f06`) |
| B-35 Lote 2 | Antigravity | 95 min | 55 min | ✅ Aprob. c/obs (`ac89f06`) |
| B-36 Lote 3 | Antigravity | 95 min | 45 min | ✅ Aprob. c/obs (`b6cb16a`) |
| B-37 Lote 4 | Antigravity | 95 min | 40 min | ✅ Aprob. c/obs (`b6cb16a`) |
| B-38 Lote 5 | Antigravity | 95 min | 40 min | ✅ Aprob. c/obs (`b6cb16a`) |
| B-39 Comparador | Antigravity | 70 min | 35 min | ✅ Aprob. c/obs (`bd90814`) |
| B-40 Cierre | Claude | 60 min | | Pendiente |
| **Total** | | **~17 h** | | |

En la Etapa C los bloques mecánicos se estimaron ~50% cortos y los de trabajo
real dieron cerca. Tomar estas cifras con ese sesgo conocido.

---

## Modo de ejecución — corrida continua

Decisión de Marlon del 2026-09-19: **el bucle corre los 13 bloques de
principio a fin**, sin pausas por etapa, hasta terminar o hasta que se agote
el presupuesto de tokens de cualquiera de los dos asistentes.

Bucle automatizado según `docs/guia_bucle_automatizado.md`, con las tres
restricciones del acta de B-15 intactas: puntero puro y no resumen, auditor
sin permisos de escritura ni commit, y paradas explícitas.

### Qué cambia respecto de las paradas anteriores

Las paradas por fin de etapa **se eliminan**. Las decisiones que antes
escalaban a Marlon las toma Claude dentro del acta, que es donde ya tiene
autoridad según `docs/protocolo_equipo.md`:

| Situación | Antes | Ahora |
|---|---|---|
| Fin de etapa | Parar y consultar | Seguir |
| Veredicto DEVUELTO | Parar | Antigravity subsana y reenvía; parar recién al **tercer** DEVUELTO del mismo bloque |
| Diseño de B-33 | Parar y consultar | ✅ Resuelto 2026-09-19: partido en B-33a y B-33b (`docs/decision_b33_api_formularios.md`, D-12) |
| El acta propone tocar `docs/decisiones.md` | Parar | **Sigue parando** |

**El bucle se detiene y espera a Marlon solo en tres casos:**

1. El acta propone abrir o modificar una decisión de `docs/decisiones.md`.
2. Un bloque acumula **tres** veredictos DEVUELTO — señal de que el problema
   no es de ejecución.
3. Bloqueo externo insalvable (WAF con captcha, dominio caído, credenciales).

Al cerrar cada bloque, Antigravity actualiza `docs/bitacora_equipo.md`. Sin
copiar y pegar prompts, ese archivo es la única visibilidad que le queda a
Marlon sobre lo que está pasando.

---

## Política de tokens

El presupuesto de tokens es el recurso que decide hasta dónde llega esta
fase, así que se administra explícitamente. Tres principios.

### 1. Orden por valor sobre costo, para que quedarse sin tokens no duela

El orden de los bloques ya no es solo lógico: es **descendente en retorno por
token gastado**. Si el presupuesto se agota a mitad de camino, lo que quedó
sin hacer debe ser lo de menor valor.

| Prioridad | Bloques | Por qué en ese orden |
|---|---|---|
| **1** | B-28, B-29 | ≈ +3.500 docs esperados con cambios de una línea. La mejor relación del plan por un margen enorme. |
| **2** | B-31, B-32 | Sitemaps y wayback: alto retorno, costo bajo, aplican a todos los portales a la vez. |
| **3** | B-30, B-34 | ZIP y el lote de las 12 fuentes con documento ya detectado: retorno alto pero trabajo por fuente. |
| **4** | B-33a, B-33b | Alto valor y **alto costo en tokens**. El diseño ya está cerrado (D-12), así que lo que queda es ejecución. B-33a primero: es el que tiene el criterio medible. |
| **5** | B-35 a B-38 | Las 17 fuentes sin documento detectado. Es donde menos se espera encontrar, y es lo aceptable de perder. |
| **6** | B-39, B-40 | Medición y cierre. **Si el presupuesto está por agotarse, estos dos se ejecutan igual**: sin medir, la fase no tiene resultado reportable. |

**Regla dura:** B-39 y B-40 no se sacrifican. Ante presupuesto ajustado se
recortan lotes de la Etapa H, nunca el cierre.

### 2. Auditorías por niveles, no todas iguales

Auditar 13 bloques con la misma profundidad gasta tokens míos en verificar
cambios triviales. Los bloques se agrupan en tres niveles:

| Nivel | Bloques | Alcance de la auditoría |
|---|---|---|
| **Completa** | B-28, B-30, B-32, B-33a, B-33b, B-39, B-40 | Parte + `git show --stat` + sondeo independiente. Son los que introducen mecanismo nuevo, criterio nuevo o miden el resultado. |
| **Ligera** | B-29, B-31 | Solo reproducir el número del criterio de aceptación. Son cambios de bandera con umbral numérico: o el conteo subió o no. |
| **Agrupada** | B-34 a B-38 | Dos auditorías en total, no cinco: una después de B-35 y otra después de B-38. Son lotes casi idénticos; auditar cada uno por separado repite el mismo trabajo cinco veces. |

Baja las invocaciones de 13 a 9 y concentra el esfuerzo donde un error sería
caro.

### 3. Lo que no se gasta

**Del lado de Claude (auditor):**
- Nunca releer el repositorio completo. El protocolo ya dice parte +
  `git show --stat` + un sondeo; el `--stat` antes que el diff entero, y el
  diff completo solo de los archivos que el hallazgo exige.
- No repetir en el acta lo que ya dice el parte. El acta contiene el
  veredicto, lo que verifiqué por mi cuenta y los hallazgos. Nada más.
- No reescribir documentos enteros para cambiar un renglón.

**Del lado de Antigravity (ejecutor):**
- **No pegar logs de corrida en el contexto.** Una corrida de crawler genera
  miles de líneas y aporta lo mismo que una consulta SQL agregada sobre
  `inventory.db`. El parte lleva el conteo y dos o tres muestras, no el log.
- Redirigir la salida de las corridas a archivo y leer solo el agregado.
- No reexplorar el repositorio en cada bloque: el estado vive en
  `docs/plan_bloques_fase2.md` y en `docs/bitacora_equipo.md`.
- Un solo parte por bloque, con evidencia literal pero acotada.

### 4. Si el presupuesto se agota

El trabajo está commiteado bloque a bloque, así que agotarse no pierde nada:
deja el repositorio en el último bloque cerrado y en verde. El que se quede
sin tokens deja escrito en `docs/bitacora_equipo.md` **en qué bloque quedó y
cuál es el siguiente**, para poder retomar sin reconstruir el contexto.
