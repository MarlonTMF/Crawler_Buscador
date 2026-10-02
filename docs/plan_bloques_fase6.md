# Plan de bloques — Fase 6: recuperar los faltantes reales

**Ejecuta Antigravity en solitario**, sin auditoría de Claude. Bloques **B-67 a
B-74**. Alcance: **BCB, INE y ASFI**.

---

## 1. Punto de partida (medido el 2026-10-02, commit `6d546c6`)

Los 37 faltantes que mostraba la interfaz eran en su mayoría artefactos: el
calendario de cada serie arrancaba en su documento más antiguo aunque no fuera
de la serie. Corregido eso (cada serie se arma con sus propios documentos, vía
`series_pattern` en el YAML) e incorporadas al inventario las recuperaciones
verificadas, el estado real es:

| Serie | Faltantes | Recuperados | Pendientes |
|---|---:|---:|---|
| BCB · deuda externa (semestral) | 4 | 3 (jun-24, dic-24, dic-25) | **2025-S1** (`DEPEX jun25` da 404) |
| ASFI · seguimiento al POA (trimestral) | 1 | 0 | **2024-Q3** |
| INE · escala salarial (anual) | 1 | 0 | **2025** (su página de listado da 404: el INE migró a `nube.ine.gob.bo`) |
| INE · auditoría interna (anual) | 5 | 0 | **2013 a 2017** — dudosos: pueden no haberse publicado nunca en línea |
| **Total** | **11** | **3 (27,3 %)** | **8** |

Además, la serie mensual de balance general de ASFI está **atrasada**:
nov-2025 y dic-2025 no figuran (último publicado: `202510_BDR_EstadosFinancieros`,
en la carpeta de publicación `2026-07`).

Se ven en la interfaz: `dashboard/vigilancia/index.html`.

### Meta de la fase

**Recuperar o explicar cada faltante.** Al cierre, cada uno de los 8 pendientes
debe estar en una de dos situaciones, con evidencia:

- **Recuperado**: documento descargado, verificado e incorporado al inventario.
- **No publicado**: evidencia de que la institución no lo publicó (no figura en
  sus listados, en su calendario de publicaciones ni en el archivo histórico).

Meta numérica: **recuperados / (faltantes − no publicados demostrados) ≥ 80 %**.
Un «no publicado» sin evidencia cuenta como pendiente.

---

## 2. Reglas sin auditor

Aprendidas a la mala en las fases 4 y 5. No son opcionales.

1. **Ninguna recuperación cuenta sin verificar el archivo que entrega el
   servidor.** La escalera ya lo hace (compuerta `ano_servido_contradictorio`).
   Antes de reportar una cifra, correr `python scripts/construir_vigilancia.py
   --refrescar`: vuelve a consultar cada recuperación de forma independiente y
   es la cifra que vale.
2. **Nunca construir URLs escribiendo el año en portales que entregan por
   identificador** (el INE ignora el nombre del archivo y sirve por el número de
   la ruta). En esos portales el candidato sale de **un listado real del
   sitio**, nunca de modificar una URL conocida. Así nacieron los 8 falsos
   positivos de la fase 5.
3. **Extrapolar solo patrones observados** (D-17): una plantilla requiere al
   menos 3 URLs reales que la cumplan. Nada de probar variantes inventadas
   (D-02).
4. **Incorporar lo verificado**: `python scripts/incorporar_recuperaciones.py
   --input <corrida.json>`. Sin esto la recuperación no se ve en el detector.
5. **Corridas por portal** (`--sources ine`, etc.): la corrida de los tres juntos
   supera los 25 minutos. Sin agente: `--max-gemini-calls 0`.
6. **Ver fallar cada prueba antes del arreglo**, un bloque un commit, suite en
   verde (`python -m pytest tests/ -q -m "not live"`, hoy 300 pruebas), nunca
   `git add -A`.
7. **Cada parte** (`docs/entregas/B-NN.md`) termina con la salida literal de
   `python scripts/construir_vigilancia.py` y de
   `python scripts/detectar_huecos.py --format table`.
8. **Parar y avisar a Marlon** si: hay que crear o cambiar una decisión en
   `docs/decisiones.md`; un portal bloquea con captcha o WAF; o un bloque falla
   tres veces.

---

## 3. Bloques

### B-67 · Corrida real del INE con el arreglo del año — 40 min

La corrección de la compuerta de año (`f64d253`) se probó con los casos reales y
con la corrida del BCB, pero **la corrida real del INE quedó interrumpida**.

```bash
python scripts/recuperar_periodos.py --sources ine --max-gemini-calls 0 --format json --output output/recup_b67_ine.json
python scripts/incorporar_recuperaciones.py --input output/recup_b67_ine.json --dry-run
```

**Criterio:** cero recuperaciones del INE rechazadas por el simulacro de
incorporación (es decir, la escalera ya no admite documentos de otro año), y
los rechazos de la escalera listados con motivo `ano_servido_contradictorio`.

**Commit:** `test: corrida real del ine confirma la compuerta de anio servido`

### B-68 · INE: mapear el portal nuevo — 120 min

200 direcciones del INE redirigen y sus páginas de listado (`/descarga/wpfdcat/…`)
dan 404. Es la reorganización del portal.

1. Con `output/revalidacion_ine.json`, agrupar las 200 `REDIRIGIDA` por destino
   y entender la estructura nueva (`nube.ine.gob.bo` y la que corresponda).
2. Encontrar en el sitio nuevo **las páginas de listado** de las series
   vigiladas y extraer de ahí los documentos, con su año declarado por el
   servidor.
3. Actualizar en el inventario las URLs que redirigen (guardar la nueva sin
   perder la anterior; proponer el campo si hace falta).
