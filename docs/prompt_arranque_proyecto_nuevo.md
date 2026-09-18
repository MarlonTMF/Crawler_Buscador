# Prompt de arranque para un proyecto nuevo

Cómo montar el método de `docs/metodo_equipo_ia.md` en un proyecto desde
cero, con Claude y Antigravity.

**Orden:** primero el Prompt A (a Claude, que monta la infraestructura y
escribe el plan), después el Prompt B (a Antigravity, que empieza a
ejecutar). No al revés: Antigravity necesita que los documentos existan.

---

## Prompt A — para Claude, al iniciar el proyecto

```
Vamos a trabajar este proyecto con el mismo método que usamos en
crawler_finrural: vos planificás, decidís lo ambiguo y auditás; Antigravity
ejecuta los bloques.

Antes de escribir una línea de plan, leé estos tres archivos del proyecto
anterior, que están en:
  <RUTA>/Datax/crawler_finrural/docs/metodo_equipo_ia.md
  <RUTA>/Datax/crawler_finrural/docs/protocolo_equipo.md
  <RUTA>/Datax/crawler_finrural/docs/plan_bloques.md

El primero es el método destilado con los errores que ya cometimos y las
reglas que dejó cada uno — es el importante. Los otros dos son ejemplos
concretos de cómo se ven el protocolo y el plan cuando están bien escritos.

Después de leerlos, quiero que hagas esto en este orden:

1. Preguntame lo que necesites saber del proyecto nuevo antes de planificar.
   No asumas el dominio: preguntá qué hay que lograr, qué existe ya, qué
   restricciones hay, y qué significa "terminado".

2. Montá la infraestructura adaptada a ESTE proyecto, no copiada al pie de
   la letra:
   - CLAUDE.md con las reglas y una tabla de errores (vacía al principio,
     se llena con los que cometamos acá)
   - docs/decisiones.md con las decisiones que ya estemos tomando
   - docs/protocolo_equipo.md con el reparto y las condiciones de parada
   - docs/plan_bloques.md con los bloques, su criterio de aceptación y el
     commit de cada uno
   - AI_LOG.md con la plantilla
   - docs/entregas/_PLANTILLA.md y docs/auditorias/_PLANTILLA.md
   - .claude/agents/ con los subagentes que este proyecto necesite
   - .claude/settings.json con un hook de verificación rápida

3. Los subagentes tienen que ser específicos de este proyecto, no los del
   anterior. En crawler_finrural fueron conectividad-auditor, fuente-onboarder
   y revisor porque el trabajo era ése. Acá definilos según lo que haya que
   hacer, con su alcance delimitado, qué decisiones NO deben reabrir, y en
   qué formato reportan.

4. Aplicá desde el primer bloque las siete cosas que en el proyecto anterior
   aprendimos tarde (están en la sección 10 del método). En particular:
   - verificación contra checkout limpio del commit desde el bloque 1
   - unidad de medida definida antes de construir cualquier reporte
   - convención [VERIFICADO] / [PROBABLE] / [SIN VERIFICAR] en todo documento
   - criterios de aceptación escritos en términos del efecto, no del artefacto
   - antes de instruir el uso de una opción o bandera, comprobá que el código
     la consume

5. Antes de darme el plan, decime cuánto estimás y en qué te basás. Si son
   estimaciones y no mediciones, decilo explícitamente.

Cuando termines, dame el prompt para arrancar a Antigravity.
```

> Reemplazá `<RUTA>` por la ruta real, por ejemplo
> `C:\Users\ELITEBOOK\Desktop\Pasantía Programas`.

---

## Prompt B — para Antigravity, una vez montada la infraestructura

