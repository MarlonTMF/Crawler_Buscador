# Plan de bloques — Fase 4: vigencia, huecos y recuperación

Continuación de `docs/plan_bloques_fase2.md` (B-28 a B-40) y de la Fase 3
(B-41 a B-48). Esta fase cubre **B-50 a B-58**.

Origen: notas de la reunión de Marlon del 2026-09-23. **Alcance acotado a tres
portales: BCB, INE y ASFI.** Ninguna otra fuente entra en esta fase.

---

## Qué pidió la reunión, traducido a capacidades

Las notas piden seis cosas que en realidad son cuatro capacidades encadenadas:

| Nota de la reunión | Capacidad |
|---|---|
| «si la fuente es diaria y se ha atrasado un mes, tal vez cambió de link» | Detectar atraso |
| «falta febrero, aparece abril — cómo manejar los casos faltantes» | Detectar huecos |
| «fuentes que no se pueden actualizar se vayan al histórico» | Ciclo de vida de la fuente |
| «reportes perdidos y atrasados deben poder recuperarse» | Recuperación |
| «a veces las mueven; a veces ya no existe y requiere búsqueda de herencia» | Recuperación por migración |
| «cruce de datos del crawler externo con el interno» | Conciliación |
| «las DB de DataX deben estar al día» | Consecuencia de todo lo anterior |

**Las cuatro dependen de una sola cosa que hoy no funciona: saber a qué
período pertenece cada documento.** No se puede detectar que falta febrero si
no se sabe de qué mes es cada archivo. Por eso la Etapa J va primero y todo lo
demás depende de ella.

---

## El hallazgo que ordena la fase

Medido el 2026-09-23 sobre las tres bases:

```
bcb    121 filas ->   4 con período  (3%)   · 117 'unknown'
ine    443 filas ->   2 con período  (0.5%) · 441 'unknown'
asfi   601 filas -> 154 con período  (26%)  ·  62 'unknown', 385 'low'
```

La causa es concreta. `extractor.py` tiene tres capas de extracción de fecha,
pero el patrón genérico de la capa 1 reconoce **únicamente** `_MM_AAAA`:

```python
gen_match = re.search(r"_(?P<m>0[1-9]|1[0-2])_(?P<y>20\d{2})\b", url)
```

Contando los patrones reales que publican los tres portales:

| Portal | Patrón dominante | URLs | ¿Reconocido hoy? |
|---|---|---:|:---:|
| ASFI | `/AAAA-MM/` | 582 de 601 | **no** |
| BCB | `/AAAA/MM/` | 75 de 121 | **no** |
| BCB | `_MM_AAAA` | 1 de 121 | sí |
| INE | solo año | 220 de 443 | **no** |
| INE | sin fecha en la URL | 223 de 443 | no aplica |

El formato soportado cubre **1 URL de 1.165**. No es que la extracción de
fechas falle: es que está mirando un patrón que estos portales no usan.

### La distinción que hay que respetar

En `https://www.asfi.gob.bo/sites/default/files/2026-06/MEMORIA_2025.pdf`, el
`2026-06` de la carpeta es **cuándo se publicó**, y `2025` en el nombre es **de
qué período habla el documento**. Son cosas distintas y el esquema ya las
separa (`published_at` frente a `period_start`).

Confundirlas rompería justamente lo que la reunión pide: una memoria de 2025
publicada en 2026-06 se contaría como documento del período 2026-06, y el
detector de huecos reportaría que falta 2025 cuando está ahí.

**Regla para la Etapa J:** la fecha de la carpeta alimenta `published_at`; la
del nombre del archivo alimenta `period_start`. Cuando solo hay una, se asigna
a lo que corresponda y la confianza baja a `medium` o `low`, nunca `high`.

### INE es un problema distinto

Sus URLs son `descarga/wpfdcat/277/planes-estrategicos-institucionales`: no
llevan fecha. Para INE no sirve la capa 1 y hay que apoyarse en las capas 2
(texto del enlace y su contexto) y 3 (cabeceras HTTP). Es más trabajo y menos
seguro, y el plan lo trata como un bloque aparte.

