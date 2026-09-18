# Protocolo de equipo — Claude + Antigravity

Cómo trabajamos dos asistentes sobre el mismo repositorio sin pisarnos, sin
duplicar esfuerzo y sin que el costo de coordinación se coma el ahorro.

**Plan que ejecutamos:** `docs/plan_bloques.md` (27 bloques, 5 etapas,
aprobado). Este documento no lo reemplaza ni lo modifica: dice **quién hace
cada bloque, qué entrega, y cómo se verifica**.

---

## Por qué dos asistentes

No es por capacidad, es por **economía de contexto**. El plan tiene 23 horas
estimadas y la etapa C —onboarding de 34 fuentes— se lleva 13 h 45 de trabajo
muy repetitivo: generar YAML, explorar un sitio, correr el crawler, leer
`inventory.db`, repetir. Ese trabajo no necesita el contexto acumulado de
decisiones, incidentes y umbrales; necesita constancia y verificación.

El contexto acumulado sí hace falta para lo otro: decidir si una URL
corresponde a la institución correcta, leer 341 líneas de diff que nadie
revisó, decidir cuándo una fuente deja de encajar en el modelo declarativo.

**Reparto en una frase:** Antigravity ejecuta el plan, Claude decide lo
ambiguo y audita lo ejecutado.

---

## Reparto por tipo de trabajo

| Tipo de trabajo | Quién | Por qué |
|---|---|---|
| Ejecución repetitiva con criterio de aceptación escrito | **Antigravity** | El criterio ya está definido; ejecutar y verificar no requiere el historial |
| Commits mecánicos de trabajo ya verificado | **Antigravity** | El contenido está listo, falta la higiene |
| Exploración de sitios, generación de YAML, corridas del crawler | **Antigravity** | Es el grueso del plan y es paralelizable |
| Escribir scripts de soporte (generador, runner) | **Antigravity**, diseño revisado por Claude | El código es directo; la sutileza está en qué **no** debe hacer |
| Aceptar o rechazar una URL como institución correcta | **Claude** | D-01 falló 4 veces acá. Requiere el historial de cómo falló |
| Leer diffs sin revisar y decidir qué hacer con ellos | **Claude** | Puede contener la causa de D-08; decidir "commitear o partir el bloque" es criterio |
| Clasificar ambigüedades del catálogo | **Claude** | "Cargar / duplicado / entrada interna" es una decisión, no una consulta |
| Cerrar una decisión abierta (D-03, D-07) | **Claude** | Va a `docs/decisiones.md` con umbral; es el artefacto de más larga vida |
| Auditar entregas | **Claude** | Ver abajo: la auditoría necesita ojos que no escribieron el código |
| Marcar una fuente como "no encaja en el modelo" | **Antigravity marca, Claude confirma** | Marcar es observación; decidir qué se hace con ella es criterio |

---

## Sobre los subagentes auditores

**El auditor es Claude, no un subagente de Antigravity.** Dos razones:

1. **Un auditor con las mismas anteojeras no audita.** La lección que dejó el
   proyecto anterior del equipo: el valor de delegar una revisión no fue que
   el revisor supiera más, sino que **no tenía el contexto de haber escrito
   el código**. Si Antigravity ejecuta y Antigravity audita, la revisión
   hereda exactamente los supuestos que habría que cuestionar.
2. **La auditoría necesita el historial de fracasos.** Saber que
   `sicsantacruz.com` pasó de "confianza alta" a parking en seis días, o que
   tres sugerencias de IA apuntaron a instituciones distintas, es lo que hace
   que un auditor mire el campo `matched_keywords` en vez del status 200.

Pero la auditoría **no se hace releyendo el repositorio** — eso quemaría
justamente los tokens que este arreglo quiere ahorrar. Se hace sobre el
**parte de entrega** (abajo), más un sondeo puntual.

Los tres subagentes de `.claude/agents/` (`conectividad-auditor`,
`fuente-onboarder`, `revisor`) son de Claude. Antigravity **no los invoca**,
pero **sí los lee**: `fuente-onboarder.md` es literalmente el manual de
operación de la etapa C y está escrito de forma agnóstica a la herramienta.

