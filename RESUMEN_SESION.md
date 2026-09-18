# Resumen de sesión — Prospector de Datos Web / DataX

> Pegá este archivo entero como primer mensaje de un chat nuevo para retomar sin
> volver a explicar el contexto. Fecha de corte: 2026-09-17 (actualizado en la
> misma fecha, segunda pasada: se aplicó `URLsFaltantes.md`, se resolvió BCP y
> Aduana, y se cerraron las decisiones de CADECO y NIH — ver abajo).

## Qué es esto

`crawler_finrural` es un prototipo de crawler/prospector de datos web para DataX
(institución financiera boliviana + entorno multi-fuente). Es **una propuesta
propia**, no la base oficial del equipo — el sistema de producción real es
**SPIM**, cuya base de datos (`platform_db`) analizamos aparte a partir de un
backup. Un compañero también presentó una propuesta de arquitectura C4 +
backlog para un "Prospector" nuevo, que revisamos por separado.

## Qué se construyó en esta sesión (código reusable)

- **`src/crawler/core/api_detector.py`** + **`generate_api_report.py`** +
  `scripts/render_api_report_pdf.py` — detecta si un sitio institucional
  expone una API pública y si tiene documentación (Swagger/OpenAPI/WSDL).
  Sondeo activo + subdominios + bundles JS + tráfico de red (Playwright,
  opcional). Genera `output/api_report.{json,md,pdf}`.
- **`src/crawler/core/url_resolver.py`** + **`resolve_dead_domains.py`** —
  resolución **automática y auditable** de dominios muertos: (1) le pregunta a
  Gemini qué pasó, (2) si la sugerencia no responde, le prueba variantes
  mecánicas (www, TLD, esquema) — el "intercambio Gemini↔motor de variantes",
  (3) **nunca acepta un candidato sin verificar que su contenido mencione la
  institución real** (filtra por palabras clave del nombre). Todo intento
  queda logueado en `output/url_resolution_log.json` con la respuesta cruda
  de la IA. Solo escribe a `config/moved_urls.json` +
  `output/excel_urls_diagnostic.json` cuando el contenido está verificado.
- **Fix en `src/crawler/core/fetcher.py`**: la lista de modelos Gemini estaba
  obsoleta (`gemini-2.0-flash`/`1.5-*` ya no existen en la API); se actualizó
  a modelos vigentes. También se le agregó el mismo "intercambio de
  variantes" a `_probe_gemini_alternatives`.
- Tests: `tests/test_api_detector.py`, `tests/test_url_resolver.py` (18 tests,
  todos verdes).

## Lecciones aprendidas — no repetir estos errores

1. **Nunca aceptar una URL sugerida por IA sin verificar contenido.** Ya
   pasó 3 veces: Gemini sugirió `cadex.org` para CADEXCO (era CADEX Santa
   Cruz, institución distinta), `ibce.org.bo` para IBCH (era IBCE, comercio
   exterior, no cemento/hormigón), y el propio `fetcher.py` escribió
   automáticamente `bcp.org` para BCP sin verificar (se detectó y se borró
   de `moved_urls.json` antes de que contaminara el dataset).
2. **`allow_variants=True` es solo para dominios raíz muertos**, no para
   URLs de reportes/documentos específicos que fallan — usarlo ahí generó
   sondeos larguísimos y resoluciones sin sentido (probó variantes de una
   URL con ruta completa). Para verificar una URL puntual, chequeo directo
   simple (GET con headers de navegador), sin variantes.
3. **Circuit breaker necesario** en cualquier sondeo masivo de rutas — un
   dominio que acepta conexión pero nunca responde puede colgar un script
   30+ minutos si no hay corte por fallos consecutivos.
4. **GEMINI_API_KEY tiene cuota diaria limitada** (dos claves distintas ya la
   agotaron en la misma sesión). No relanzar llamadas en loop corto; esperar
   al reset diario.
5. **El backup de la base (`backup_10.0.0.12`)** tiene contraseñas en texto
   plano y permisos excesivos (`pasante03` con `GRANT ALL` a nivel de base
   completa). **Nunca publicar como Artifact público** nada que mencione esos
   hallazgos — el clasificador de seguridad ya bloqueó un intento. Se generan
   como **archivos HTML locales** (`output/informe_backup_platform_db.html`)
   y se abren con `Start-Process` en PowerShell, nunca se comparten por link.
6. El archivo `backup_10.0.0.12` está en `.gitignore` (no estaba cubierto
   originalmente — se agregó a mano).

## Hallazgos clave de la base real (SPIM / `platform_db`)

Análisis completo en `output/informe_backup_platform_db.html` (local).
Puntos que importan para seguir trabajando:

