# Plan de bloques — Fase 5: mejorar la recuperación de fuentes perdidas

**Ejecuta Antigravity en solitario.** Claude no audita esta fase. Por eso el
plan está escrito para verificarse solo: cada criterio de aceptación es **un
comando que imprime un número**, el parte pega esa salida literal, y Marlon
puede comprobar el estado completo con **un solo comando** (B-59).

Alcance: **BCB, INE y ASFI.** Bloques **B-59 a B-66**. Origen: sección 8,
«Próximos pasos», de `dashboard/presentacion_ejecutiva.html`.

---

## 1. Objetivo y metas

Mejorar los resultados del sistema de fuentes perdidas. Línea base medida el
**30 de septiembre de 2026** con `scripts/recuperar_periodos.py`:

| Indicador | Línea base 30-sep | Meta de la fase |
|---|---:|---:|
| Resultados falsos admitidos | **6** | **0** — no negociable |
| Recuperaciones verificadas | 3 | ≥ 10 |
| Estrategias con al menos una recuperación | 1 de 5 | ≥ 3 de 5 |
| URLs catalogadas revalidadas | 0 de 1.165 | 1.165 de 1.165 |
| Cobertura de fechas en BCB | 32 % | ≥ 65 % |
| Faltantes consultados al agente | ~10 de 34 | todos los pendientes |

**Regla de las metas:** si una no se alcanza, el parte reporta el número real
con su causa y se sigue. **No se ajusta la meta ni se redondea.** Un resultado
peor y explicado vale; uno inflado no. La primera fila es la excepción: con
falsos positivos admitidos, el bloque no se cierra.

---

## 2. Diagnóstico actualizado

| # | Problema | Evidencia |
|---|---|---|
| **P-1** | **No se detectan documentos movidos.** `gap_detector.py` no hace ninguna petición HTTP: solo compara períodos dentro de `inventory.db`. Si una URL catalogada da 404, nadie se entera. | Lectura del código |
| **P-2** | **Escalón 1 inerte.** Saca candidatos de `resource_audit_log` y luego descarta los que están en el inventario. El propio docstring lo admite. | 0 recuperaciones |
| **P-3** | **Escalón 3 admite resultados que no corresponden al período.** El portal del INE entrega por ID numérico e ignora el nombre del archivo: cualquier variante del nombre devuelve el mismo PDF con 200. | 6 falsos positivos el 30-sep: cinco años de auditoría (2013-2017) con **el mismo SHA-256** `c599975b…`, y una «escala salarial 2025» que es `ine_escala_salarial_2026.pdf` |
| **P-4** | **Escalón 4 codificado a mano** para `bcb/deuda_externa` e `ine/rendicion_cuentas`. No usa `wayback_engine.py` (CDX, caché); llama a la Availability API con timeout de 2 s. | 0 recuperaciones |
| **P-5** | **Agente con muestra truncada.** `max_gemini_calls=10` se agota antes de recorrer los faltantes. | 10 consultas, 0 recuperaciones |
| **P-6** | **Cambio de política sin decisión escrita.** Código sin commitear en `recovery_ladder.py` acepta automáticamente un candidato del agente si su dominio es un **sucesor configurado** (`is_authorized_successor`), sin pasar por la cola de herencia ni por aprobación humana. D-18 exige lo contrario. | `recovery_ladder.py`, línea ~833 |
| **P-7** | **BCB pone el período en el nombre del archivo** (`DEPEX dic25.pdf`), no en la ruta. El extractor no lo reconoce. | Cobertura 32 % |

---

## 3. Reglas de ejecución sin auditor

1. **Cada criterio es un comando.** El parte pega la salida literal, sin
   editar. Si el comando no existe o no corre, el bloque no está hecho.
2. **Ninguna cifra a mano.** Todo número del parte salió de correr algo.
3. **Ver fallar la prueba antes del arreglo** y pegar las dos salidas: la del
   fallo y la del éxito.
4. **Un bloque, un commit**, con `python -m pytest tests/ -q -m "not live"` en
   verde. Nunca `git add -A`: los archivos se agregan por nombre.