---

## Asignación bloque por bloque

Leyenda: 🅰️ Antigravity · 🅲 Claude · 🅰️→🅲 Antigravity ejecuta, Claude decide con el resultado

### Etapa A · Ordenar lo ya hecho (2 h 30)

| Bloque | Quién | Nota |
|---|---|---|
| B-01 · Higiene de `.gitignore` | 🅰️ | Copiar `Informe_Prospeccion_en_Cifras.html` a `docs/` **antes** de ignorar la carpeta: es la fuente de las cifras del benchmark |
| B-02 · Fix mailto:/tel: | 🅰️ | Código y prueba ya escritos. Verificar que la prueba falla sin el fix antes de commitear |
| B-03 · Tests `live` | 🅰️ | Incluye romper una aserción a propósito para ver la suite en rojo |
| B-04 · Resoluciones de URL | 🅰️ | Solo verificación de formato + commit. **No agregar resoluciones nuevas** |
| B-05 · Infraestructura (agentes, hook) | 🅰️ | Confirmar que el hook efectivamente se dispara |
| B-06 · Documentos | 🅰️ | Incluye este archivo |
| B-07 · Diff del fetcher (341 líneas) | 🅰️→🅲 | **Antigravity resume el diff, Claude decide.** Ver protocolo de resumen abajo |

### Etapa B · Cerrar Track A (2 h 20)

| Bloque | Quién | Nota |
|---|---|---|
| B-08 · Brecha de 13 fuentes | 🅰️→🅲 | Antigravity corre la consulta y lista la diferencia con nombres; Claude clasifica cada una |
| B-09 · FMI con headless | 🅰️→🅲 | Prueba mecánica; si el resultado es ambiguo (ni 200 limpio ni 403 claro), escala |
| B-10 · SICSANTACRUZ | 🅲 | Investigación de identidad institucional. Antigravity puede reunir candidatos, **no aceptarlos** |
| B-11 · Cerrar Track A | 🅰️→🅲 | Antigravity recalcula; Claude valida el número final antes de que entre al informe |

### Etapa C · Escalar Track B (13 h 45) — el grueso

| Bloque | Quién | Nota |
|---|---|---|
| B-12 · Generador de YAML | 🅰️ | Claude revisa el diseño antes del commit. Lo sutil: **no debe inventar reglas de clasificación**, tiene que dejarlas como TODO |
| B-13 · Runner por lotes | 🅰️ | Debe reproducir el resultado ya medido de FINRURAL (175 recursos, 0 errores) o no sirve |
| B-14 → B-22 · 9 lotes de onboarding | 🅰️ | **El trabajo duro.** Claude audita el parte de cada lote + sondea 1 fuente al azar |

### Etapa D · Calibración (2 h 10)

| Bloque | Quién | Nota |
|---|---|---|
| B-23 · Headless ante 403 | 🅲 decide criterio → 🅰️ implementa | La decisión (¿por defecto o solo marcadas?) cierra D-03 y necesita los datos de la etapa C |
| B-24 · Calibración de profundidad | 🅰️ | Requiere reportar antes/después con ambas cifras |

### Etapa E · Sostenimiento (2 h 15)

| Bloque | Quién | Nota |
|---|---|---|
| B-25 · Re-verificación de Track A | 🅰️ | Verificar en ambos sentidos: sin cambios no alerta, con URL rota sí |
| B-26 · Reporte reproducible | 🅰️ | |
| B-27 · Cierre | 🅲 | Requiere contar la historia completa: qué se hizo, por qué, qué falta |

**Cuenta:** 19 bloques íntegros para Antigravity, 2 para Claude, 6 compartidos.
Antigravity se lleva ~17 de las 23 horas estimadas.

---

## El parte de entrega

Antigravity cierra cada bloque escribiendo `docs/entregas/B-NN.md`. **Este
archivo es la superficie de auditoría**: Claude lee esto, no el repositorio
entero. Si el parte es vago, el bloque se devuelve sin más análisis.

