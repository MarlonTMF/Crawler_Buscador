# Prospector DataX / crawler_finrural

Prospector de datos web para instituciones financieras/multilaterales
bolivianas y de comercio exterior. Prototipo propio del equipo — el sistema
de producción real es **SPIM** (`platform_db`), analizado aparte desde un
backup (`backup_10.0.0.12`, gitignored, sensible).

**Las decisiones están escritas en `docs/decisiones.md` (D-01 a D-08). Léelo
antes de proponer cambios de arquitectura o de reabrir algo ya resuelto —
están cerradas y no se reabren sin una razón nueva.**

**El plan de trabajo activo está en dos niveles:**

- `docs/plan_cobertura_100.md` — las **fases** (qué y por qué), con el
  baseline medido.
- `docs/plan_bloques.md` — los **bloques** (cómo, cuánto y con qué commit).
  Cada bloque cierra con un commit y deja el repositorio en verde. Rellená la
  columna **Real** de las tablas de seguimiento al cerrar cada bloque.

Actualizá ambos cuando algo cambie de estado; no los dejes desincronizados
del código real. Lo que se aprendió por el camino —una corrección, un
descarte, una verificación que cambió el rumbo— va a `AI_LOG.md`, con el
razonamiento y no solo el hecho.

**El trabajo se reparte entre dos asistentes.** `docs/protocolo_equipo.md`
define quién hace cada bloque (Antigravity ejecuta, Claude decide lo ambiguo
y audita), qué se entrega por bloque (`docs/entregas/B-NN.md`) y cuándo hay
que parar y escalar en vez de decidir. Leelo antes de tomar un bloque.

## Objetivo del proyecto (dos metas separadas, no una — ver D-04)

1. **Track A — Conectividad.** Toda URL del catálogo (`output/excel_urls_diagnostic.json`)
   responde `200` o tiene un mapeo verificado por contenido en
   `config/moved_urls.json`. Baseline medido 2026-09-17: 59/63 (93.7%).
2. **Track B — Extracción real de documentos.** El motor de crawling
   (`orchestrator.py` + `discovery.py` + adaptadores) obtiene al menos un
   documento real por fuente, verificado corriendo el pipeline y leyendo
   `inventory.db` o el JSON exportado — nunca solo el log de consola.
   Baseline: 2/63 fuentes configuradas, piloto FINRURAL validado (175
   documentos reales, 0 errores).

## Reglas del proyecto

**Ninguna URL se acepta sin verificar contenido (D-01).** Un status 200 no
prueba que sea la institución correcta — pasó 3 veces antes de esta regla
(CADEX Santa Cruz por CADEXCO, IBCE por IBCH, bcp.org por BCP) y una cuarta
vez que la regla ya detectó (`sicsantacruz.com`, dado por bueno por una
investigación externa, resultó ser un dominio de parking al verificarlo).
Toda resolución de URL lleva `reason` + `matched_keywords` en
`config/moved_urls.json` y queda auditada en `output/url_resolution_log.json`.

**`allow_variants=True` solo para dominios raíz muertos (D-02).** Nunca para
URLs de documentos/reportes puntuales que fallan — genera sondeos sin
sentido.

**Un 403 no es un dominio muerto (D-03).** Antes de descartarlo, probar con
`HeadlessFetcher` (`wait_until="domcontentloaded"`, no `"networkidle"` — con
`networkidle` un sitio con Cloudflare Challenge nunca llega a inactividad de
red y da timeout). BCP respondió 200 con navegador real tras dar 403 con
`curl`/`requests`.

**Fuentes nuevas: YAML declarativo, no adaptador Python (D-07).** Usar
`GenericSourceAdapter` sobre la plantilla `config/source_finrural.example.yaml`.
Solo escribir un adaptador Python a medida si una fuente puntual tiene lógica
que el modelo declarativo no puede expresar (paginación no estándar,
autenticación, formularios dinámicos) — y en ese caso, solo para esa fuente.

**Ningún YAML nuevo se da por bueno sin correrlo.** Generar 61 YAML sin
verificar ninguno sería el mismo error que "código que compila pero nunca se
ejecutó". Cada fuente nueva se corre aislada
(`python -m src.crawler.main --config config/source_X.yaml`) y se confirma
≥1 recurso real en `output/X/` o en `inventory.db` antes de marcarla como
lista.

## Comandos

