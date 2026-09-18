# Método de trabajo con dos asistentes de IA

Cómo trabajar un proyecto con **Claude** (planifica, decide, audita) y
**Antigravity** (ejecuta), sin que el costo de coordinación se coma el
ahorro y sin que nadie tenga que confiar en la palabra del otro.

Este documento es **portable**: está escrito para copiarse a un proyecto
nuevo. Todo lo que dice salió de haberlo hecho mal primero — cada regla
tiene detrás un incidente concreto, y están citados para que se entienda
por qué existen.

---

## 1. Por qué dos asistentes, y cómo se reparte

No es por capacidad, es por **economía de contexto**. El trabajo repetitivo
con criterio ya definido —generar configuración, correr procesos, commitear,
extraer datos— no necesita el historial acumulado de decisiones. Lo que sí lo
necesita es decidir qué hacer cuando algo es ambiguo.

| Tipo de trabajo | Quién | Por qué |
|---|---|---|
| Ejecución con criterio de aceptación escrito | **Antigravity** | El criterio ya existe; ejecutar no requiere el historial |
| Diagnóstico técnico (leer código, encontrar la causa) | **Antigravity** | Es acotado y verificable |
| Escribir scripts de soporte | **Antigravity**, diseño revisado | El código es directo; lo sutil es qué **no** debe hacer |
| Decidir entre dos opciones razonables | **Claude** | Queda fijado en el proyecto; necesita el historial |
| Aceptar o rechazar algo como "verificado" | **Claude** | Es donde los proyectos se equivocan más |
| Escribir o completar el registro de decisiones | **Claude** | Es el artefacto de más larga vida |
| Auditar entregas | **Claude** | Ver §4 |

**Regla que resume todo:** *Antigravity ejecuta y diagnostica; Claude decide
lo que tendrá consecuencias después de que el bloque cierre.*

---

## 2. Los archivos que hacen que funcione

Sin estos, el arreglo no se sostiene: sin criterio escrito de antemano, la
auditoría es opinión contra opinión y cuesta más que hacer el trabajo.

```
CLAUDE.md                    Reglas del proyecto + tabla de errores ya cometidos
AI_LOG.md                    Bitácora de incidentes, con el razonamiento
docs/
  decisiones.md              D-01..D-NN: contexto, alternativa, razón, UMBRAL
  plan_bloques.md            Los bloques: pasos, criterio de aceptación, commit
  protocolo_equipo.md        El reparto, formato de entrega, condiciones de parada
  entregas/B-NN.md           Parte de Antigravity por bloque (evidencia pegada)
  auditorias/B-NN.md         Acta de Claude por bloque (veredicto + sondeo)
.claude/
  agents/*.md                Subagentes con alcance delimitado
  settings.json              Hook que corre la verificación rápida sola
```

**Por qué cada decisión lleva un "umbral que la reabriría":** sin eso una
decisión es una opinión y nadie sabe si sigue vigente. Con el umbral escrito,
meses después cualquiera puede comprobar si esa condición se cumplió.

---

## 3. La unidad de trabajo: el bloque

Un bloque **cierra con un commit y deja el repositorio en verde**. Si no
puede cerrar con un commit que se sostenga solo, está mal dimensionado.

Cada bloque se define **antes** de empezarlo con:

- **Objetivo** en una línea. Si necesita dos, hace dos cosas.
- **Entradas**: qué debe existir antes. Si falta, el bloque está bloqueado y
  se salta — no se empieza a medias.
- **Pasos**: comandos reales, copiables. No descripciones.
- **Criterio de aceptación**: cómo se comprueba, verificando el **efecto** y
  no el artefacto.
- **Estimado**.
- **Commit**: el mensaje exacto con el que cierra.

> **Recomendación aprendida:** al planificar los bloques a partir del estado
> del repositorio, mirá los archivos **modificados y los no rastreados**. En
> este proyecto la primera etapa solo asignó bloques a los modificados y
> quedaron ~1.550 líneas sin dueño, incluidos dos módulos completos del
> núcleo. Hubo que agregar un bloque a mitad de camino.