Además, **440 de sus 443 filas están clasificadas como
`planes_estrategicos`**. Sin datasets bien separados no se puede declarar una
periodicidad por dataset, que es lo que la Etapa K necesita.

---

## Etapa J — Saber de cuándo es cada documento

Prerequisito de toda la fase. Sin esto, las etapas K, L y M no se pueden
construir.

### B-50 · Ampliar la extracción de fecha a los patrones reales — Antigravity — 100 min

**Objetivo.** Que el motor reconozca los formatos que BCB y ASFI publican de
verdad.

**Pasos.**
1. Agregar a la capa 1 los patrones medidos: `/AAAA-MM/`, `/AAAA/MM/`,
   `AAAAMM_`, `DDmesAAAA` y año suelto.
2. Implementar la separación `published_at` / `period_start` descrita arriba,
   con su nivel de confianza.
3. **Ver fallar los tests antes del arreglo** — regla del proyecto, aplicada en
   D-06 y no negociable acá.

**Criterio de aceptación.** Sobre las corridas existentes, sin volver a
rastrear: ASFI ≥ 85% de filas con `period_start` o `published_at` resuelto
(hoy 26%) y BCB ≥ 65% (hoy 3%). Ninguna fila con `confidence: high` cuya fecha
provenga solo de la carpeta de publicación.

**Commit.** `feat: reconoce los patrones de fecha que los portales usan de verdad`

---

### B-51 · Fechas de INE y corrección de sus datasets — Antigravity — 110 min

**Objetivo.** INE no expone fechas en la URL y tiene 440 de 443 documentos en
un solo dataset. Las dos cosas hay que resolverlas juntas porque la
periodicidad se declara por dataset.

**Pasos.**
1. Apoyarse en las capas 2 y 3 para las fechas, y medir cuánto rinde cada una.
2. Reescribir las `dataset_rules` de `config/source_ine.yaml` según lo que el
   portal publica realmente.

**Criterio de aceptación.** Ningún dataset de INE concentra más del 40% de las
filas, salvo que se justifique por escrito con evidencia del portal. Al menos
el 50% de las filas con período o fecha de publicación resuelta.

**Si las capas 2 y 3 no alcanzan**, el resultado válido es reportarlo con la
medición, no forzar una heurística que invente fechas. Una fecha inventada es
peor que ninguna: contamina el detector de huecos.

**Commit.** `feat: fechas y clasificacion de datasets para ine`

---

## Etapa K — Detectar atraso y huecos

### B-52 · Declarar la periodicidad esperada — Antigravity — 60 min

**Objetivo.** El sistema no puede saber que falta febrero si no sabe que la
serie es mensual.

**Pasos.** Agregar a cada dataset de los tres YAML su periodicidad declarada
(`diaria`, `semanal`, `mensual`, `trimestral`, `semestral`, `anual`, `eventual`)
y la tolerancia de atraso en períodos. Es configuración declarativa, en la
línea de D-07: nada de lógica por fuente en Python.

**Criterio de aceptación.** Los tres portales con periodicidad declarada en
todos sus datasets, y la periodicidad declarada **contrastada contra lo
observado** — si un dataset declarado mensual tiene 3 documentos en 5 años, la
declaración está mal y se corrige.

**Commit.** `feat: declara periodicidad y tolerancia por dataset`

---

### B-53 · Calendario de períodos esperados contra observados — Antigravity — 110 min

**Objetivo.** El corazón de lo que pidió la reunión: «falta febrero, aparece
abril».

**Pasos.** Un comando que, por dataset, genere los períodos esperados entre el
primero observado y hoy, los cruce con los observados y produzca tres salidas:
huecos intermedios, atraso desde el último período, y estado del dataset.

Estados: `AL_DIA`, `ATRASADO`, `CON_HUECOS`, `INACTIVO`.