5. **Revisar a mano cada recuperación nueva** antes de contarla: abrir la URL,
   confirmar que el documento es de la institución y del período asignado. Es
   exactamente el control que habría atrapado los 6 falsos positivos.
6. **Formato de los partes:** `docs/entregas/B-NN.md`, con la salida de
   `scripts/verificar_fase5.py` al final. Actualizar `docs/bitacora_equipo.md`
   al cerrar cada bloque.
7. **Parar y escalar a Marlon** si: hace falta tocar o crear una decisión en
   `docs/decisiones.md`; un portal bloquea por WAF o captcha; un cambio exige
   modificar el contrato con el prospector interno; o un bloque falla tres
   veces seguidas.

---

## Etapa Q — Base limpia y resultados confiables

### B-59 · Estado limpio, compuertas de calidad y verificador — 120 min

**Por qué va primero.** Mientras el escalón 3 admita falsos positivos,
cualquier mejora medida está contaminada. Y hay código ajeno sin commitear que
no se sabe si se queda.

**Pasos.**

1. **Revisar el trabajo sin commitear** (`recovery_ladder.py`, `fetcher.py`,
   `discovery.py`, `relocation_manager.py`, `bridge_exporter.py`, el dashboard
   y sus pruebas). Commitearlo en **commits separados por tema**, cada uno con
   la suite en verde. Lo que no se entienda o rompa pruebas, no se commitea y
   se anota en el parte.
2. **P-6 — parada obligatoria.** Antes de commitear `recovery_ladder.py`,
   revertir la aceptación automática de sucesores: un candidato de dominio
   sucesor **va a la cola de herencia igual que cualquier dominio externo**.
   Si se considera que esa aceptación automática debe quedar, **no decidirlo**:
   escalar a Marlon, que es una decisión de política (D-18).
3. **Dos compuertas de calidad** en `recovery_ladder.py`, aplicadas a todos los
   escalones antes de admitir una recuperación:
   - **Huella repetida:** si el mismo `content_sha256` ya se asignó a otro
     período del mismo dataset (en esta corrida o en `inventory.db`), se
     rechaza.
   - **Año contradictorio:** si el nombre del archivo contiene un año de cuatro
     dígitos distinto del período buscado —y no hay otro año que coincida—, se
     rechaza.
   - Cada rechazo queda registrado con su motivo en la salida JSON
     (`rechazos_calidad`).
4. **Crear `scripts/verificar_fase5.py`**, que imprime de una vez los seis
   indicadores de la tabla de la sección 1. Es lo que Marlon corre para saber
   cómo va la fase sin leer partes.

**Pruebas.** `tests/test_compuertas_calidad.py` con, como mínimo: el caso real
de los cinco años de auditoría con la misma huella (debe rechazar 4 de 5 o los
5), el caso de `ine_escala_salarial_2026.pdf` asignado a 2025 (debe rechazar),
y un caso válido de BCB (`DEPEX dic25.pdf` para `2025-S2`, debe admitir).

**Criterio de aceptación.**

```bash
python scripts/recuperar_periodos.py --sources bcb,ine,asfi --max-gemini-calls 10 --format json --output output/recup_b59.json
python scripts/verificar_fase5.py
```

Debe mostrar **0 resultados falsos admitidos**, los 6 casos del 30-sep en
`rechazos_calidad`, y las 3 recuperaciones válidas de BCB intactas.

**Commits.** Los de la revisión del código ajeno, y luego
`fix: compuertas de calidad contra huella repetida y año contradictorio`.

---

## Etapa R — Detectar lo que se movió

### B-60 · Revalidación de las 1.165 URLs catalogadas — 120 min

**Resuelve P-1.** Es el paso 1 del informe y la capacidad que falta para
detectar un documento que se tenía y cambió de lugar.

**Qué construir.** `src/crawler/core/url_revalidator.py` y
`scripts/revalidar_urls.py`. Para cada URL de `resource_audit_log` de los tres
portales, `HEAD` (con `GET` de respaldo si responde 405) y clasificación:

| Estado | Condición |
|---|---|
| `VIGENTE` | 200 y tipo de contenido documental |
| `REDIRIGIDA` | 301/302 hacia otra URL que responde 200 — guardar el destino |
| `ELIMINADA` | 404 o 410 |
| `INACCESIBLE` | timeout, 403, error de conexión — **no equivale a eliminada** |

**Especificaciones.** Respetar `rate_limit_per_second` de cada YAML. Guardar
la fecha de revalidación para poder repetirla y comparar. Salida:
`output/revalidacion_<fuente>.json`. Las `REDIRIGIDA` y `ELIMINADA` son la
entrada del escalón 1 (B-61).

**Criterio de aceptación.**

```bash
python scripts/revalidar_urls.py --sources bcb,ine,asfi --format resumen
```

Clasifica **las 1.165** URLs y muestra el conteo por estado. Cuántas salgan
eliminadas no es meta: si son 0, es un buen resultado.

**Commit.** `feat: revalidacion de urls catalogadas para detectar documentos movidos`

### B-61 · Escalón 1 real — 110 min

**Resuelve P-2.** Paso 2 del informe.

**Qué construir.** Reemplazar `_try_rung_1_known_url` para que trabaje sobre
la URL conocida del documento, no sobre una búsqueda en la propia base:

1. Seguir la redirección si B-60 la marcó `REDIRIGIDA`.
2. Si está `ELIMINADA`, pedir el directorio superior y buscar en el listado un
   archivo del mismo período.
3. Probar variantes de la misma URL: mayúsculas, `%20` contra espacio, guion
   contra guion bajo, extensión en mayúsculas.

**Límite.** Esto no es sondeo especulativo (D-02) porque parte de una URL que
**existió y se cayó**. Variantes de URLs que nunca existieron siguen
prohibidas. Dejarlo escrito en el parte.

**Criterio de aceptación.**

```bash
python -m pytest tests/test_recovery_rung1.py -v
```

Con al menos cuatro casos: redirección seguida, directorio superior, variante
de codificación, y un caso negativo que debe devolver `None`.

**Commit.** `fix: el escalon 1 sigue el rastro de la url conocida`

---

## Etapa S — Generalizar las búsquedas

### B-62 · Escalón 3 derivado de la serie — 110 min

**Resuelve P-3 en su parte de cobertura.** Paso 3 del informe. Las compuertas
de B-59 ya cubren los falsos positivos; este bloque hace que el escalón
funcione para cualquier dataset.

**Qué construir.** Derivar candidatos de las URLs observadas del propio
dataset: tomar sus URLs de `inventory.db`, inferir qué parte varía con el
período, generar el candidato del período faltante, y buscar además en
`sitemap.xml` si el portal lo publica.

**Criterio de aceptación.**

```bash
python scripts/recuperar_periodos.py --sources asfi --dry-run
```

Debe listar candidatos para **los 20 faltantes de `asfi/poa_seguimiento`**,
que hoy no generan ninguno. Cuántos se recuperen se mide en B-66.

**Commit.** `feat: el escalon 3 deriva candidatos de las urls observadas del dataset`

### B-63 · Escalón 4 sobre el motor CDX — 90 min

**Resuelve P-4.** Paso 3 del informe.

**Especificaciones.** Quitar el condicional por portal y dataset. Usar
`src/crawler/core/wayback_engine.py`: consultar CDX por la URL conocida del
dataset y filtrar por período. Timeout de al menos 15 s. Marcar el recurso
como procedente del archivo histórico.

**Criterio de aceptación.**

```bash
python scripts/recuperar_periodos.py --sources bcb,ine,asfi --dry-run
```

Debe mostrar consultas CDX para **los 6 datasets con faltantes**, con el
número de instantáneas encontradas por cada uno.

**Commit.** `feat: el escalon 4 usa el motor cdx de wayback`

### B-64 · Período en el nombre del archivo — 90 min

**Resuelve P-7.** Paso 5 del informe.

**Qué construir.** En `src/crawler/core/extractor.py`, reconocer el período
dentro del nombre del archivo: mes abreviado más año corto (`dic25`, `jun24`),
mes completo más año (`Septiembre 2023`), y `AAAAMM` al inicio del nombre.
Recalcular sobre las corridas existentes con
`scripts/actualizar_fechas_inventario.py`, sin volver a rastrear.