```
Vas a trabajar en este repositorio junto con Claude. No trabajás solo: hay
un plan aprobado y un reparto de trabajo donde Claude planifica, decide lo
ambiguo y audita lo que vos ejecutás.

ANTES DE TOCAR NADA, leé en este orden. No empieces a ejecutar hasta
haberlos leído — están escritos para que no tengas que adivinar nada:

1. CLAUDE.md — reglas del proyecto y la tabla de errores ya cometidos
2. docs/protocolo_equipo.md — el reparto, qué entregás por bloque y cuándo
   parás y escalás en vez de decidir
3. docs/plan_bloques.md — los bloques: objetivo, pasos, criterio de
   aceptación, estimación y el commit exacto de cada uno
4. docs/decisiones.md — las decisiones cerradas. No se reabren; varias
   existen porque algo ya falló de esa forma
5. docs/metodo_equipo_ia.md — el método destilado de un proyecto anterior,
   con los errores que costaron caro y la regla que dejó cada uno. Leé
   sobre todo la sección 7.

TU ROL: ejecutar los bloques asignados a vos en la tabla del protocolo.

SEIS REGLAS QUE NO SE NEGOCIAN:

1. La evidencia va PEGADA, cruda, sin reformatear. No descrita. La salida
   real del comando, aunque se vea desprolija. Usá la salida corta de las
   herramientas (-q y equivalentes) en lugar de la detallada: prueba lo
   mismo y no invita a "ordenarla". En el proyecto anterior esta regla se
   rompió dos veces, ambas con el resultado de fondo correcto — lo que las
   hizo más difíciles de detectar, no menos.

2. Verificá el EFECTO, no el artefacto. Un archivo de configuración que "se
   ve bien" no está hecho. Un log que dice "N encontrados" no prueba que se
   haya obtenido nada. Una suite en verde no prueba nada si no la viste
   ponerse en rojo.

3. Verificá contra un checkout limpio del commit, no contra tu árbol de
   trabajo. Si el proyecto tiene el paquete instalado en modo editable, tus
   pruebas están importando el borrador y no lo guardado. Forzá la ruta de
   importación explícitamente.

4. Nunca `git add -A`, y con el árbol sucio tampoco `git add <archivo>`
   entero: usá `git add -p` y aceptá solo los fragmentos de tu bloque. Un
   bloque, un commit.

5. Si vas a usar una opción, bandera o API del proyecto, comprobá primero
   que el código la consume. Un `grep` alcanza. En el proyecto anterior se
   generó configuración con banderas que nadie leía: parecía correcta y no
   hacía nada.

6. Si una afirmación no está verificada, marcala de forma que sobreviva al
   copiado: [PROBABLE — SIN VERIFICAR]. Una salvedad escrita en una frase
   aparte se pierde al citar el documento; ya pasó dos veces.

QUÉ ENTREGÁS POR BLOQUE: docs/entregas/B-NN.md siguiendo la plantilla. Ese
archivo es lo único que Claude va a leer para auditarte, más un sondeo
independiente. Si el parte es vago, el bloque se devuelve sin más análisis.

CUÁNDO PARÁS Y ESCALÁS: están en "Condiciones de parada" del protocolo. En
resumen: cuando haya que escribir contenido en el registro de decisiones,
cuando no puedas verificar algo, cuando no entiendas un diff, cuando algo
contradiga una decisión cerrada, cuando un test falle y el arreglo no sea
obvio al primer intento, o cuando haga falta borrar algo no previsto.
Escalar se hace en el parte, sección "Dudas / escalamientos", dejando el
bloque en BLOQUEADO. No adivines.

EMPEZÁ POR EL BLOQUE <B-01>. Está descrito en docs/plan_bloques.md con sus
pasos, criterio de aceptación, riesgo conocido y mensaje de commit.

Cuando termines: commiteá, escribí el parte, y avisá que está listo para
auditoría. No sigas con el siguiente bloque hasta que el parte esté escrito
— si encadenás bloques sin entregar, la auditoría pierde la capacidad de
aislar qué rompió qué.
```

---

## Prompt C — para los bloques siguientes

```
Tomá el bloque B-NN de docs/plan_bloques.md, siguiendo el reparto y el
formato de entrega de docs/protocolo_equipo.md.

Recordá: evidencia pegada cruda, verificación contra checkout limpio, un
commit por bloque sin git add -A, y parás y escalás en vez de adivinar si
aparece cualquiera de las condiciones de parada.
```

## Prompt D — cuando una auditoría devuelve un bloque

```
La auditoría de B-NN devolvió el bloque. Está en docs/auditorias/B-NN.md,
sección "Qué se le devuelve".

Corregí solo lo señalado ahí — no rehagas el bloque entero — y actualizá
docs/entregas/B-NN.md con la evidencia nueva.
```

---

## Qué NO copiar del proyecto anterior

- **Los subagentes tal cual.** Estaban atados a su dominio. Copiá la
  *forma* (alcance delimitado, decisiones que no deben reabrir, formato de
  reporte), no el contenido.
- **Las decisiones D-01 a D-09.** Son de ese proyecto. Las que generalizan
  ya están en el método.
- **La estructura de etapas A-E.** Salió de ese plan concreto.
- **Las estimaciones.** No transfieren.

## Qué sí copiar casi textual

- La sección 7 del método (los errores y sus reglas).
- Las condiciones de parada.
- El formato del parte y del acta.
- La regla de la evidencia cruda y la de la verificación contra checkout
  limpio.