```markdown
# B-NN · <título del bloque>

- **Ejecutado por:** Antigravity
- **Fecha:** YYYY-MM-DD
- **Estimado:** NN min · **Real:** NN min · **Desvío:** +/- NN%
- **Commit:** <hash corto> — <primera línea del mensaje>

## Qué se hizo
Dos o tres frases. Qué cambió en el repositorio.

## Criterio de aceptación — evidencia
El criterio, copiado del plan, y debajo la **salida real** del comando que lo
verifica. Pegada, no parafraseada. Si el criterio pedía ver algo fallar,
va la salida de la corrida en rojo *y* la de la corrida en verde.

```
$ comando exacto
salida real, sin editar
```

## Desviaciones del plan
Qué se hizo distinto de lo escrito, y por qué. "Ninguna" es una respuesta
válida y frecuente.

## Dudas / escalamientos
Lo que no se decidió porque no correspondía decidirlo. Vacío si no hubo.

## Estado
LISTO PARA AUDITORÍA | BLOQUEADO: <razón>
```

**Regla sobre la evidencia:** se pega la salida real del comando. Una
descripción de la salida ("los tests pasaron") no es evidencia — el proyecto
ya tiene cuatro incidentes registrados donde algo "parecía" correcto y no lo
era.

---

## Protocolo de auditoría

Claude audita leyendo **tres cosas**, no el repositorio:

1. `docs/entregas/B-NN.md` — el parte.
2. `git show --stat <hash>` — qué archivos tocó realmente, para contrastar
   con lo que el parte dice que tocó.
3. **Un sondeo**: un detalle concreto elegido por el auditor, distinto en cada
   bloque. En un lote de onboarding, abrir el `inventory.db` de **una** fuente
   al azar y confirmar que los recursos son documentos reales y no páginas de
   navegación.

### Veredictos

| Veredicto | Qué significa | Qué pasa después |
|---|---|---|
| **APROBADO** | Criterio cumplido, evidencia real, sin desviaciones que importen | Siguiente bloque |
| **APROBADO CON OBSERVACIONES** | El bloque cierra, pero queda algo anotado para después | Se anota en `AI_LOG.md` y sigue |
| **DEVUELTO** | La evidencia no sostiene el criterio | Vuelve a Antigravity con la razón concreta. No se rehace el bloque entero: se corrige lo señalado |

### Qué hace fallar una auditoría

- Evidencia parafraseada en vez de salida real.
- Criterio de aceptación "cumplido" sin el comando que lo demuestra.
- Una URL aceptada sin `reason` y `matched_keywords` (D-01).
- Una fuente marcada como onboardeada citando el log de consola
  ("se descubrieron N candidatos") en vez de `inventory.db`.
- `git add -A` en el historial, o un commit que mezcla dos bloques.
- Un número que no se puede reproducir corriendo el comando del parte.

---

## Verificación contra HEAD limpio

**Todo bloque que commitea código Python verifica contra un checkout limpio de
HEAD, no contra el árbol de trabajo.**

Motivo, descubierto auditando B-03: el paquete `crawler` está instalado en
modo editable apuntando a este repositorio, así que **cualquier** corrida de
pytest en esta máquina importa el árbol de trabajo, sin importar desde dónde
se ejecute. Un `52 passed` local no dice nada sobre lo que quedó commiteado.
B-03 dejó HEAD con 2 tests rotos y las tres verificaciones del parte salieron
en verde.

```bash
git worktree add --detach /tmp/wt_head HEAD
cd /tmp/wt_head && PYTHONPATH=$PWD/src python -m pytest tests/ -q -m "not live"
cd - && git worktree remove --force /tmp/wt_head
```

El `PYTHONPATH` es lo que hace la diferencia: sin él, el worktree también
importa el paquete instalado y la verificación vuelve a mentir. Esa salida va
pegada en el parte.

No aplica a bloques que solo tocan datos o documentación.

---

