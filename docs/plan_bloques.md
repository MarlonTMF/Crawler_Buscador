# Plan de bloques — ejecución de la cobertura 100%

Este documento es el **plan operativo**: qué se hace, en qué orden, cuánto
debería costar y con qué commit cierra cada pieza. El **por qué** de cada
decisión vive en `docs/decisiones.md` (D-01 a D-08) y el **mapa de fases** en
`docs/plan_cobertura_100.md`. Este archivo no repite ninguno de los dos: los
ejecuta.

---

## Cómo se lee un bloque

Un bloque es una unidad de trabajo que **cierra con un commit y deja el
repositorio en verde**. Si un bloque no puede cerrar con un commit que se
sostenga solo, está mal dimensionado y hay que partirlo.

| Campo | Qué significa |
|---|---|
| **Objetivo** | La frase que justifica el bloque. Si no se puede decir en una línea, el bloque hace dos cosas. |
| **Entradas** | Qué tiene que existir antes. Si falta algo, el bloque está bloqueado y se salta, no se empieza a medias. |
| **Pasos** | Comandos reales, no descripciones. Copiables. |
| **Criterio de aceptación** | Cómo se comprueba que quedó hecho — siempre verificando el **efecto**, no el artefacto (`CLAUDE.md`). |
| **Estimado** | Tiempo de trabajo efectivo, sin contar esperas de corridas largas salvo que se indique. |
| **Commit** | El mensaje exacto con el que cierra. Uno por bloque. |

**Regla de oro heredada del proyecto anterior:** ningún bloque se marca como
terminado sin correr su criterio de aceptación. Un bloque "que se ve bien" no
está hecho.

---

## Convención de commits