- 28 tablas, ~198.700 filas, fusión de dos subsistemas (uno en español para
  seguimiento manual de operadores, otro en inglés para el pipeline
  automatizado con Airflow).
- `source` tiene **74 fuentes institucionales reales** — el universo real de
  cobertura, mucho más grande que los "5" del backlog del compañero.
- `broken_url` (218 filas / 42 archivos) está **desactualizado desde mayo
  2025** — no refleja el estado actual.
- Integridad relacional débil (solo 8/28 FK reales), tipos inconsistentes
  entre tablas (`report.id_file` es bigint, el resto integer), `file9` es
  un resto de migración sin PK.
- Lógica de negocio real vive en funciones PL/pgSQL (`asignar()`,
  `log_file_alert()`, `moda()`) — hay que portarla en cualquier reescritura.

## Documentos/artifacts publicados (links)

- **Radar de APIs** — `https://claude.ai/code/artifact/2e359614-8c69-44ae-9f82-aff9251ac4a0`
- **Revisión del Backlog Prospector** (arquitectura del compañero) — `https://claude.ai/code/artifact/15228e01-8ddf-4e30-9100-208fc46a501a`
- **Plan de equipo Prospector** (3 personas, 6 semanas) — `https://claude.ai/code/artifact/6155e14a-63fb-49cb-a6a8-e922890786fc`
- **Cobertura de Fuentes** — `https://claude.ai/code/artifact/b5d797bb-a8d2-4964-b6d6-a45ac9de2223`
- **Plan Cobertura 100%** (6 fases + resultado Fase 1) — `https://claude.ai/code/artifact/42445e4a-63a7-484b-9552-10fe0367cd1d`
- Informe de la base de datos: **solo local**, `output/informe_backup_platform_db.html`

## Estado de cobertura (última medición)

Universo reconciliado: **76 fuentes** (74 de SPIM + 5 propias, menos 3
duplicadas por nombre). Con la Fase 1 ya ejecutada: **26/32 URLs del Grupo A
confirmadas OK**. Quedaban 6 pendientes de las cuales solo 2 eran dominios
realmente muertos (el resto: BCP bloqueado 403, un link puntual de Aduana
movido).

## Lo que se acaba de recibir (`URLsFaltantes.md`, raíz del proyecto)

Investigación externa (Claude con búsqueda web) sobre las 11 instituciones
sin resolver. **Resultado, con fuentes citadas y nivel de confianza:**

| Fuente | Resultado | Confianza |
|---|---|---|
| CADEXCO | Dominio corregido: `cadexco.bo` (no `.org.bo`) | Alta |
| IBCH | Dominio corregido: `ibch.com` (no `.org.bo`) | Alta |
| SISPAM | Renombrada a OAP: `observatorioagro.gob.bo` | Alta |
| SPVS | Disuelta 2009/2013 (DS 0071, Ley 365) → **APS** (pensiones/seguros) + **ASFI** (valores) | Alta |
| SUPTRANS | Disuelta 2009 (DS 0071) → **ATT** (`att.gob.bo`) | Alta |
| IN | Es el SIN: `impuestos.gob.bo` | Alta |
| SICSANTACRUZ | Real y vigente: `sicsantacruz.com` | Alta |
| OBA | Absorbida por SEA: `sea.gob.bo/centro-de-datos-autonomicos` | Media |
| CADECO | Ambiguo — hay varias por departamento (La Paz, Cochabamba, Santa Cruz, Chuquisaca tienen sitio propio) | Media |
| NIH | **No es boliviana** — es NIDA (EE.UU.), registro mal cargado | Alta |
| BOLCEREALES | Confirmado: inactiva, sin sucesor único (coincide con lo que ya sabíamos) | Media |

## Qué se cerró en la segunda pasada (misma fecha, 2026-09-17)

1. **Bug fix**: `config/moved_urls.json` tenía una coma colgante — JSON
   inválido. Corregido.
2. **Aplicado `URLsFaltantes.md`** a los 3 registros que sí existían en el
   dataset de 54 (`output/excel_urls_diagnostic.json` + `moved_urls.json`):
   CADEXCO → `cadexco.bo`, IBCH → `ibch.com` (ambos verificados por
   contenido, no solo por status 200), BOLCEREALES → marcada `DISUELTA` sin
   sucesor (dominio confirmado caído, DNS no resuelve).