## Reglas que ninguno de los dos negocia

Están en `CLAUDE.md` y `docs/decisiones.md`. Las cuatro que más van a
aparecer durante la ejecución:

1. **D-01 · Ninguna URL se acepta solo por status 200.** Falló cuatro veces.
   Si un candidato responde pero su contenido no menciona palabras clave
   específicas de la institución, queda como `reachable_unverified`, no como
   resuelto.
2. **D-07 · YAML declarativo, no adaptador Python.** Si una fuente no encaja,
   se marca y se sigue. Forzarla adentro del modelo genérico es peor que
   dejarla afuera.
3. **Verificar el efecto, no el artefacto.** Un YAML que "se ve bien" no está
   hecho; un log que dice "candidatos descubiertos" no prueba descarga.
4. **Nunca `git add -A`.** Hay trabajo de varias sesiones mezclado en el
   árbol. Cada commit agrega sus archivos por nombre.

---

## Condiciones de parada

Antigravity **para y escala a Claude** —no decide— cuando:

| Situación | Por qué para |
|---|---|
| Hace falta escribir o completar contenido de `docs/decisiones.md` (incluido un umbral faltante en una decisión ya cerrada) para que un bloque cumpla su propio criterio | Es el artefacto de más larga vida del proyecto. La propuesta va en "Dudas / escalamientos" del parte, no directo al commit — aunque el texto parezca de bajo riesgo (ver B-06, donde salió bien pero no debió decidirse sola) |
| Un candidato de URL no se puede verificar por contenido | Es exactamente donde el proyecto falló 4 veces (D-01) |
| Un diff o un bloque de código que no entiende | Commitear a ciegas es cómo entra un bug silencioso |
| Una fuente no encaja en el modelo declarativo | Marcarla es observación; qué hacer con ella es criterio (D-07) |
| Algo que contradiría una decisión D-01 a D-08 | Las decisiones cerradas se reabren con una entrada nueva, no en silencio |
| Un test falla y el arreglo no es obvio en un intento | Dos intentos basados en una hipótesis equivocada cuestan más que aislar el caso |
| Haría falta borrar datos o archivos no previstos en el plan | Irreversible |
| Un bloque se pasa más del 50% del estimado | No para el trabajo: anota la razón en `AI_LOG.md` y sigue |

Escalar se hace **en el parte**, sección "Dudas / escalamientos", y dejando el
bloque en estado `BLOQUEADO`. No se adivina.

---

## Cómo no pisarnos

- **Un bloque, un dueño, a la vez.** Mientras Antigravity tiene un bloque
  abierto, Claude no edita archivos de código ni de datos; solo escribe en
  `docs/auditorias/` y `AI_LOG.md`.
- **El commit es la señal de entrega.** Antigravity commitea y escribe el
  parte; a partir de ahí el bloque es de Claude hasta el veredicto.
- **Antes de empezar un bloque, `git pull`/`git status`.** Si el árbol tiene
  cambios que el parte anterior no menciona, parar y preguntar.
- **Los bloques 🅰️→🅲 se parten en dos commits**, no en uno: el de la
  ejecución mecánica y el de la decisión. Así el historial muestra dónde
  entró el criterio.

---

## El ciclo, en concreto

```
1. Claude asigna el siguiente bloque (o Antigravity toma el siguiente de la tabla)
2. Antigravity: git status limpio → ejecuta el bloque → corre el criterio
   de aceptación → commitea → escribe docs/entregas/B-NN.md
3. Claude: lee el parte + git show --stat + un sondeo → veredicto
4. APROBADO → siguiente bloque
   DEVUELTO → Antigravity corrige solo lo señalado
5. Cada 4-5 bloques: Claude actualiza la columna "Real" de
   docs/plan_bloques.md y el artifact publicado
```

**Lo que hace que esto funcione y no sea burocracia:** cada bloque del plan ya
tiene un criterio de aceptación verificable escrito **antes** de empezar. Sin
eso, la auditoría sería opinión contra opinión y costaría más que hacer el
trabajo.