```
tipo: descripción en minúscula, imperativa, en español

- viñeta con el qué y, si no es obvio, el porqué
- otra viñeta

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

| Tipo | Cuándo |
|---|---|
| `feat` | Capacidad nueva del crawler o del pipeline |
| `fix` | Corrección de un comportamiento roto |
| `test` | Pruebas nuevas o reorganización de la suite |
| `docs` | Documentación, decisiones, planes |
| `chore` | Configuración, hooks, agentes, `.gitignore` |
| `data` | Cambios en el catálogo de fuentes (`config/moved_urls.json`) — extensión propia de este proyecto, porque los datos **son** el entregable de Track A y merecen historial propio |
| `refactor` | Reestructura sin cambio de comportamiento |

Nunca `git add -A`: cada bloque agrega **sus** archivos por nombre. Hay trabajo
de tres sesiones mezclado en el árbol y un `add -A` lo aplastaría en un commit
ilegible.

---

## Seguimiento de tiempo

Rellená **Real** al cerrar cada bloque y anotá el desvío. Si un bloque se pasa
más del 50%, escribí una línea en `AI_LOG.md` con la razón — la próxima
estimación del mismo tipo de trabajo depende de eso.

### Etapa A · Ordenar lo ya hecho (deuda de commits)

| # | Bloque | Estimado | Real | Estado | Commit |
|---|---|---|---|---|---|
| B-01 | Higiene de `.gitignore` y material de terceros | 20 min | — | ⬜ | `chore:` |
| B-02 | Fix de `mailto:`/`tel:` en discovery | 15 min | — | ⬜ | `fix:` |
| B-03 | Separación de tests `live` | 15 min | — | ⬜ | `test:` |
| B-04 | Resoluciones de URL verificadas | 20 min | — | ⬜ | `data:` |
| B-05 | Infraestructura de trabajo (CLAUDE.md, agentes, hook) | 20 min | — | ⬜ | `chore:` |
| B-06 | Documentos de decisiones y planes | 15 min | — | ⬜ | `docs:` |
| B-07 | Cambios del dashboard y del fetcher pendientes | 45 min | 20 min | ✅ | `feat:` ×2 |
| B-07b | Módulos sin trackear que el plan omitió | 40 min | — | ⬜ | `feat:` |
| | **Subtotal etapa A** | **3 h 10 min** | | | |

> **B-07b agregado el 2026-09-18.** Al ordenar el árbol tras cerrar B-07
> aparecieron ~1.550 líneas **sin trackear** que ningún bloque cubría:
> `src/crawler/core/api_detector.py` (583), `src/crawler/core/url_resolver.py`
> (289), `resolve_dead_domains.py` (179), `generate_api_report.py` (253),
> `ingest_samples.py`, `update_all_evidence.py`,
> `scripts/render_api_report_pdf.py`, sus tests
> (`test_api_detector.py`, `test_url_resolver.py` — 18 casos que ya pasan) y
> los documentos `RESUMEN_SESION.md` y `URLsFaltantes.md`.
>
> **Por qué se escapó:** la etapa A se diseñó leyendo `git status` y se
> enfocó en los archivos **modificados** (la columna ` M`), sin asignar
> bloque a los **sin trackear** (`??`) más allá de los que B-01 mandó a
> ignorar. Es un hueco del plan, no de la ejecución.

### Etapa B · Cerrar Track A (Fase 0)

| # | Bloque | Estimado | Real | Estado | Commit |
|---|---|---|---|---|---|
| B-08 | Auditar la brecha de 13 fuentes (76 vs 63) | 45 min | — | ⬜ | `data:` |
| B-09 | FMI: probar el patrón BCP con headless | 30 min | — | ⬜ | `data:` |
| B-10 | SICSANTACRUZ: investigación nueva post-parking | 40 min | — | ⬜ | `data:` |
| B-11 | Fusionar duplicado de BOLCEREALES y cerrar Track A | 25 min | — | ⬜ | `data:` |
| | **Subtotal etapa B** | **2 h 20 min** | | | |

### Etapa C · Escalar Track B (Fase 2)

| # | Bloque | Estimado | Real | Estado | Commit |
|---|---|---|---|---|---|
| B-12 | Generador de esqueletos YAML desde el diagnóstico | 75 min | — | ✅ | `feat:` |
| B-13 | Runner por lotes con reporte de cobertura | 60 min | — | ✅ | `feat:` |
| B-14 | Lote 1 — 4 fuentes (BCP, INE, ASFI, BCB) | 80 min | 80 min | ✅ | `feat:` |
| B-15 | Lote 2 — 4 fuentes (APS, ADA, DGAC, SEPREC) + consolidación de portales | 80 min | 80 min | ✅ | `feat:` |
| B-16 | Lote 3 — 4 portales (IBCE-CAO, CNDC, ASOFIN, ATT) | 80 min | 90 min | ✅ | `feat:` |
| B-17 | Lote 4 — 4 portales | 80 min | — | ⬜ | `feat:` |
| B-18 | Lote 5 — 4 portales | 80 min | — | ⬜ | `feat:` |
| B-19 | Lote 6 — 4 portales | 80 min | — | ⬜ | `feat:` |
| B-20 | Lote 7 — 1 portal restante + cierre de onboarding | 40 min | — | ⬜ | `feat:` |
| | **Subtotal etapa C (ajustado: 25 portales en vez de 34 fuentes)** | **10 h 15 min** | | | |

### Etapa D · Calibración (Fase 3)

| # | Bloque | Estimado | Real | Estado | Commit |
|---|---|---|---|---|---|
| B-23 | Reintento automático con headless ante 403 | 70 min | — | ⬜ | `feat:` |
| B-24 | Calibración de profundidad/páginas por tamaño real | 60 min | — | ⬜ | `feat:` |
| | **Subtotal etapa D** | **2 h 10 min** | | | |

### Etapa E · Sostenimiento (Fase 4)

| # | Bloque | Estimado | Real | Estado | Commit |
|---|---|---|---|---|---|
| B-25 | Script de re-verificación de Track A | 50 min | — | ⬜ | `feat:` |
| B-26 | Reporte de cobertura reproducible | 45 min | — | ⬜ | `feat:` |
| B-27 | Cierre: README, artifact y estado final | 40 min | — | ⬜ | `docs:` |
| | **Subtotal etapa E** | **2 h 15 min** | | | |

**Total estimado: 23 horas de trabajo efectivo** (≈ 3 jornadas). Las etapas A y
B (4 h 50 min) desbloquean todo lo demás y no dependen de nada externo.

> Aviso honesto sobre estas cifras: son **estimaciones, no mediciones**. La
> única cifra medida acá es el tiempo de corrida del crawler sobre FINRURAL
> (296 candidatos a 1 req/s ≈ 5 min de espera). En el proyecto anterior las
> estimaciones razonadas por partes se quedaron cortas dos veces seguidas
> (bundle estimado 42 KB → medido 68,6 KB; carga estimada 760 ms → medida
> 1 680 ms). Esperá el mismo sesgo acá y corregí la tabla con los reales.

---

# ETAPA A · Ordenar lo ya hecho

Hay tres sesiones de trabajo sin commitear en el árbol (`git status`: 11
archivos modificados, 13 sin seguimiento). Esta etapa no agrega
funcionalidad: convierte ese pilón en historial legible. Se hace primero
porque cualquier bloque posterior que rompa algo va a ser imposible de aislar
si el punto de partida es un árbol sucio.

---

## B-01 · Higiene de `.gitignore` y material de terceros

**Objetivo.** Que el repositorio no arrastre 10 MB de material de análisis que
no es código del proyecto.

**Entradas.** Ninguna.

**Pasos.**

```bash
# Verificar qué pesa lo que está sin seguimiento
du -sh "Elecciones De Crawler por URL" "Propuesta arquitectura y Backlogs"
# 9.9M y 792K — material de benchmark y propuestas de terceros