**La tolerancia depende de la periodicidad.** Una fuente diaria atrasada un mes
es una alarma; una anual atrasada un mes es normal. Esa es literalmente la
primera nota de la reunión.

**Criterio de aceptación.** Reporte reproducible para BCB, INE y ASFI, y **al
menos un hueco real verificado a mano** contra el portal: que exista el
período y que nosotros no lo tengamos. Un detector de huecos que solo produce
falsos positivos no sirve, y la única forma de saberlo es comprobar uno.

**Commit.** `feat: detector de huecos y atrasos por dataset`

---

## Etapa L — Recuperar lo atrasado y lo perdido

### B-54 · Escalera de recuperación — Antigravity — 110 min

**Objetivo.** Dado un período faltante, buscarlo en orden de menor a mayor
riesgo. La reunión lo dice: «en su mayoría buscarse en la misma URL, a veces
las mueven de dirección».

**Orden de la escalera**, y se detiene en el primer escalón que lo encuentre:
1. La misma URL que ya conocíamos.
2. La plantilla de la serie con el período faltante — esto es D-17, que ya
   existe y exige validación HEAD antes de admitir nada.
3. Otra ruta dentro del mismo dominio: sitemap y buscador interno del portal.
4. El archivo histórico de la web (`wayback_engine`, ya implementado).

**Criterio de aceptación.** Al menos 10 períodos faltantes de los detectados en
B-53 recuperados y verificados con bytes y hash, y un registro de en qué
escalón apareció cada uno. Ese registro es lo que dice qué escalón vale la pena
y cuál sobra.

**Commit.** `feat: escalera de recuperacion de periodos faltantes`

---

### B-55 · Búsqueda de herencia — decisión de Claude antes de implementar — 120 min

**Objetivo.** El caso más difícil de la reunión: «puede darse que ya no exista
y requiera una búsqueda de herencia, a qué URL migró, o si ahora lo manejan
otras entidades u otro dominio».

**Parada de diseño obligatoria.** Antigravity entrega primero un diagnóstico y
Claude decide. No se implementa nada antes.

**Por qué esta parada.** Buscar «qué entidad se hizo cargo de esta serie» es
exactamente la clase de error que D-01 existe para prevenir. Este proyecto ya
aceptó cuatro veces una institución equivocada que respondía 200: CADEX por
CADEXCO, IBCE por IBCH, `bcp.org` por BCP, y `sicsantacruz.com` que resultó ser
un dominio de parking aprobado por una investigación externa. Una búsqueda de
herencia automatizada es una máquina de repetir ese error a escala.

**La decisión a tomar** es qué evidencia hace admisible una herencia. Como
mínimo, y a definir en el acta: continuidad verificable de la serie, mención
explícita de la entidad anterior, y coincidencia de la estructura del
documento. **Ninguna herencia se acepta de forma automática**: el resultado del
bloque es una propuesta con evidencia para que la apruebe una persona.

**Criterio de aceptación.** La decisión formal escrita en `docs/decisiones.md`,
y al menos un caso de herencia propuesto con su evidencia completa — aceptado o
rechazado, ambos son resultado válido.

**Commit.** `feat: propuesta de herencia de series con evidencia obligatoria`

---

## Etapa M — Ciclo de vida y conciliación

### B-56 · Estado de vigencia y paso a histórico — Antigravity — 80 min

**Objetivo.** «Fuentes que no se pueden actualizar se vayan al histórico».

**Pasos.** Un estado explícito por dataset: `VIGENTE`, `ATRASADO`, `MIGRADO`,
`HISTORICO`, con la regla de transición y la fecha en que cambió. El catálogo
ya marca procedencia histórica para entidades disueltas (SPVS-ASFI, SPVS-APS,
SUPTRANS); esto lo generaliza y lo vuelve automático.

**Criterio de aceptación.** El paso a `HISTORICO` nunca es automático por
silencio: exige que la escalera de B-54 se haya agotado y quede registrado qué
se intentó. Una fuente que se archiva porque nadie la buscó bien es una fuente
perdida, no una fuente histórica.