---

## 4. La auditoría

### Quién audita

**Claude, no un subagente del que ejecutó.** Dos razones:

1. Un auditor con las mismas anteojeras no audita. El valor de delegar una
   revisión no es que el revisor sepa más, sino que **no tiene el contexto de
   haber escrito el código**.
2. La auditoría necesita el historial de fracasos: saber qué falló antes es
   lo que hace mirar el campo correcto.

### Cómo se audita sin quemar el ahorro

**No releyendo el repositorio.** Se leen tres cosas:

1. `docs/entregas/B-NN.md` — el parte.
2. `git show --stat <hash>` — qué archivos tocó realmente, para contrastar
   con lo que el parte declara.
3. **Un sondeo**: un detalle concreto, distinto en cada bloque, verificado de
   forma independiente.

El sondeo es lo que hace que la auditoría valga. Ejemplos reales de este
proyecto, todos de uno o dos comandos:

- Comparar la huella digital de un archivo copiado contra el original.
- Probar el fix contra 7 casos que los tests no cubren.
- Reproducir la verificación en un worktree **propio**, no el del ejecutor.
- Intentar descargar el documento que el reporte dice que existe.
- Mirar el desglose de un conteo y preguntarse qué es cada cosa.

### Veredictos

| Veredicto | Significa | Después |
|---|---|---|
| **Aprobado** | Criterio cumplido, evidencia real | Siguiente bloque |
| **Aprobado con observaciones** | Cierra, pero queda algo anotado | Se anota y sigue |
| **Devuelto** | La evidencia no sostiene el criterio | Se corrige **solo lo señalado**, no se rehace el bloque |

---

## 5. La regla de la evidencia, y por qué es la más frágil

**La evidencia se pega cruda. No se describe, no se reformatea.**

Es la única cosa sobre la que descansa todo el arreglo: permite que auditar
cueste tres comandos en vez de rehacer el trabajo.

**Se rompió dos veces en este proyecto**, ambas con el resultado de fondo
correcto —lo que las hace más difíciles de detectar, no menos—. Se
descubrieron por anomalías de forma antes que de fondo:

- Identificadores de test sin el prefijo de su archivo, algo que la
  herramienta no puede emitir.
- Porcentajes de progreso que retrocedían (75% → 66%), cuando solo
  incrementan.
- Una salida en inglés sin separadores, pegada bajo un comando que imprime
  en español con separadores.

> **Recomendación que funcionó mejor que exigir disciplina:** pedir la salida
> **corta** (`pytest -q` en vez de `-v`). El problema no era mala fe sino una
> salida larga que invitaba a ser "ordenada". Bajar la fricción resultó
> mejor que subir la exigencia. *Cuando una regla se rompe por fricción,
> bajá la fricción antes que subir la vigilancia.*

---

## 6. Condiciones de parada

El ejecutor **para y escala** —no decide— cuando:

| Situación | Por qué |
|---|---|
| Hay que escribir o completar el registro de decisiones | Es el artefacto de más larga vida. La propuesta va al parte, no al commit |
| No se puede verificar algo por su contenido | Es donde los proyectos aceptan datos equivocados |
| No entiende un diff o un bloque de código | Commitear a ciegas es cómo entra un bug silencioso |
| Algo contradiría una decisión cerrada | Se reabre con una entrada nueva, no en silencio |
| Un test falla y el arreglo no es obvio al primer intento | Dos intentos sobre una hipótesis equivocada cuestan más que aislar el caso |
| Haría falta borrar datos o archivos no previstos | Irreversible |
| Un bloque se pasa más del 50% del estimado | No para: anota la razón y sigue |

---

## 7. Los errores que más costaron, y la regla que dejó cada uno

Esta es la sección que más vale copiar a un proyecto nuevo. **Todos son de la
misma familia: algo que parece correcto, no produce ningún error, y no hace
lo que se cree.**

### 7.1 La verificación medía otra cosa