# Agregarlos a .gitignore junto con las salidas locales
```

Al `.gitignore` van: `Elecciones De Crawler por URL/`,
`Propuesta arquitectura y Backlogs/`, `*.rar`, `*.zip`, `mi_benchmark_run.log`,
`resultadosPrimerCrawleoUnido.xlsx`.

**Criterio de aceptación.** `git status --short` no lista ninguna de esas
rutas, y `git check-ignore -v "Elecciones De Crawler por URL"` confirma la
regla que las cubre.

**Riesgo conocido.** El informe del benchmark
(`Informe_Prospeccion_en_Cifras.html`) es la única fuente de las cifras de los
3 crawlers citadas en `docs/plan_cobertura_100.md`. Si se ignora la carpeta
entera, esa evidencia deja de estar versionada — copiar ese HTML a `docs/`
antes de ignorar el resto.

**Estimado.** 20 min.

**Commit.**
```
chore: ignora material de benchmark y binarios de terceros

- 10 MB de corridas de benchmark y propuestas externas fuera del repo
- se conserva en docs/ el informe comparativo, que es la fuente de las
  cifras citadas en el plan de cobertura
```

---

## B-02 · Fix de `mailto:`/`tel:` en discovery

**Objetivo.** Commitear el bug ya corregido (D-06) con su prueba de
regresión, aislado de todo lo demás.

**Entradas.** `src/crawler/core/discovery.py` y `tests/test_discovery.py` ya
modificados (hecho en sesión previa).

**Pasos.**

```bash
python -m pytest tests/test_discovery.py -q          # 5 passed
git add src/crawler/core/discovery.py tests/test_discovery.py
```

**Criterio de aceptación.** Los 5 casos de `tests/test_discovery.py` pasan, y
—esto es lo que de verdad importa— se confirma que fallan sin el fix:

```bash
git stash -- src/crawler/core/discovery.py
python -m pytest tests/test_discovery.py -q          # 3 failed, 2 passed
git stash pop
```

**Estimado.** 15 min.

**Commit.**
```
fix: descarta enlaces mailto:/tel: que el crawler trataba como páginas

_is_allowed_domain devolvía True para esquemas sin netloc, así que cada
enlace de contacto entraba a la cola de rastreo y gastaba 3 reintentos con
backoff (~9s) sin producir nada. Contra FINRURAL, una corrida de 100s se
quedaba entera en enlaces de contacto sin escanear una sola página real;
con el fix escanea 19 páginas y descubre 296 candidatos en 25s.

- filtro explícito de mailto:, tel:, fax:, whatsapp: y sms: en las anclas
- segunda capa en _is_allowed_domain: rechaza todo esquema no HTTP(S),
  porque una URL así también puede entrar por sitemap o wayback
- prueba de regresión verificada fallando antes de aplicar el fix
```

---

## B-03 · Separación de tests `live`

**Objetivo.** Que la verificación rápida exista y sea confiable (D-08).

**Entradas.** B-02 cerrado.

**Pasos.**

```bash
python -m pytest tests/ -q -m "not live"    # 52 passed, 2 deselected, ~8s
python -m pytest tests/ -q                  # completa, ~65 min — NO en este bloque
git add pyproject.toml
git add -p tests/test_validation_engine.py  # SOLO los hunks de @pytest.mark.live
```

> **Corregido tras la auditoría de B-03 (2026-09-17).** Este paso decía
> `git add pyproject.toml tests/test_validation_engine.py`. Ese archivo tenía
> 54 líneas pendientes de otra sesión —dos tests de Gemini— que viajaron de
> polizón y dejaron HEAD roto: los tests quedaron commiteados y el
> `fetcher.py` que los soporta no. `git add -p` evita exactamente eso. La
> regla de `CLAUDE.md` contra `git add -A` aplica igual a nivel de archivo
> cuando el archivo tiene trabajo mezclado.

**Criterio de aceptación.** La suite filtrada corre en menos de 15 segundos y
**detecta un error real**: introducir a propósito una aserción invertida en
`tests/test_discovery.py`, confirmar que la suite se pone en rojo, y
revertirla. Una salvaguarda que no se vio fallar no es una salvaguarda.

Y —agregado tras la auditoría— que **HEAD quede en verde contra el código de
HEAD**, no contra el árbol de trabajo (ver "Verificación contra HEAD limpio"
en `docs/protocolo_equipo.md`).

**Estimado.** 15 min.

**Commit.**
```
test: separa con el marcador live los 2 tests que tocan red real

