# Fase 4 · Vía B — Recuperar y publicar

**Para quien toma esta vía.** Este archivo es autónomo: no hace falta haber
seguido las fases anteriores del proyecto. Trae el contexto mínimo, el
contrato con la otra vía, tus cinco bloques y cómo se cierra.

- **Repositorio:** `https://github.com/MarlonTMF/Crawler_Buscador`
- **Tu rama:** `fase4/recuperacion` (desde `main`)
- **La otra vía:** `fase4/fechado`, la trabaja Marlon
- **Estimado de esta vía:** 8 h 40 en 5 bloques
- **Alcance de toda la fase:** solo tres portales — **BCB, INE y ASFI**

---

## 1. Qué hace este sistema, en un párrafo

El **Buscador de Fuentes** (repo `crawler_finrural`) rastrea portales
institucionales bolivianos —bancos centrales, reguladores financieros,
institutos de estadística— y cataloga los documentos que publican: memorias,
boletines mensuales, series estadísticas. Cada fuente se configura con un YAML
declarativo y el resultado queda en una base SQLite por fuente,
`output/<fuente>/inventory.db`, en la tabla `resource_audit_log`.

No guarda los archivos en disco: descarga los bytes a memoria, calcula el
SHA-256 y registra la fila. El entregable es **un catálogo verificado de
recursos**, no una carpeta de PDFs.

---

## 2. Qué pidió la reunión y por qué existe la Fase 4

Las notas del 23 de septiembre piden que las fuentes estén al día y que se
note cuando no lo están:

> «si la fuente es diaria y se ha atrasado un mes, tal vez cambió de link» ·
> «falta febrero, aparece abril» · «reportes perdidos y atrasados deben poder
> recuperarse, en su mayoría en la misma URL, a veces las mueven» · «fuentes
> que no se pueden actualizar se vayan al histórico» · «cruce de datos del
> crawler externo con el interno»

Eso se resolvió en cuatro etapas encadenadas:

```
J · Fechar   →   K · Detectar   →   L · Recuperar   →   M · Cerrar
                                    └──── tu vía ────────────┘
```

**Vía A (Marlon)** resuelve J y K: hacer que cada documento tenga un período y
detectar cuáles faltan.
**Vía B (vos)** resuelve L y M: recuperar lo que falta y publicarlo hacia el
sistema que lo consume.

---

## 3. El contrato entre las dos vías — léelo antes de escribir código

Tu vía consume lo que produce la vía A. Para que no tengas que esperarla,
**el formato está acordado de antemano** y vos trabajás contra un fixture
hasta que el detector real aterrice.

### Lo que la vía A te entrega: un registro de hueco

```json
{
  "source_id": "asfi",
  "dataset_id": "boletines_mensuales",
  "periodicidad": "mensual",
  "periodo": "2026-02",
  "periodo_inicio": "2026-02-01",
  "periodo_fin": "2026-02-28",
  "estado": "FALTANTE",
  "ultimo_observado": "2026-04",
  "url_patron_conocido": "https://www.asfi.gob.bo/.../{AAAA}/{MM}/...",
  "detectado_en": "2026-09-24T14:00:00+00:00"
}
```

Se entrega como lista JSON en `output/huecos_<fuente>.json`.

### Lo que tu vía devuelve: el mismo registro, resuelto

```json
{
  "...": "todos los campos del hueco, sin modificar",
  "recuperado": true,
  "escalon": 2,
  "url_recuperada": "https://...",
  "content_sha256": "a1b2...",
  "bytes": 184320,
  "verificado_contenido": true,
  "intentos": [
    {"escalon": 1, "resultado": "no_encontrado"},
    {"escalon": 2, "resultado": "encontrado", "http": 200}
  ]
}
```

**El campo `intentos` no es decorativo.** Es lo que al final dirá, con datos,
qué escalón de la escalera vale la pena y cuál sobra.

### Cómo arrancás sin esperar a la vía A

Creá `tests/fixtures/huecos_muestra.json` con **tres huecos reales**
verificados a mano contra los portales: uno de ASFI, uno de BCB y uno de INE.
Buscalos vos mismo en el sitio —un boletín mensual que exista en el portal y
no esté en nuestro `inventory.db`— y anotá la URL real en
`url_patron_conocido`.

Con eso podés construir y probar toda la escalera. Cuando la vía A entregue el
detector, cambiás el fixture por el archivo real y no tocás nada más.