**Advertencia.** Mejorar las fechas puede **cambiar el conteo de faltantes**:
aparecen series que antes no se podían evaluar. Es esperable. El parte reporta
el conteo antes y después.

**Criterio de aceptación.**

```bash
python scripts/verificar_fase5.py
python scripts/detectar_huecos.py --format resumen
```

BCB con cobertura de fechas **≥ 65 %**, y ninguna fila marcada `high` cuya
fecha provenga solo de la carpeta de publicación.

**Commit.** `feat: reconoce el periodo en el nombre del archivo`

---

## Etapa T — Medir y cerrar

### B-65 · El agente con presupuesto completo — 90 min

**Resuelve P-5.** Paso 4 del informe. Va después de B-61 a B-64 a propósito:
interesa cuánto aporta el agente **después** de que los escalones
deterministas hagan su trabajo.

**Especificaciones.** `--max-gemini-calls` igual o mayor al número de
faltantes pendientes. Registrar por consulta: candidatos propuestos, cuántos
pasaron `HEAD`, cuántos pasaron la verificación de contenido, cuántos pasaron
las compuertas de B-59, y cuántos fueron a la cola de herencia. **No tocar los
guardarraíles:** el agente no escribe en la base y ningún dominio distinto se
acepta solo.

**Criterio de aceptación.** El parte responde con números:

```
faltantes consultados al agente:      N
candidatos propuestos:                N
pasaron HEAD:                         N
pasaron verificacion de contenido:    N
pasaron compuertas de calidad:        N
recuperados por el escalon 5:         N
derivados a cola de herencia:         N
```

**Si el resultado es 0 con presupuesto completo, esa es la respuesta**: se
retira el escalón 5 y se ahorra el gasto. Es tan válido como lo contrario.

**Commit.** `feat: mide el aporte del agente con presupuesto completo`

### B-66 · Corrida completa y actualización del informe — 90 min

**Qué entregar.**

1. Corrida completa sobre los faltantes y sobre las URLs `REDIRIGIDA` y
   `ELIMINADA` de B-60.
2. **Revisión manual de cada recuperación** (regla 5).
3. Actualizar `dashboard/presentacion_ejecutiva.html`: secciones 1, 3
   (figura), 4, 5, 6 y 7 con las cifras nuevas. **Se editan números y textos,
   no la estructura ni el estilo.** Cambiar la fecha de medición.
4. Actualizar `docs/resultados_escalera_recuperacion.html` del mismo modo.

**Criterio de aceptación.**

```bash
python scripts/verificar_fase5.py
```

Pegar la salida y la tabla de la sección 1 con la columna «Resultado» llena.

**Commit.** `docs: resultados medidos de la fase 5`

---

## 4. Seguimiento

| Bloque | Paso del informe | Estimado | Real | Estado |
|---|---|---:|---:|---|
| B-59 Base limpia y compuertas | — | 120 min | | Pendiente |
| B-60 Revalidación de URLs | 1 | 120 min | | Pendiente |
| B-61 Escalón 1 real | 2 | 110 min | | Pendiente |
| B-62 Escalón 3 derivado | 3 | 110 min | | Pendiente |
| B-63 Escalón 4 sobre CDX | 3 | 90 min | | Pendiente |
| B-64 Período en el nombre | 5 | 90 min | | Pendiente |
| B-65 Agente con presupuesto | 4 | 90 min | | Pendiente |
| B-66 Corrida y reporte | — | 90 min | | Pendiente |
| **Total** | | **13 h 40** | | |

## 5. Orden

B-59 primero, sin excepción: sin compuertas de calidad, todo lo que viene se
mide sobre resultados contaminados. B-60 antes que B-61, que necesita sus
datos. B-62, B-63 y B-64 son independientes entre sí. B-65 va al final a
propósito. **Si el tiempo se agota, lo aceptable de perder es B-65; B-59 y
B-66 no se sacrifican.**