La suite completa tardaba 65 minutos y nadie la corría antes de comitear,
que es lo mismo que no tener verificación. Los responsables son 2 tests
que mockean session.head/get pero el fallback interno de HttpFetcher
escapa el mock y sale a la red de verdad.

- marcador live registrado en pyproject.toml
- pytest -m "not live" corre 52 tests en 8s
- causa exacta del escape del mock sin diagnosticar, anotada en D-08
```

---

## B-04 · Resoluciones de URL verificadas

**Objetivo.** Versionar el trabajo de Track A de las dos últimas sesiones:
CADEXCO, IBCH, BCP (3 documentos) y Aduana Nacional.

**Entradas.** `config/moved_urls.json` con las 6 entradas nuevas.

**Pasos.**

```bash
python -c "import json; json.load(open('config/moved_urls.json', encoding='utf-8'))"
git add config/moved_urls.json
```

**Criterio de aceptación.** El JSON carga sin error (ya rompió una vez por una
coma colgante), y cada entrada nueva tiene `reason` y `matched_keywords` —
sin esos dos campos la resolución no cumple D-01 y no se commitea.

```bash
python -c "
import json
m = json.load(open('config/moved_urls.json', encoding='utf-8'))
faltan = [e['original'] for e in m if not e.get('reason')]
print('sin razón documentada:', faltan or 'ninguna')
"
```

**Estimado.** 20 min.

**Commit.**
```
data: aplica las resoluciones verificadas por contenido de 6 URLs

Todas verificadas contra el contenido de la página, no solo por status 200
(D-01), después de que tres sugerencias de IA apuntaran a instituciones
distintas en sesiones anteriores.

- CADEXCO -> cadexco.bo (verificado: "Cochabamba", no CADEX Santa Cruz)
- IBCH -> ibch.com (verificado: "cemento", no IBCE comercio exterior)
- BCP: 3 documentos remapeados a la nueva estructura /web/institucional/
- Aduana Nacional: boletines movidos a /com_boletines
```

---

## B-05 · Infraestructura de trabajo

**Objetivo.** Versionar `CLAUDE.md`, los 3 subagentes y el hook.

**Entradas.** B-03 cerrado (el hook depende del marcador `live`).

**Pasos.**

```bash
git add CLAUDE.md .claude/
```

**Criterio de aceptación.** El hook se dispara de verdad: editar cualquier
archivo y confirmar que corre la suite rápida. Si el hook no se ejecuta, el
bloque no está hecho — un hook mal configurado **no falla, simplemente no
corre**, y da confianza falsa durante todo el proyecto.

**Estimado.** 20 min.

**Commit.**
```
chore: infraestructura de trabajo — agentes, hook y reglas del proyecto

- CLAUDE.md con las reglas, los comandos y la tabla de fallos silenciosos
  que ya se cometieron acá
- 3 subagentes con alcance delimitado: conectividad-auditor (Track A),
  fuente-onboarder (Track B) y revisor (cierre de fase)
- hook PostToolUse que corre la suite rápida (8s) tras cada edición,
  verificado introduciendo un error real y viendo que lo detecta
```

---

## B-06 · Documentos de decisiones y planes

**Objetivo.** Versionar `docs/decisiones.md`, `docs/plan_cobertura_100.md`,
este archivo y `AI_LOG.md`.

**Entradas.** Ninguna.

**Criterio de aceptación.** Cada decisión D-01 a D-08 tiene fecha de
verificación y umbral que la reabriría. Una decisión sin umbral es una
opinión, y no se commitea como decisión.

**Estimado.** 15 min.

**Commit.**
```
docs: registro de decisiones, plan de cobertura y plan de bloques

- D-01 a D-08 con contexto, alternativa descartada, razón y umbral
- plan de cobertura con el baseline medido (Track A 59/63, Track B 2/63)
- plan de bloques con estimaciones, criterios de aceptación y commits
- AI_LOG.md con las paradas planificadas de las etapas B y C
```

---

## B-07 · Cambios del dashboard y del fetcher pendientes

**Objetivo.** Cerrar la deuda más grande del árbol: 951 líneas modificadas en
`fetcher.py`, `validation_engine.py`, `headless_fetcher.py`, `dashboard_server.py`
y `dashboard/app.js` de sesiones anteriores, sin commit.

**Entradas.** B-02 a B-06 cerrados.

**Pasos.**

```bash
git diff src/crawler/core/fetcher.py | head -100     # revisar antes de agregar
git diff dashboard_server.py dashboard/app.js
python -m pytest tests/ -q -m "not live"
```

**Criterio de aceptación.** Antes de agregar nada: leer el diff completo. Son
cambios de sesiones anteriores y **nadie verificó que sigan siendo
correctos**. En particular, `fetcher.py` creció 341 líneas — ahí adentro está
el fallback que escapa el mock de D-08; si al leerlo aparece la causa, este
bloque se parte en dos y el arreglo va aparte.

**Riesgo conocido.** Este es el bloque con más probabilidad de desbordarse. Si
el diff revela cambios que no se entienden, **no se commitean a ciegas**: se
anota en `AI_LOG.md` y se consulta.

**Estimado.** 45 min.

**Commit.** (a ajustar según lo que revele el diff)
```
feat: resolución de dominios muertos con verificación de contenido

