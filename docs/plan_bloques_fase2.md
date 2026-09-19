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

### B-33 · Conectar API y formularios al pipeline — Claude decide, Antigravity implementa — 100 min

**Objetivo.** `api_detector.py` (583 líneas) y `form_automator.py` están
implementados y no los llama nadie. Desbloquean los casos sin salida:
SICSANTACRUZ (API Strapi), SICOES e INE (formularios de consulta).

**Parada obligatoria antes de implementar.** Este es el bloque con más riesgo
de desbordarse. Antigravity entrega primero un diagnóstico —qué expone cada
módulo, qué haría falta en el orchestrator, si entra en un bloque— y Claude
decide si se implementa entero o se parte. Toca el motor de extracción, así
que aplica la regla de `CLAUDE.md`: plan aprobado antes del cambio.

**Criterio de aceptación.** SICSANTACRUZ pasa de 0 a ≥ 10 documentos
descargados vía la API, con los primeros bytes verificados.

**Commit.** `feat: descubrimiento por api y formularios en el pipeline de extraccion`

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
| B-28 Profundidad en 6 portales | Antigravity | 90 min | | Pendiente |
| B-29 Headless BCP/BCRP | Antigravity | 50 min | | Pendiente |
| B-30 Verificar ZIP | Antigravity | 60 min | | Pendiente |
| B-31 Sitemaps | Antigravity | 60 min | | Pendiente |
| B-32 Wayback | Antigravity | 90 min | | Pendiente |
| B-33 API y formularios | Claude + Antigravity | 100 min | | Pendiente |
| B-34 Lote 1 (12 con doc) | Antigravity | 95 min | | Pendiente |
| B-35 Lote 2 | Antigravity | 95 min | | Pendiente |
| B-36 Lote 3 | Antigravity | 95 min | | Pendiente |
| B-37 Lote 4 | Antigravity | 95 min | | Pendiente |
| B-38 Lote 5 | Antigravity | 95 min | | Pendiente |
| B-39 Comparador | Antigravity | 70 min | | Pendiente |
| B-40 Cierre | Claude | 60 min | | Pendiente |
| **Total** | | **~17 h** | | |

En la Etapa C los bloques mecánicos se estimaron ~50% cortos y los de trabajo
real dieron cerca. Tomar estas cifras con ese sesgo conocido.

---

## Modo de ejecución

Bucle automatizado según `docs/guia_bucle_automatizado.md`, con las tres
restricciones del acta de B-15: puntero puro y no resumen, auditor sin
permisos de escritura ni commit, y parada explícita.

**El bucle se detiene y consulta a Marlon cuando:**

- el veredicto es **DEVUELTO**
- el bloque queda **BLOQUEADO**
- el acta propone tocar `docs/decisiones.md`
- **termina una etapa** (F, G, H, I)
- llega **B-33**, que tiene parada de diseño propia antes de implementar

Al cerrar cada bloque, Antigravity actualiza `docs/bitacora_equipo.md`. Es lo
que reemplaza la visibilidad que Marlon pierde al no copiar y pegar los
prompts.