**Commit.** `feat: ciclo de vida de datasets y archivado justificado`

---

### B-57 · Cruce con el crawler interno — BLOQUEADO — 120 min estimados

**Estado: bloqueado.** Falta que Marlon envíe las URLs de los repositorios del
crawler interno y del externo. Se clonan **al lado** de este proyecto, nunca
dentro.

**Objetivo.** «Cruce de datos del crawler externo con el interno» y «las DB de
DataX al día».

**Clave de cruce propuesta**, a confirmar cuando se vean los esquemas:
institución + dataset + período. Es otra razón por la que la Etapa J va
primero: sin período no hay clave de cruce.

**Salida esperada.** Qué tiene el interno que nosotros no, qué tenemos nosotros
que el interno no, y qué tienen ambos con período distinto.

**Criterio de aceptación.** El cruce corre sobre los tres portales y ninguna
diferencia queda sin clasificar en una de esas tres categorías.

**Commit.** `feat: conciliacion entre el catalogo externo y el interno`

---

### B-58 · Reporte de vigencia y cierre — Claude — 70 min

Estado de los tres portales: al día, atrasados, con huecos, recuperados y
archivados. Actualizar `docs/bitacora_equipo.md`.

**Criterio de aceptación.** Toda cifra sale de correr los instrumentos, no de
los partes. Si una capacidad quedó a medias, se dice cuál y por qué.

**Commit.** `docs: estado de vigencia de bcb, ine y asfi`

---

## Seguimiento

| Bloque | Responsable | Estimado | Real | Estado |
|---|---|---:|---:|---|
| B-50 Patrones de fecha reales | Antigravity | 100 min | | Pendiente |
| B-51 Fechas y datasets de INE | Antigravity | 110 min | | Pendiente |
| B-52 Periodicidad declarada | Antigravity | 60 min | | Pendiente |
| B-53 Detector de huecos y atrasos | Antigravity | 110 min | | Pendiente |
| B-54 Escalera de recuperación | Antigravity | 110 min | | Pendiente |
| B-55 Búsqueda de herencia | Claude + Antigravity | 120 min | | Pendiente |
| B-56 Ciclo de vida e histórico | Antigravity | 80 min | | Pendiente |
| B-57 Cruce con el interno | Antigravity | 120 min | | **Bloqueado** |
| B-58 Reporte y cierre | Claude | 70 min | | Pendiente |
| **Total** | | **~14 h** | | |

---

## Modo de ejecución

Igual que la Fase 2: corrida continua con el bucle de
`docs/guia_bucle_automatizado.md`, auditoría con puntero puro, auditor sin
permisos de escritura ni commit, y la política de tokens de
`docs/plan_bloques_fase2.md`.

**Paradas de esta fase:**

1. **B-55**, parada de diseño antes de implementar la herencia.
2. **B-57**, bloqueado hasta que lleguen las URLs de los repositorios.
3. Las tres condiciones generales: decisión de política, tres DEVUELTO del
   mismo bloque, o bloqueo externo insalvable.

**Orden por valor sobre tokens.** B-50 es el de mayor retorno de toda la fase
—un cambio de patrones que desbloquea 1.165 filas— y por eso va primero. Si el
presupuesto se agota, lo aceptable de perder es B-55 y B-57; **B-58 no se
sacrifica**, porque sin medición la fase no tiene resultado.

---

## Deuda que esta fase hereda y no resuelve

Queda anotado para no perderlo de vista:

- `config/source_snis.yaml` tiene trabajo sin commitear y
  `test_integracion_reproducibilidad_real` falla por esa razón.
- `dashboard/app.js` tiene el arreglo del campo booleano tratado como URL, sin
  commitear.
- 8.655 filas del catálogo global vienen de la Fase 1 y no tienen hash.
- ASFI sigue 1.777 documentos por debajo de Rolando.