- fetcher.py: veredicto de Gemini + intercambio de variantes mecánicas,
  con verificación de contenido obligatoria antes de aceptar un candidato
- headless_fetcher.py: render con Playwright para sitios tras Cloudflare
- dashboard: columna de mapeo con aceptar/rechazar por URL
```

---

# ETAPA B · Cerrar Track A

Objetivo de la etapa: pasar de **59/63 (93.7%)** a 100% del catálogo, o a
100% con exclusiones **documentadas y justificadas** — que una fuente
disuelta quede marcada como tal también es cerrar el caso.

Agente responsable: `conectividad-auditor`.

---

## B-08 · Auditar la brecha de 13 fuentes

**Objetivo.** Saber qué son las 13 fuentes de diferencia entre el universo
reconciliado (76) y el dataset operativo (63), y si corresponde cargarlas.

**Entradas.** `backup_10.0.0.12` presente, `pgdumplib` instalado (ambos ya
verificados).

**Pasos.**

```bash
python -c "
import pgdumplib, json
dump = pgdumplib.load('backup_10.0.0.12')
spim = {r[2] for r in dump.table_data('public','source')}
mio  = {r['Fuente'] for r in json.load(open('output/excel_urls_diagnostic.json', encoding='utf-8'))}
print('en SPIM y no en el dataset:', sorted(spim - mio))
print('en el dataset y no en SPIM:', sorted(mio - spim))
" 2>/dev/null
```

**Criterio de aceptación.** La lista de la diferencia está enumerada **fuente
por fuente**, y cada una clasificada en una de tres categorías: (a) hay que
cargarla, (b) es duplicado de una que ya está con otro nombre, (c) es una
entrada interna/de prueba que no corresponde cargar. Un "son 13" sin nombres
no cierra el bloque.

**Nota de contexto que ahorra tiempo.** Ya se sabe que 43 de las 74 fuentes de
SPIM se cargaron en bloque el 2022-11-01 con `homepage='vacio'` y sin ningún
archivo asociado — DATAX, CADECO y NIH entre ellas. Es probable que buena
parte de la brecha caiga en la categoría (c).

**Estimado.** 45 min.

**Commit.**
```
data: audita la brecha entre el universo SPIM y el dataset operativo

- diferencia enumerada fuente por fuente contra la tabla source del backup
- cada una clasificada: cargar / duplicado / entrada interna sin cargar
- el total del catálogo pasa a ser un número con nombres detrás, no una
  estimación arrastrada de sesiones anteriores
```

---

## B-09 · FMI: probar el patrón BCP con headless

**Objetivo.** Determinar si el 403 de `imf.org` es un bloqueo de bot (como
BCP) o un problema real.

**Entradas.** Playwright instalado (verificado).

**Pasos.**

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from playwright.sync_api import sync_playwright
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent=UA)
    r = pg.goto('https://www.imf.org/', wait_until='domcontentloaded', timeout=25000)
    print('status', r.status if r else None, '|', pg.title())
    b.close()
"
```

**Criterio de aceptación.** Si responde 200 con navegador: se registra el
mapeo con `source` indicando que requiere headless, igual que BCP, y se anota
en el YAML de esa fuente cuando llegue su turno en la etapa C. Si sigue en
403 con navegador real: es otro caso y se documenta como tal, sin forzarlo.

**Recordatorio de D-03.** `wait_until="domcontentloaded"`, nunca
`"networkidle"` — con `networkidle` el primer intento contra BCP dio timeout
falso a los 20s.

**Estimado.** 30 min.

**Commit.**
```
data: confirma si el 403 del FMI es bloqueo de bot o barrera real

- probado con navegador real siguiendo el patrón que resolvió BCP (D-03)
- resultado registrado en el diagnóstico con la evidencia de la prueba
```

---

## B-10 · SICSANTACRUZ: investigación nueva

**Objetivo.** Resolver la única fuente cuyo dominio expiró y fue re-registrado
por un tercero.