---

## 4. Reparto de archivos, para no chocar al fusionar

Cada vía es dueña de sus archivos. **Si necesitás tocar uno de la otra
columna, avisá antes.**

| Archivo | Dueño |
|---|---|
| `src/crawler/core/extractor.py` | **Vía A** |
| `config/source_{bcb,ine,asfi}.yaml` | **Vía A** |
| `scripts/detector_huecos.py` | **Vía A** (nuevo) |
| `src/crawler/core/recuperador.py` | **Vía B** (nuevo) |
| `src/crawler/core/ciclo_vida.py` | **Vía B** (nuevo) |
| `scripts/exportar_catalogo.py` | **Vía B** (nuevo) |
| `src/crawler/core/fetcher.py` | **Vía B** (solo B-54b) |

**Conflictos previsibles y cómo se evitan:**

- `docs/decisiones.md` — las dos vías agregan decisiones. Están **reservados
  los números**: la vía A usa **D-18 y D-19**, la vía B usa **D-20 en
  adelante**. Siempre al final del archivo, sin renumerar lo existente.
- `docs/plan_bloques_fase4.md` — cada vía actualiza **solo sus propias filas**
  de la tabla de seguimiento.
- **El estado de vigencia de B-56 no va en los YAML** (son de la vía A): va en
  `inventory.db` o en un archivo propio.

---

## 5. Cómo se trabaja un bloque

Convención del proyecto, y conviene respetarla porque la revisión se apoya en
ella:

1. **Un bloque, un commit.** Cada bloque cierra con un commit propio y la
   suite rápida en verde: `python -m pytest tests/ -q -m "not live"`
   (136 pruebas, ~15 s).
2. **Nunca `git add -A`.** Hay trabajo de varias sesiones en el árbol; cada
   commit agrega sus archivos por nombre.