4. Buscar en esos listados **escala salarial 2025** y **auditoría interna
   2013-2017**.

**Criterio:** los listados del sitio nuevo identificados y documentados en el
parte; escala salarial 2025 recuperada e incorporada, o evidencia de que no
figura en el listado.

**Commit:** `feat: descubrimiento sobre el portal reorganizado del ine`

### B-69 · ASFI: POA 2024-T3 y balance general atrasado — 90 min

1. **POA 2024-Q3.** Los seguimientos se llaman `Seguimiento al POA <trimestre>
   trimestre <año>.pdf`, en carpetas de publicación `sites/default/files/AAAA-MM/`.
   Tomar del inventario las carpetas **observadas** y probar el nombre del tercer
   trimestre de 2024 en las carpetas cercanas a su fecha esperada de publicación.
2. **Balance general nov y dic-2025.** Patrón observado
   `AAAAMM_BDR_EstadosFinancieros.zip` (2017-01 a 2025-10). Probar `202511` y
   `202512` en las carpetas de publicación observadas a partir de `2026-07`.

**Criterio:** cada uno recuperado e incorporado, o la lista literal de URLs
probadas (todas con plantilla observada) y su respuesta.

**Commit:** `feat: recuperacion de faltantes de asfi con plantillas observadas`

### B-70 · BCB: DEPEX jun-25 — 60 min

`DEPEX jun25.pdf` da 404 con la plantilla que sí funciona para jun-24, dic-24,
dic-25 y jun-26.

1. Revisar el **Calendario de Publicaciones** del BCB (enlazado en su página,
   `webdocs/Otros/Calendario de Publicaciones 2025 …pdf`): ¿estaba previsto el
   informe del primer semestre de 2025?
2. Buscar en el archivo histórico de la web (escalón 4, CDX) la carpeta
   `webdocs/informes_deudaexterna/`.

**Criterio:** recuperado e incorporado, o «no publicado» con la evidencia de
ambas fuentes.

**Commit:** `feat: resolucion del informe de deuda externa del primer semestre de 2025`

### B-71 · Estado «no publicado» con evidencia — 90 min

Hoy el detector solo distingue «faltante» de «tenido». Hace falta un tercer
estado para lo que la institución nunca publicó.

1. Un archivo declarativo `config/periodos_no_publicados.yaml`: por serie y
   período, la evidencia (listado revisado, calendario, consulta CDX) y la fecha.
2. El detector y la interfaz los muestran aparte: ni faltantes ni recuperados.
3. Aplicarlo a lo que B-68 a B-70 demuestren que no existe.

Si esto exige una decisión nueva en `docs/decisiones.md` (qué evidencia basta),
**parar y escalar a Marlon** antes de aplicarlo.

**Criterio:** cada entrada con evidencia verificable; la meta de la sección 1
calculada con este estado.

**Commit:** `feat: estado no publicado con evidencia para periodos inexistentes`

### B-72 · Retirar el agente de la escalera — 30 min

Con presupuesto suficiente propuso 55 direcciones y ninguna existía.

1. `--max-gemini-calls` por defecto en **0** en `scripts/recuperar_periodos.py`.
   El escalón 5 sigue disponible solo de forma explícita.
2. Redactar en el parte la propuesta de decisión para que Marlon la apruebe; no
   escribirla en `docs/decisiones.md` sin su visto bueno.

**Commit:** `chore: el agente queda desactivado por defecto en la recuperacion`

### B-73 · Series de producción cuyo último archivo desapareció — 120 min

De las 192 series de SPIM atrasadas, **19** tienen su último archivo descargado
fuera de línea (30 URLs con 404). Son las de mayor valor para DATAX.

1. Tomarlas de `output/vigencia_spim.json` (estado `ATRASADA`, ver
   `dashboard/vigilancia/data.js` → `ultimo_archivo: NO_DISPONIBLE`). Ojo: el
   campo de URL de SPIM puede traer **varias URLs separadas por `;`**.
2. Para cada una, aplicar la escalera sobre la URL conocida (escalón 1: seguir
   redirección y revisar el directorio superior; escalón 4: archivo histórico).

**Criterio:** tabla de las 19 series con la nueva URL encontrada o el motivo por
el que no se encontró. Los datos de SPIM no se publican fuera del repositorio.

**Commit:** `feat: busqueda de la nueva ubicacion de series de produccion caidas`

### B-74 · Corrida final y cifras — 45 min

```bash
python scripts/construir_vigilancia.py --refrescar
python scripts/detectar_huecos.py --format table
python -m pytest tests/ -q -m "not live"
```

Actualizar `docs/bitacora_equipo.md` con la tabla de la sección 1 completa
(recuperado / no publicado / pendiente por cada faltante) y la meta calculada.

**Commit:** `docs: cierre de la fase 6 con faltantes recuperados o explicados`

---

## 4. Seguimiento

| Bloque | Estimado | Real | Estado |
|---|---:|---:|---|
| B-67 Corrida del INE con el arreglo | 40 min | | Pendiente |
| B-68 Portal nuevo del INE | 120 min | | Pendiente |
| B-69 Faltantes de ASFI | 90 min | | Pendiente |
| B-70 DEPEX jun-25 | 60 min | | Pendiente |
| B-71 Estado «no publicado» | 90 min | | Pendiente |
| B-72 Retirar el agente | 30 min | | Pendiente |
| B-73 Series de SPIM caídas | 120 min | | Pendiente |
| B-74 Corrida final | 45 min | | Pendiente |
| **Total** | **9 h 55** | | |

**Orden:** B-67 primero (confirma que no entran falsos positivos). B-68 a B-70
son independientes entre sí. B-71 después de ellos, porque usa su evidencia.
B-72 y B-73 en cualquier momento. B-74 al final, siempre.