El paquete estaba instalado en modo editable apuntando al repositorio, así
que **toda corrida de pruebas importaba el árbol de trabajo, no lo
commiteado**. Tres bloques se verificaron contra el borrador creyendo que
verificaban lo guardado. La primera verificación del auditor tampoco fue
válida, por lo mismo.

> **Regla:** todo bloque que commitea código verifica contra un checkout
> limpio del commit, con la ruta de importación forzada explícitamente.
> ```bash
> git worktree add --detach /tmp/wt HEAD
> cd /tmp/wt && PYTHONPATH=$PWD/src <comando de pruebas>
> cd - && git worktree remove --force /tmp/wt
> ```
> Sin forzar la ruta, el worktree también importa el paquete instalado y la
> verificación vuelve a mentir. **Adoptalo desde el día uno**, no después de
> que muerda.

### 7.2 Agregar un archivo entero cuando el árbol está sucio

Un paso del plan decía `git add <archivo>`. Ese archivo tenía 54 líneas
pendientes de otra sesión, que viajaron de polizón y dejaron el repositorio
roto: pruebas commiteadas que usaban código sin commitear.

> **Regla:** con el árbol sucio, `git add -p` y aceptar solo los fragmentos
> del bloque. La prohibición de `git add -A` aplica igual a nivel de archivo.

### 7.3 Una instrucción específica basada en un supuesto no verificado

Se indicó que cierta configuración "naciera con la opción de renderizado
activada". El ejecutor lo hizo exactamente. El problema: **ese mecanismo no
existía** — la bandera no la leía nadie. El resultado fue una configuración
que parece correcta y no hace nada.

> **Regla:** antes de instruir el uso de una bandera, opción o API,
> comprobá que el código la consume (`grep` alcanza).
>
> **Y la lección más incómoda:** *una instrucción específica y equivocada es
> peor que una vaga*, porque su especificidad desalienta la pregunta. Nadie
> cuestiona un "activá la opción X" que suena como si quien lo pide supiera
> que X existe.

### 7.4 Una salvedad que se pierde al citar

Una afirmación escrita con su salvedad explícita —"es probable, sin
verificar"— fue citada de documento en documento y llegó al plan como hecho
establecido. **Pasó dos veces**: con una cifra heredada y con una relación
institucional supuesta.

> **Regla:** marcá el estado de cada afirmación de forma que **sobreviva al
> copiado**, no en una frase aclaratoria aparte:
> `[VERIFICADO 2026-09-18]`, `[PROBABLE — SIN VERIFICAR]`, `[REFUTADO]`.
>
> Distinguí tres estados, no dos: confirmado, refutado y **sin evidencia**.
> Retirar algo a "sin evidencia" no es declararlo falso.

### 7.5 Responder 200 no es servir

Se encontró un portal que responde correctamente y lista 40 documentos. Al
intentar la descarga: cero bytes. Usarlo habría subido la métrica apoyándose
en una fuente de la que no sale nada.

> **Regla:** verificá el **artefacto final**, no el enlace. Descargá y mirá
> los primeros bytes (`%PDF`, `PK\x03\x04`). Un enlace que existe no es un
> documento que se obtiene.
>
> El contraejemplo también importa: en un caso posterior, la misma prueba
> confirmó que sí se podía, y por eso se aprobó. **La diferencia no fue de
> criterio sino de hecho verificado.**

### 7.6 Un número correcto que cuenta la cosa equivocada

Un reporte informaba 257 recursos procesados con 0 errores. Eran ciertos. La
mitad eran archivos de checksum de 89 bytes, no documentos.

> **Regla:** definí la **unidad de medida** antes de construir el reporte, y
> hacé que el reporte distinga las categorías que importan. "Recursos" y
> "documentos" no son lo mismo, y la métrica de aceptación debe usar la
> segunda.
>
> Es el más difícil de detectar de todos: no falla ninguna verificación.
> Solo se ve mirando el desglose y preguntándose qué es cada cosa.

### 7.7 La verificación que nadie ejecuta