3. **Formato de commit:** `tipo: descripción en minúscula, imperativa, en
   español`. Tipos: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`, `data`.
4. **Una prueba de regresión no vale hasta verla fallar.** Se escribe la
   prueba, se confirma que falla, y recién después se arregla.
5. **Ninguna cifra sin verificar.** Si un parte dice «recuperamos 12
   períodos», esa cifra sale de consultar `inventory.db`, no del log de
   consola.
6. Al cerrar cada bloque, un parte en `docs/entregas/B-NN.md` con evidencia
   literal de consola.

---

## 6. Las tres reglas que este proyecto aprendió a la mala

Te las paso porque tu vía toca justo donde estos errores duelen.

**Un 200 no prueba nada (D-01).** El proyecto aceptó cuatro veces una
institución equivocada que respondía 200: CADEX por CADEXCO, IBCE por IBCH,
`bcp.org` por BCP, y un dominio de parking que una investigación externa dio
por bueno. **Toda URL se verifica por contenido**, con palabras clave de la
institución.

**Nada de sondeo especulativo (D-02).** No se prueban variantes al azar de una
URL que falló. Sí se permite extrapolar una serie **cuya plantilla está
demostrada** —por ejemplo porque el portal tiene un script que la construye—,
y en ese caso cada candidato pasa por `HEAD` antes de entrar al catálogo
(D-17).

**Verificar el efecto, no el artefacto.** Los errores más caros de este
proyecto no lanzaron ninguna excepción: un motor que marcaba recursos como
procesados sin transferir un solo byte, un log que decía «candidatos
descubiertos» sin descargar nada. Si algo parece hecho, comprobalo leyendo la
base.

---

## 7. Tus bloques

### B-54 · Escalera de recuperación determinista — 110 min

**Objetivo.** Dado un período faltante, buscarlo en orden de menor a mayor
riesgo, parando en el primer escalón que lo encuentre.

**Los cuatro escalones:**

1. **La misma URL** que ya conocíamos. La reunión dice que en su mayoría
   siguen ahí, así que este escalón debería resolver la mayoría.
2. **La plantilla de la serie** con el período faltante. Ya existe
   `src/crawler/core/series_extrapolator.py`, que exige `HEAD` con 200,
   tamaño mayor a cero y extensión documental antes de admitir nada.
3. **Otra ruta del mismo dominio**: sitemap y buscador interno del portal.
4. **El archivo histórico de la web.** Ya existe
   `src/crawler/core/wayback_engine.py`.

**Reusá lo que hay.** Tres de los cuatro escalones ya tienen motor
implementado; este bloque los encadena y registra el resultado, no los
reescribe.

**Criterio de aceptación.** Al menos **10 períodos faltantes recuperados** con
bytes y hash verificados, **y el registro de en qué escalón apareció cada
uno**.

**Commit.** `feat: escalera de recuperacion de periodos faltantes`

---

### B-54b · El agente como escalón final — 90 min

**Objetivo.** Que el agente proponga candidatos cuando los cuatro escalones
deterministas no encontraron nada. Es el escalón 5.

**El mecanismo ya existe:** `fetcher.py::_ask_gemini_for_alternatives` se usa
hoy para resolver dominios caídos. Este bloque lo conecta a la recuperación de
períodos; no lo reescribe.

**Por qué va último y no primero.** Los escalones 1 a 4 son deterministas y
verificables. El agente es generativo y **ya falló antes en este proyecto**:
las tres instituciones equivocadas que menciona la regla D-01 las sugirió él.
Ponerlo al final significa que solo opina cuando nada determinista funcionó,
que es donde su costo se justifica y donde su error es más fácil de atrapar.

**Las seis reglas que no se pueden saltar:**

1. El agente **nunca escribe en `inventory.db`**: propone, no admite.
2. Toda propuesta pasa por **`HEAD`** con 200, tamaño mayor a cero y tipo
   documental.
3. Toda propuesta pasa por **verificación de contenido** con palabras clave de
   la institución.
4. **Cambio de dominio institucional nunca es automático** — eso es una
   herencia y va a B-55.
5. **Tope de llamadas por corrida**, registrado. La cuota de Gemini ya se
   consumió sin querer una vez.
6. Queda registrado **en qué escalón apareció cada recuperación**.

**Ojo con el log.** Hay una regla nueva por un incidente reciente: el texto de
una excepción de `requests` incluye la URL de la petición, y esa URL lleva
`?key=<clave>`. Una clave de API terminó publicada así. Usá
`fetcher._redact_secrets()` sobre cualquier texto que vaya a un log o a un
parte.

**Criterio de aceptación.** Al menos **5 períodos** que los escalones 1 a 4 no
encontraron, cada uno con `HEAD` y verificación de contenido. **Si el agente
no aporta ninguno, eso también es un resultado válido y se reporta**:
significa que los deterministas alcanzan y el gasto no se justifica.

**Commit.** `feat: agente como escalon final de la escalera de recuperacion`

---

### B-55 · Búsqueda de herencia — 120 min · **con parada de diseño**

**Objetivo.** El caso más difícil: la serie ya no existe y hay que averiguar a
qué URL migró o qué entidad se hizo cargo.

> **Parada obligatoria.** Antes de implementar nada, entregá un diagnóstico y
> esperá la decisión. Automatizar «qué entidad heredó esta serie» es una
> máquina de repetir el error de D-01 a escala: el proyecto ya aceptó cuatro
> veces una institución equivocada que respondía 200.

**El diagnóstico debe responder:** qué evidencia haría admisible una herencia.
Como mínimo, a discutir: continuidad verificable de la serie, mención explícita
de la entidad anterior en el sitio nuevo, y coincidencia de la estructura del
documento.

**Criterio de aceptación.** La decisión formal escrita en `docs/decisiones.md`
(numeración D-20 en adelante), y al menos un caso propuesto con su evidencia
completa. **Ninguna herencia se acepta automáticamente:** la salida es una
propuesta para que la apruebe una persona. Aceptada o rechazada, ambas son
resultado válido.

**Commit.** `feat: propuesta de herencia de series con evidencia obligatoria`

---

### B-56 · Estado de vigencia y paso a histórico — 80 min

**Objetivo.** «Fuentes que no se pueden actualizar se vayan al histórico».

**Pasos.** Un estado explícito por dataset —`VIGENTE`, `ATRASADO`, `MIGRADO`,
`HISTORICO`— con su regla de transición y la fecha del cambio.

**Criterio de aceptación.** El paso a `HISTORICO` **nunca es automático por
silencio**: exige que la escalera de B-54 se haya agotado y quede registrado
qué se intentó. Una fuente archivada porque nadie la buscó bien es una fuente
perdida, no una fuente histórica.

**Nota de reparto.** Este estado **no va en los YAML de las fuentes**, que son
de la vía A. Va en `inventory.db` o en un archivo propio.

**Commit.** `feat: ciclo de vida de datasets y archivado justificado`

---

### B-57 · Cruce con el prospector interno — 120 min · **con decisión previa**

**Objetivo.** «Cruce de datos del crawler externo con el interno» y «las DB de
DataX al día».

**Lo que ya existe, y conviene leer antes de diseñar nada.** Hay **tres
sistemas**, no dos:

| Sistema | Rol |
|---|---|
| **Buscador de Fuentes** (este repo) | El motor de descubrimiento y extracción |
| `Prospector-Externo` | Prospecta y **sirve la Catalog API** en el puerto 8000 |
| `prospector_interno` | Ingiere, almacena y **ya concilia** con `DuckDBDiffEngine` |

El contrato de integración **ya está implementado**: el interno llama a
`/health`, `/runs` y `/catalog/resources?source_id=X`, y clasifica cada
diferencia en `CONFIRMED`, `NEW`, `MODIFIED` o `URL_CHANGED`. No hay que
diseñar la conciliación: hay que **alimentarla**.

Entre los campos del contrato está **`period_label`** — que es exactamente lo
que produce la vía A. Hoy lo mandamos vacío en el 97% de BCB.

> **Parada de decisión.** Este repo **no es** el `Prospector-Externo` que el
> interno consume. Cómo se cierra ese puente —un exportador, portar el motor,
> o exponer una segunda fachada— se decide **antes de escribir código**. Está
> desarrollado en `docs/arquitectura_integracion.md`, sección 5; la opción
> recomendada es el exportador.

**Ojo:** la Catalog API y el `dashboard_server.py` de este repo usan **ambos el
puerto 8000** y no pueden correr a la vez.

**Criterio de aceptación.** Ninguna diferencia queda sin clasificar: solo en el
interno, solo en el externo, o en ambos con período distinto.

**Commit.** `feat: conciliacion entre el catalogo externo y el interno`

---

## 8. Seguimiento

| Bloque | Estimado | Real | Estado |
|---|---:|---:|---|
| B-54 Escalera determinista | 110 min | | Pendiente |
| B-54b Agente como escalón 5 | 90 min | | Pendiente |
| B-55 Herencia · parada de diseño | 120 min | | Pendiente |
| B-56 Ciclo de vida | 80 min | | Pendiente |
| B-57 Cruce con el interno · decisión previa | 120 min | | Pendiente |
| **Total Vía B** | **8 h 40** | | |

Las estimaciones son estimaciones. En fases anteriores los bloques mecánicos
se quedaron cortos alrededor de un 50%.

---

## 9. Puntos de sincronización

| Cuándo | Qué |
|---|---|
| **Antes de empezar** | Confirmar el contrato de la sección 3. Si algo del formato no te sirve, cambiarlo ahora sale gratis; después no. |
| **Cuando la vía A cierre B-53** | Cambiás el fixture por `output/huecos_<fuente>.json` real. Si la escalera se rompe ahí, el contrato estaba mal y hay que corregirlo entre los dos. |
| **En B-55 y B-57** | Las dos paradas. No sigas de largo. |
| **Al final** | Se fusionan las dos ramas y se hace **B-58 · reporte de vigencia y cierre** (70 min) entre ambos. |

**Orden de fusión:** primero `fase4/fechado` a `main`, después
`fase4/recuperacion` rebasada sobre `main`. La vía A no depende de la B, así
que va primero.

---

## 10. Para arrancar

```bash
git clone https://github.com/MarlonTMF/Crawler_Buscador
cd Crawler_Buscador
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -e .
python -m pytest tests/ -q -m "not live"            # 136 pruebas, ~15 s

git checkout -b fase4/recuperacion
```

Hace falta un `.env` con `GEMINI_API_KEY` para B-54b. **No está en el
repositorio ni debe estarlo** — pedísela a Marlon.

**Documentos de referencia en el repo:**

- `docs/arquitectura_integracion.html` — los tres sistemas y el contrato, con
  diagramas. Empezá por acá.
- `docs/plan_bloques_fase4.md` — el plan completo de la fase, las dos vías.
- `docs/decisiones.md` — D-01 a D-17, las decisiones cerradas del proyecto.
- `CLAUDE.md` — reglas del proyecto y la tabla de errores silenciosos.