**Entradas.** B-08 cerrado (por si la brecha revela un registro relacionado).

**Pasos.** Buscar si el Gobierno Autónomo Departamental de Santa Cruz movió el
Sistema de Información y Comunicación Agropecuario a otro dominio o a un
subportal de `santacruz.gob.bo`. Verificar cualquier candidato **por
contenido** (D-01) — este caso es precisamente el que demuestra por qué:
`URLsFaltantes.md` lo daba por vivo con "confianza alta" el 2026-09-11 y seis
días después servía una página de parking de Namecheap.

**Criterio de aceptación.** Una de dos salidas, ambas válidas: (a) URL nueva
verificada por contenido, o (b) la fuente queda marcada como discontinuada con
la evidencia de la búsqueda registrada en `url_resolution_log.json`. Lo que no
es aceptable es dejarla en `DOMINIO_PARKING` sin conclusión.

**Riesgo conocido.** El dominio en manos de un tercero puede aparecer en
buscadores como si siguiera siendo institucional. No aceptar ningún resultado
sin abrir el contenido.

**Estimado.** 40 min.

**Commit.**
```
data: resuelve SICSANTACRUZ tras la expiración de su dominio

- sicsantacruz.com dejó de ser institucional: hoy es parking de Namecheap
- búsqueda del portal sucesor registrada en url_resolution_log.json con
  su evidencia, resuelva o no
```

---

## B-11 · Fusionar duplicado de BOLCEREALES y cerrar Track A

**Objetivo.** Higiene final del catálogo y cierre medido de la etapa.

**Entradas.** B-08, B-09 y B-10 cerrados.

**Pasos.**

```bash
# El registro con Fuente="manual" apunta a la misma bolsadecereales.org.bo
# que el registro BOLCEREALES: son la misma institución cargada dos veces.
python -c "
import json
p='output/excel_urls_diagnostic.json'
d=json.load(open(p, encoding='utf-8'))
from collections import Counter
print(Counter(str(r.get('HTTP_Status')) for r in d))
"
```

**Criterio de aceptación.** La cifra final de cobertura de Track A se
**calcula**, no se declara: total de registros, cuántos en `200`, cuántos
excluidos con razón documentada, y el porcentaje resultante. Ese número entra
en `docs/plan_cobertura_100.md` y en el artifact.

**Estimado.** 25 min.

**Commit.**
```
data: cierra Track A — catálogo sin duplicados y cobertura recalculada

- registro duplicado de BOLCEREALES fusionado (misma institución, dos filas)
- cobertura final calculada sobre el catálogo limpio, no estimada
- las exclusiones (disueltas, sin sucesor) quedan con su razón registrada
```

---

# ETAPA C · Escalar Track B

De **2 fuentes** con motor de extracción configurado a las **34 prioritarias**
(las que ya tienen "documento detectado" en el diagnóstico ligero). Es la
etapa más larga del plan y la que produce el entregable real: documentos.

Agente responsable: `fuente-onboarder`.

---

## B-12 · Generador de esqueletos YAML

**Objetivo.** Que crear el YAML de una fuente cueste minutos y no media hora,
sin que eso signifique aceptarlo sin verificar.

**Entradas.** Etapa A cerrada.

**Pasos.** Escribir `scripts/generar_yaml_fuente.py` que, dada una `Fuente`
del diagnóstico, emita `config/source_<id>.yaml` con: `source.id`, `name`,
`base_url` y `allowed_domains` derivados de `Final_Url`; `crawl.seeds` con la
URL verificada; `max_depth`/`max_pages` conservadores; `allowed_extensions`
por defecto; y las secciones de `classification` **vacías con un comentario
`# TODO: completar tras explorar el sitio`**.

**Criterio de aceptación.** El YAML generado para FINRURAL es equivalente al
que ya existe a mano en sus campos estructurales. Y —esto es lo importante—
el generador **no inventa reglas de clasificación**: las deja explícitamente
pendientes. Un YAML autogenerado con reglas plausibles pero no verificadas es
exactamente el fallo silencioso que `CLAUDE.md` describe: corre sin error y no
encuentra nada.

**Estimado.** 75 min.

**Commit.**
```
feat: generador de esqueletos YAML por fuente

- deriva id, dominios y semilla desde el diagnóstico de conectividad
- deja las reglas de clasificación como TODO explícito en vez de inventar
  patrones plausibles que correrían sin error y sin encontrar nada
- verificado contra el YAML de FINRURAL escrito a mano
```

---

## B-13 · Runner por lotes con reporte de cobertura

**Objetivo.** Correr N fuentes seguidas y obtener una tabla de resultado real
sin revisar `inventory.db` a mano una por una.

**Entradas.** B-12 cerrado.