La suite de pruebas tardaba 65 minutos, así que nadie la corría antes de
commitear — que equivale a no tener verificación. Dos tests escapaban su
propio mock y salían a la red real, **consumiendo cuota de una API de pago
sin aparecer en ningún registro**.

> **Regla:** una verificación rápida que se ejecuta siempre vale más que una
> completa que nadie corre. Separá lo lento con una etiqueta y dejá lo rápido
> por debajo de ~15 segundos, enganchado a un hook automático.
>
> **Y verificá que la salvaguarda pueda fallar:** rompé algo a propósito y
> comprobá que se pone en rojo. Una salvaguarda que nadie vio fallar no es
> una salvaguarda.

### 7.8 Reglas de exclusión que excluyen de más, en silencio

Una regla de `.gitignore` demasiado amplia dejó fuera un archivo necesario.
Peor: el intento de corregirla **no hizo nada y no dio ningún error**, porque
no se puede re-incluir un archivo si su carpeta padre está excluida entera.

> **Regla:** después de tocar reglas de exclusión, comprobá el efecto sobre
> archivos concretos (`git check-ignore -v <archivo>`), no asumas que la
> regla funcionó.

### 7.9 Lo que se ignora puede ser el entregable

La carpeta de resultados estaba ignorada entera, y adentro vivían el catálogo
curado y el registro de auditoría — o sea, **todo el resultado del trabajo
existía solo en el disco de una máquina**.

> **Regla:** revisá qué hay dentro de lo que ignorás. Los datos curados no
> son artefactos de corrida: versionalos, aunque estén en la misma carpeta.

---

## 8. Sobre las estimaciones

Los bloques de "commitear trabajo ya escrito" salieron sistemáticamente
~50% por debajo de lo estimado. Los de trabajo real, no.

> **Recomendación:** no recalibres el plan entero con los primeros datos —
> vienen del tipo de bloque más barato. Esperá a tener datos de bloques con
> trabajo de verdad. Y anotá en la bitácora cualquier desvío mayor al 50%,
> con la razón: la próxima estimación del mismo tipo depende de eso.

---

## 9. El ciclo, en concreto

```
1. Claude asigna el siguiente bloque (o el ejecutor toma el siguiente de la tabla)
2. Antigravity: árbol limpio → ejecuta → corre el criterio de aceptación →
   commitea → escribe docs/entregas/B-NN.md con la evidencia pegada
3. Claude: lee el parte + git show --stat + un sondeo independiente → veredicto
4. Aprobado → siguiente bloque
   Devuelto → se corrige solo lo señalado
5. Cada 4-5 bloques: actualizar la columna "Real" del plan y la bitácora
```

**Para no pisarse:** un bloque, un dueño, a la vez. Mientras el ejecutor
tiene un bloque abierto, el auditor no edita código ni datos — solo escribe
en `docs/auditorias/` y en la bitácora. El commit es la señal de entrega.

**Los bloques compartidos se parten en dos commits**, no en uno: el de la
ejecución mecánica y el de la decisión. Así el historial muestra dónde entró
el criterio.

---

## 10. Lo que haría distinto desde el día uno

1. **Adoptar la verificación contra checkout limpio desde el primer bloque**,
   no después de descubrir que tres verificaciones no medían nada.
2. **Definir la unidad de medida de cualquier métrica antes de construir el
   reporte** que la muestra.
3. **Convención de estado de afirmación** (`[VERIFICADO]` / `[PROBABLE]` /
   `[SIN VERIFICAR]`) desde el primer documento, para que sobreviva al
   copiado entre archivos.
4. **Pedir salida corta de las herramientas** desde el principio, para no
   invitar a reformatear.
5. **Verificar que existe el mecanismo antes de instruir su uso.** Un `grep`
   de treinta segundos habría evitado un bloque entero de trabajo inerte.
6. **Planificar mirando archivos modificados y no rastreados**, no solo los
   primeros.
7. **Escribir el criterio de aceptación en términos del efecto** desde el
   inicio: "≥1 documento descargado y verificado", no "≥1 recurso
   encontrado".