3. Las otras **8 instituciones de `URLsFaltantes.md`** (SISPAM, SPVS,
   SUPTRANS, IN, SICSANTACRUZ, OBA, CADECO, NIH) **no existían como
   registros** en el dataset de 54 — pertenecen al universo de 74 fuentes de
   SPIM que solo se había analizado desde el backup, nunca cargado al
   pipeline. Se agregaron como **registros nuevos** (SPVS se dividió en
   SPVS-APS y SPVS-ASFI). Hallazgo importante: `sicsantacruz.com`, reportado
   como "confianza alta" por la investigación externa, hoy es una **página de
   parking de Namecheap** (dominio expiró y fue re-registrado por un
   tercero) — no se aceptó, queda marcada `unreachable_parking` para
   re-investigar. También fallan DNS `caboco.org` y
   `cadecochuquisaca.org.bo`, pese a estar listados como vivos.
4. **BCP (Banco Central del Paraguay) resuelto**: no está muerto — Cloudflare
   bloquea clientes HTTP simples (curl/requests → 403 o challenge JS) pero el
   sitio responde 200 con navegador headless real. Las 3 URLs de documentos
   rotas se remapearon a la nueva estructura del sitio: `tipo-de-cambio`,
   `informe-de-indicadores-financieros-if`, `informe-de-politica-monetaria-ipom`
   (esta última confianza media). **Importante para el crawler**: este
   dominio necesita `HeadlessFetcher`, el fetcher HTTP simple siempre va a
   fallar ahí.
5. **Aduana Nacional resuelto**: el link roto del boletín de recaudaciones
   (`aduana7/content/...` → 404 tras rediseño del sitio) se remapeó a
   `aduana.gob.bo/com_boletines`, verificado por título de página.
6. **DATAX confirmado como entrada interna nunca operativizada**: se accedió
   directamente al backup real (`backup_10.0.0.12`, tabla `source`) con la
   librería `pgdumplib` (no hace falta levantar Postgres). DATAX (id=22)
   tiene `homepage='vacio'` y cero archivos en la tabla `file`, igual que
   otras 42 fuentes cargadas en bloque el 2022-11-01 y nunca conectadas a un
   pipeline real.
7. **NIH — decisión cerrada con evidencia de la BD**: mismo hallazgo que
   DATAX. NIH (id=46) está en el mismo lote sin homepage/archivos que FMI,
   BM, OMC, ITU, ICCO, FIFA, UNDATA, Data.Gov, TRANSTATS y Statistics
   Denmark — todas fuentes internacionales de referencia cargadas a
   propósito. No hay ningún indicio de que debiera apuntar a otra
   institución boliviana; el nombre truncado "National Institute on Drug" es
   NIDA (National Institute on Drug Abuse, EE.UU.) con la carga incompleta.
   Confirmada como fuente internacional, **sin reasignación pendiente**.
8. **CADECO — decisión de política, no recuperable de la BD**: el registro
   original (id=18) nunca especificó departamento (nombre genérico,
   `homepage` vacío, sin archivos ni observaciones) → es indeterminable con
   los datos disponibles, no un dato perdido. Se fija **La Paz**
   (`cadecolp.org`) como registro canónico por decisión de política (sede,
   verificado vivo), documentado explícitamente como tal. Si se quiere
   cobertura completa, desdoblar en entradas por departamento — Cochabamba y
   Santa Cruz también viven; Chuquisaca y el paraguas CABOCO no.

## Qué sigue (en orden)

1. Actualizar los artifacts publicados (Cobertura de Fuentes, Plan Cobertura
   100%) con los números finales de esta pasada.
2. **MX** ya se descartó — el archivo asociado se llama literalmente
   "Uruguay test", es data de prueba, no una fuente real.
3. Re-investigar `sicsantacruz.com` más adelante (hoy es dominio de parking)
   y considerar si vale la pena re-registrar el dominio o buscar un
   reemplazo institucional.
4. Si se decide desdoblar CADECO por departamento, usar las URLs ya
   verificadas: La Paz `cadecolp.org`, Cochabamba `cadecocbba.com`, Santa
   Cruz `cadecocruz.org.bo`.
5. Pendiente aparte, no bloqueante: los 23 archivos de SPIM con señal de
   atención vigente (BCB×10, BCRP×3, BBV×2...) — requiere coordinación con el
   equipo que opera SPIM, no es trabajo de este pipeline.

## Archivos clave

- `output/excel_urls_diagnostic.json` — dataset maestro (54 registros)
- `config/moved_urls.json` — mapeos de dominio confirmados
- `output/url_resolution_log.json` — auditoría completa de resoluciones (con
  respuesta cruda de la IA en cada intento)
- `backup_10.0.0.12` — dump de la DB real (gitignored, sensible)
- `URLsFaltantes.md` — investigación externa recién recibida (raíz del repo)
- `generate_api_report.py`, `resolve_dead_domains.py` — scripts ejecutables
- `.env` — tiene `GEMINI_API_KEY` (clave real, no committear)