**Pasos.** Escribir `scripts/correr_lote.py` que reciba una lista de ids,
ejecute el orchestrator para cada uno y consulte su `inventory.db` para
reportar: recursos `PROCESADO_EXITOSAMENTE`, errores por tipo, duración y
tipos de archivo encontrados.

**Criterio de aceptación.** Corrido sobre FINRURAL (la fuente ya validada)
reproduce el resultado conocido: ≥175 recursos procesados, 0 errores. Si no
reproduce un resultado ya medido, el runner miente y no sirve para medir los
otros 33.

**Riesgo conocido.** A `rate_limit_per_second: 1.0`, una fuente con ~300
candidatos tarda ≥5 minutos. Un lote de 4 fuentes puede ser 20-30 minutos de
espera: el runner tiene que poder correr en segundo plano y dejar el reporte
escrito, no exigir que alguien mire la consola.

**Estimado.** 60 min.

**Commit.**
```
feat: runner por lotes con reporte de cobertura real

- ejecuta N fuentes y consulta inventory.db de cada una para el conteo
- reporta recursos procesados, errores por tipo, duración y extensiones
- validado reproduciendo el resultado ya medido de FINRURAL (175, 0 errores)
```

---

## B-14 a B-20 · Lotes de onboarding (25 portales únicos tras consolidación)

Siete bloques (B-14 a B-20) con la **misma estructura**.
> **Ajuste B-14/B-15 (consolidación de portales):** el catálogo tenía 15 entradas
> compartiendo 6 portales (`asfi.gob.bo`, `aps.gob.bo`, `bcb.gob.bo`, `att.gob.bo`,
> `icco.org`, `ruralytierras.gob.bo`), más 3 de procedencia histórica (`SPVS-ASFI`,
> `SPVS-APS`, `SUPTRANS`). Aplicando la regla de 1 YAML por portal y datasets por
> institución/tema, el universo se redujo de 34 fuentes a 25 portales únicos
> (ahorro de 9 YAMLs y corridas redundantes). Con B-14 (4 portales) y B-15 (4 portales),
> quedan 17 portales por onboardear en B-16 a B-20.

**Objetivo de cada bloque.** Dejar 4 portales (1 en el último) con YAML propio
y al menos un documento real extraído y verificado.

**Entradas.** B-12 y B-13 cerrados. Track A resuelto para esas 4 fuentes.

**Pasos por cada fuente del lote.**

1. `python scripts/generar_yaml_fuente.py --fuente XXX` — esqueleto.
2. Explorar el sitio de verdad (`curl`/`WebFetch`): dónde viven los
   documentos, qué extensiones, si es HTML plano o SPA.
3. Completar `classification.dataset_rules` y `excluded_path_keywords` con
   patrones **reales de ese sitio**, no copiados de otra fuente.
4. `python -m src.crawler.main --config config/source_XXX.yaml --output-dir output`
5. Verificar leyendo datos, nunca el log:
   ```bash
   python -c "
   import sqlite3
   c = sqlite3.connect('output/XXX/inventory.db').cursor()
   c.execute('SELECT status, COUNT(*) FROM resource_audit_log GROUP BY status')
   print(c.fetchall())
   "
   ```

**Criterio de aceptación del bloque.** Las 4 fuentes tienen ≥1 recurso
`PROCESADO_EXITOSAMENTE` que sea un documento real (no una página HTML de
navegación), **o** una razón escrita de por qué esa fuente no entrega
documentos por esta vía. Cero fuentes en estado ambiguo al cerrar el bloque.

**Riesgo conocido, y es el que más probable desvíe la estimación.** Una fuente
puede resultar ser una SPA que no expone enlaces en el HTML estático. Cuando
pase: no forzar el modelo declarativo (D-07), marcar la fuente para la etapa D
y seguir con la siguiente. Perseguir un caso raro dentro de un bloque de lote
es la forma segura de que el bloque se desborde.

**Estimado.** 80 min por bloque (20 min por fuente, incluyendo espera de
corrida). El último, 50 min.

**Commit por bloque.**
```
feat: onboarding de <FUENTE1>, <FUENTE2>, <FUENTE3>, <FUENTE4>

- YAML por fuente con reglas de clasificación derivadas del sitio real
- N documentos extraídos y verificados en inventory.db (detalle por fuente)
- <fuente que no cerró, si la hubo> queda marcada para la etapa D: <razón>
```

---

# ETAPA D · Calibración

Las dos correcciones que la etapa C va a exigir en cuanto se generalice más
allá de FINRURAL.

---

## B-23 · Reintento automático con headless ante 403

**Objetivo.** Que un 403 del fetcher HTTP simple dispare un reintento con
navegador real sin intervención manual.