```bash
# Verificación rápida (8s, 52 tests) — usar durante el desarrollo
python -m pytest tests/ -q -m "not live"

# Suite completa (65 min, incluye 2 tests que tocan red real) — antes de cerrar una fase
python -m pytest tests/ -q

# Correr el motor de extracción contra una fuente
python -m src.crawler.main --config config/source_finrural.yaml --output-dir output

# Diagnóstico ligero de conectividad (Track A)
python resolve_dead_domains.py --fuente NOMBRE_FUENTE --dry-run   # revisar antes de escribir
python resolve_dead_domains.py --fuente NOMBRE_FUENTE             # aplicar si el veredicto es 'resolved'
```

## La clase de error que más ha costado en este proyecto

Todos con la misma forma: **algo que no produce ningún error visible y
simplemente desperdicia tiempo o da un resultado sin verificar.**

| Qué pasó | Cómo se detectó |
|---|---|
| `discovery.py` encolaba `mailto:`/`tel:` como páginas crawleables (D-06) | Corriendo el pipeline real contra FINRURAL — se atascó 100s en enlaces de contacto sin escanear una página real. No apareció leyendo el código ni en tests unitarios con mocks. |
| 2 tests de `test_validation_engine.py` escapan su propio mock y hacen red real (D-08) | La suite completa tardaba 65 min; aislando test por test con timeout corto se encontraron los 2 responsables |
| Gemini sugirió `bcp.org`/`ibce.org.bo`/`cadex.org` para instituciones distintas (D-01) | Verificación de contenido obligatoria, no solo status 200 |
| `sicsantacruz.com` dado por "confianza alta" en una investigación externa resultó ser parking de dominio | Verificado con `curl` + grep de palabra clave antes de aceptarlo — el HTML tenía el comentario `<!-- Send the parked domain's origin as the referrer -->` |
| `config/moved_urls.json` tenía una coma colgante — JSON inválido desde hacía tiempo | Nadie lo cargaba con `json.load` hasta que se necesitó editarlo a mano |

**La causa común: verificar el status/artefacto, no el efecto real.** Un
`200` no prueba contenido correcto; un log que dice "candidatos descubiertos"
no prueba que se descargaron; un mock que compila no prueba que intercepta
la llamada real.

### Qué hacer en consecuencia

1. **Antes de aceptar una URL resuelta, verificar contenido** — no alcanza
   con el status code (D-01).
2. **Antes de dar una fuente por onboardeada en Track B, correrla y leer
   `inventory.db`** — no alcanza con "se descubrieron N candidatos" en el
   log.
3. **Una prueba de regresión no vale hasta verla fallar.** Se aplicó con
   D-06: se hizo `git stash` del fix y se confirmó que 3 de 5 casos fallaban
   antes de restaurarlo.
4. **Si algo tarda sospechosamente, medirlo con un timeout corto por test
   individual**, no asumir que "la red está lenta hoy" (D-08).

## Forma de trabajo

- **Un bloque, un commit.** El trabajo se organiza en bloques
  (`docs/plan_bloques.md`); cada uno cierra con un commit propio y con la
  suite rápida en verde. Si un bloque no puede cerrar con un commit que se
  sostenga solo, está mal dimensionado y hay que partirlo.
- **Nunca `git add -A`.** Cada commit agrega sus archivos por nombre — hay
  trabajo de varias sesiones mezclado en el árbol y un `add -A` lo aplasta en
  un commit ilegible.
- Formato de commit: `tipo: descripción en minúscula, imperativa, en español`,
  con viñetas que expliquen el porqué cuando no es obvio. Tipos: `feat`,
  `fix`, `test`, `docs`, `chore`, `refactor` y `data` (este último para el
  catálogo de fuentes, que es el entregable de Track A).
- Antes de un cambio que toque más de un archivo del motor de extracción
  (`orchestrator.py`, `discovery.py`, adaptadores), proponer el plan y
  esperar aprobación.
- Al corregir algo que salió mal, o al descartar una alternativa, registrarlo
  en `docs/decisiones.md` con el razonamiento — no solo el hecho. El formato
  es: Contexto → Alternativas descartadas → Decisión → Razón → Consecuencia
  → Umbral que la reabriría → Verificado el (fecha).
- No escribir en código ni en documentos ninguna cifra que no se haya
  verificado contra su fuente (correr el comando, no estimarlo).
- Subagentes disponibles en `.claude/agents/`: `conectividad-auditor` (Track
  A, Fase 0), `fuente-onboarder` (Track B, Fase 2), `revisor` (revisión de
  código antes de cerrar una fase). Ver cada archivo para su alcance exacto
  y qué NO debe reabrir.