**Entradas.** Etapa C con al menos 3 lotes cerrados — hace falta saber
**cuántas** fuentes reales dan 403, no suponerlo.

**Criterio de aceptación.** El reintento se activa solo tras un 403 (no en
toda corrida: Playwright es caro), queda registrado en el log de auditoría
como "resuelto vía headless", y una fuente conocida por bloquear bots (BCP)
pasa a extraer documentos donde antes daba 403.

**Decisión pendiente que este bloque cierra.** Si el reintento se activa por
defecto para todas las fuentes o solo para las marcadas. Se decide **con los
datos de la etapa C**, no antes — es justamente lo que `docs/decisiones.md`
deja abierto en D-03.

**Estimado.** 70 min.

**Commit.**
```
feat: reintento con navegador real ante 403 del fetcher simple

- solo tras un 403, no en toda corrida: el render es caro
- registrado en la auditoría como resuelto vía headless
- verificado contra una fuente que bloquea clientes HTTP simples
```

---

## B-24 · Calibración de profundidad/páginas por tamaño real

**Objetivo.** Reemplazar los `max_depth`/`max_pages` puestos a mano por
valores derivados del tamaño real de cada sitio.

**Entradas.** Etapa C completa — los datos de cuántas páginas tiene realmente
cada fuente salen de esas corridas.

**Criterio de aceptación.** Al menos una fuente grande (candidatas: BCB, ASFI)
extrae más documentos con el límite calibrado que con el conservador, y la
diferencia se reporta con ambas cifras. Sin ese antes/contra/después, la
calibración es una hipótesis.

**Estimado.** 60 min.

**Commit.**
```
feat: calibra profundidad y páginas según el tamaño real de cada sitio

- los límites salen de las corridas de la etapa C, no de un valor único
- antes/después medido en las fuentes grandes
```

---

# ETAPA E · Sostenimiento

100% no es un estado que se alcanza una vez: `sicsantacruz.com` pasó de
"confianza alta" a dominio de parking en seis días.

---

## B-25 · Script de re-verificación de Track A

**Objetivo.** Detectar automáticamente cuando una URL que estaba en 200 deja
de estarlo.

**Criterio de aceptación.** Corrido dos veces seguidas sin cambios en la web
no produce ninguna alerta (sin falsos positivos), y contra una URL rota a
propósito sí la produce. Las dos comprobaciones, no solo la segunda.

**Estimado.** 50 min.

**Commit.**
```
feat: re-verificación periódica de conectividad del catálogo

- detecta regresiones de URLs que estaban en 200 y dejaron de estarlo
- verificado en ambos sentidos: sin cambios no alerta, con una URL rota sí
```

---

## B-26 · Reporte de cobertura reproducible

**Objetivo.** Que el estado de cobertura sea un comando, no una recopilación
manual.

**Criterio de aceptación.** El comando emite las dos métricas de D-04 por
separado (Track A y Track B) con los números calculados de los datos, y
reproduce las cifras conocidas al correrlo sobre el estado actual.

**Estimado.** 45 min.

**Commit.**
```
feat: reporte de cobertura reproducible por comando

- Track A y Track B medidos por separado, según D-04
- las cifras salen de los datos, no de una recopilación a mano
```

---

## B-27 · Cierre

**Objetivo.** Dejar el proyecto legible para quien llegue después.

**Pasos.** Actualizar `README.md` con el estado final, refrescar el artifact
publicado, marcar las fases cerradas en `docs/plan_cobertura_100.md`, y
completar la columna **Real** de las tablas de seguimiento de este documento
con los desvíos anotados.

**Criterio de aceptación.** Alguien que no estuvo en ninguna sesión puede leer
`CLAUDE.md` → `docs/decisiones.md` → este archivo y saber qué se hizo, por
qué, y qué falta — sin preguntar.

**Estimado.** 40 min.

**Commit.**
```
docs: estado final de cobertura y cierre de los bloques ejecutados

- README con las cifras medidas de Track A y Track B
- columna Real del plan de bloques completa, con los desvíos anotados
```

---

## Qué NO está en este plan, a propósito

- **Los 23 archivos de SPIM con señal de atención vigente** (BCB×10, BCRP×3,
  BBV×2…). No es trabajo de este pipeline: requiere coordinación con el
  equipo que opera SPIM.
- **Reescribir el motor de extracción.** Funciona — 175 documentos reales
  extraídos de FINRURAL lo demuestran. Lo que falta es configuración y
  cobertura, no arquitectura.
- **Migrar la lógica PL/pgSQL de SPIM** (`asignar()`, `log_file_alert()`,
  `moda()`). Es un proyecto aparte, no un bloque.
