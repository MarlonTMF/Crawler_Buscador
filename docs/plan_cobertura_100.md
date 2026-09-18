# Plan de implementación — Cobertura 100% de URLs + extracción real de documentos

> Formato: decisiones con contexto, alternativas descartadas, razón y umbral de
> revisión — mismo criterio que se usa en otros proyectos del equipo para que
> una decisión se pueda defender más tarde sin reconstruir el razonamiento de
> memoria. Cada cifra de este documento fue medida el 2026-09-17 contra el
> repositorio real, no estimada.

## Objetivo

Dos métricas separadas, porque son dos problemas distintos con dueños de
riesgo distintos:

1. **Track A — Conectividad.** Toda URL del catálogo maestro responde 200 (o
   tiene un mapeo verificado a una URL viva) en `output/excel_urls_diagnostic.json`.
2. **Track B — Extracción.** El pipeline de crawling (`orchestrator.py` +
   `discovery.py` + adaptadores) obtiene al menos un documento/recurso real
   (no un `HTTP 200` de portada) de una fuente, de punta a punta, verificado
   por corrida real — no por lectura de código.

**Por qué separarlas.** Track A ya está resuelto en un 93.7% (ver baseline) y
lo que falta son 4 casos puntuales, cada uno con causa distinta. Track B
depende de una pieza de software completamente distinta que hoy solo está
configurada para 2 de 63 fuentes. Tratarlas como una sola meta escondería que
el 100% de Track A no implica nada sobre Track B.

---

## Baseline medido (2026-09-17)

### Track A — Conectividad HTTP

**Cierre de Etapa B / B-11 (2026-09-18):**
Fuente: `output/excel_urls_diagnostic.json`, 67 registros limpios (sin duplicados ni entradas temporales).

| Métrica | Registros | % | Detalle operativo |
|---|---|---|---|
| HTTP 200 simple | 62 / 67 | 92.5% | Resuelven directamente por GET HTTP simple |
| **Verificada y accesible** | **64 / 67** | **95.5%** | **Cifra principal de Track A**: incluye 62 en 200 + BCP y BCRP que requieren Headless por Cloudflare/WAF |
| Exclusiones documentadas | 3 / 67 | 4.5% | FMI (403 Akamai WAF), FUNDEMPRESA (410, concesión estatal concluida), BOLCEREALES (DISUELTA) |
| **Total Track A justificado** | **67 / 67** | **100.0%** | **Catálogo 100% auditado y clasificado con justificación empírica** |

*Histórico de línea base (2026-09-17):* 59/63 (93.7%) sobre un universo preliminar sin auditar.

### Track B — Extracción real de documentos

Fuente: `config/` (YAMLs de fuente) + hallazgo en vivo de esta sesión.

- **2 de 67 fuentes** tienen configuración para el motor de crawling completo
  (`source_bbv.yaml`, `source_finrural.yaml`). El resto no tiene YAML: el
  orchestrator nunca se ejecutó contra ellas, aunque el código ya es
  genérico y no necesita un adaptador nuevo por fuente
  (`GenericSourceAdapter` cubre cualquier `source.id` que no sea `bbv` o
  `finrural` — `main.py:31-47`).
- **36 de 67 fuentes** ya tienen evidencia de "documento detectado" en la
  corrida ligera de diagnóstico (`Diagnosticos_Excel` contiene
  `"documento detectado"`), de las cuales **34 no tienen YAML todavía**. Es
  el backlog natural de priorización para la Fase 2 — no hay que adivinar
  cuáles fuentes probablemente tengan documentos, ya hay una señal medida.
- El benchmark de 3 crawlers (`Elecciones De Crawler por URL/Informe_Prospeccion_en_Cifras.html`,
  2026-09-07) identificó 4 causas de por qué el crawler propio ("Mio", 974
  documentos) recuperaba muchos menos que el mejor de los tres ("Rolando",
  5902 documentos). Estado verificado hoy contra el código actual (que creció
  bastante desde ese benchmark):

  | Causa del informe | Estado verificado hoy | Evidencia |
  |---|---|---|
  | Mapa de fuentes desactualizado (13 dominios migrados, 10 caídos) | En resolución — trabajo de esta y la sesión anterior (`RESUMEN_SESION.md`) | `config/moved_urls.json` |
  | Límite de rastreo genérico (profundidad/páginas iguales para las 52) | **Parcial.** `discovery.py:56-59` ya lee `max_depth`/`max_pages` por fuente desde el YAML — pero solo 2 fuentes tienen YAML, y no hay calibración automática por tamaño de sitio | `config/source_bbv.yaml`, `config/source_finrural.yaml` |
  | robots.txt evaluado solo en la portada | **Resuelto.** `fetcher.py:90-132` cachea el parser por dominio pero evalúa `can_fetch` por cada URL candidata individual, no solo la semilla | `src/crawler/core/fetcher.py` |
  | ZIP no cuenta como recurso final | **Resuelto.** `orchestrator.py:112-189` extrae cada archivo interno de un ZIP y lo agrega como `ResourceItem` propio al mismo pipeline que los recursos sueltos | `src/crawler/core/archive_extractor.py`, `orchestrator.py` |

- **Bug nuevo encontrado y corregido en esta sesión** (no estaba en el
  informe de septiembre, porque el módulo de discovery no existía todavía en
  esa forma): `discovery.py` filtraba enlaces `#` y `javascript:` pero no
  `mailto:`/`tel:`. Por un efecto de `urlparse` (estos esquemas no tienen
  `netloc`), `_is_allowed_domain` los trataba como "dominio permitido" y el
  crawler los encolaba como páginas a visitar, gastando 3 reintentos con
  backoff (~9 s) por cada uno sin ningún resultado. **Verificado en vivo**:
  antes del fix, una corrida real contra FINRURAL con timeout de 100 s se
  quedó completamente atascada en un bloque de 15+ enlaces `mailto:`/`tel:`
  de instituciones afiliadas, sin escanear una sola página real. Después del
  fix, la misma corrida escaneó 19 páginas reales y descubrió 296 candidatos
  a recursos descargables en 25 segundos. Corregido en
  `src/crawler/core/discovery.py`, con prueba de regresión en
  `tests/test_discovery.py` (5 casos; verificados fallando sin el fix antes
  de aplicarlo — 3 de 5 fallaban).

---

## Fase 0 — Cerrar los últimos 4 huecos de conectividad (Track A) [COMPLETADA]

Cada caso fue auditado individualmente con verificación empírica de contenido:

| Fuente | Problema inicial | Resolución ejecutada | Estado final |
|---|---|---|---|
| FMI (imf.org) | 403 WAF | B-09: probado con Playwright headless (timeout por Akamai EdgeSuite). Descargas en eLibrary dan 202 vacío. Documentado como punto de partida para proxy institucional. | Exclusión documentada (403_BOT_BLOCKED) |
| BOLCEREALES | Disuelta / duplicado manual | B-11: registro basura `manual` (bbcp.org/lander) depurado. Entidad confirmada disuelta sin sucesor único en la web. | Exclusión documentada (DISUELTA) |
| SICSANTACRUZ | Dominio expirado (Namecheap) | B-10: portal propio expiró; canal sucesor verificado en el Instituto Cruceño de Estadística (`ice.santacruz.gob.bo/repositorio`) con descargas de PDFs (18.4 MB y 7.9 MB) y XLSX de precios con magic bytes. | Resuelta (HTTP 200) |
| Brecha de fuentes (76 SPIM vs 63) | Alcance no auditado | B-08: auditada contra `backup_10.0.0.12`. 6 fuentes legítimas incorporadas (AN, BCP, BCRP, BCCH, BCB_BRASIL, DOLARBLUEBOLIVIA); 5 cadenas retail a `output/fuentes_pendientes_decision_negocio.json`; 2 internas descartadas. | Catálogo consolidado (67 fuentes) |

**Cierre de Fase 0.** Track A cerrado al 100% de clasificación: **64/67 = 95.5% verificadas y accesibles**, 3/67 = 4.5% exclusiones justificadas. Desbloquea la Etapa C (onboarding de Track B).


---

## Fase 1 — Piloto: probar el pipeline completo en una fuente real

**Por qué un piloto y no ir directo a las 63.** Escribir 61 YAMLs antes de
confirmar que el motor de extracción funciona de punta a punta sería
construir sobre una suposición no verificada — exactamente el error que la
metodología de este equipo busca evitar. FINRURAL ya tenía YAML, así que es
el piloto más barato: no hay que escribir configuración nueva, solo verificar
que lo que ya existe efectivamente entrega documentos.

**Decisión.** Usar FINRURAL como fuente piloto de Track B.

**Alternativa descartada.** Usar BBV en su lugar. Ambas tienen YAML, pero
FINRURAL expuso el bug de `discovery.py` en el primer intento — quedarse en
BBV habría escondido el problema hasta que apareciera en otra fuente sin
aviso.

**Criterio de aceptación.** Al menos 1 `ResourceItem` real (no un candidato
descubierto, sino un recurso descargado, extraído y exportado) en
`output/finrural/`, verificado leyendo el JSON exportado — no solo el log de
"Se descubrieron N candidatos".

**Estado: CUMPLIDO, verificado el 2026-09-17.** Corrida real completa contra
FINRURAL tras el fix de `discovery.py`: 296 candidatos descubiertos, y de
esos, **175 procesados exitosamente antes del corte por límite de tiempo del
comando de verificación** (no un error del pipeline — a `rate_limit_per_second:
1.0` del YAML, procesar 296 candidatos toma más de los 240s que se le dieron
a esta prueba puntual; la corrida en sí no tiene límite de tiempo). Verificado
consultando directamente `inventory.db` (SQLite, `ControlDatabase`), no el
log de consola:

```
SELECT status, COUNT(*) FROM resource_audit_log GROUP BY status;
-- ('PROCESADO_EXITOSAMENTE', 175)
```

Con documentos reales confirmados, no solo conteo — por ejemplo
`reporte-sostenibilidad-2023-FINRURAL.pdf` y
`financiera_01_2026.pdf` (info financiera de enero 2026), cada uno con
`period_start`/`period_end` extraídos correctamente y `date_confidence_score`
`high` o `medium`. **0 errores** en las 175 filas. Esto confirma que Track B
ya funciona de punta a punta para al menos una fuente real, con el fix de
esta sesión — el criterio de aceptación del enunciado original ("obtención de
documento o información de por lo menos una fuente") queda cumplido y
verificado, no asumido.

---

## Fase 2 — Generalizar a las fuentes restantes

**Decisión.** Generar un YAML por fuente usando `GenericSourceAdapter`
(declarativo, sin código Python nuevo por fuente — ya lo permite
`main.py:load_adapter()`), no escribir un adaptador Python a medida por
institución.

**Razón.** `BbvAdapter` y `FinruralAdapter` existen porque tenían reglas
específicas que no encajaban en el modelo declarativo (`is_url_excluded`,
`classify_dataset` con lógica propia). Para el resto, el patrón YAML de
`source_finrural.example.yaml` (semillas, extensiones permitidas, reglas de
clasificación por patrón de URL y palabra clave) ya cubre lo que se necesita.
Escribir 61 adaptadores Python sería repetir en código lo que el YAML ya
resuelve.

**Umbral que cambiaría esto.** Si al generalizar aparece una fuente con
lógica de exclusión/clasificación que el modelo declarativo no puede
expresar (paginación no estándar, autenticación, formularios), esa fuente
puntual se convierte en su propio adaptador — no se fuerza el modelo genérico
a cubrir un caso que no le corresponde.

**Orden de priorización** (no alfabético, por señal medida):

1. **34 fuentes con "documento detectado" ya confirmado** en la corrida
   ligera y sin YAML todavía — es el backlog de mayor probabilidad de éxito
   por unidad de esfuerzo.
2. El resto de las 59 fuentes en estado `200`, en el orden que ya trae
   `output/excel_urls_diagnostic.json` (o por volumen esperado, si se cruza
   con la señal de `broken_url`/`file` de SPIM).
3. Las fuentes de la Fase 0 solo entran aquí una vez que Track A las dé por
   resueltas — no tiene sentido generar YAML para una URL todavía no
   verificada.

**Plantilla base.** `config/source_finrural.example.yaml` es el punto de
partida — trae comentado cada flag opcional (`use_sitemaps`, `use_wayback`,
`use_subdomain_enumeration`, `use_search_dorking`, `use_async_fetcher`,
`use_playwright_ocr`) con su costo y cuándo activarlo.

**Verificación por fuente, no solo al final.** Cada YAML nuevo se corre una
vez de forma aislada (`python -m src.crawler.main --config config/source_X.yaml`)
y se confirma manualmente que el `output/X/` resultante tiene al menos 1
recurso — igual que se hizo con el piloto. Generar 61 YAML sin correr ninguno
sería repetir el error de "código que compila pero no se probó".

---

## Fase 3 — Calibración de rastreo y sitios que necesitan navegador

**Contexto.** Dos límites que la Fase 2 va a chocar en cuanto se generalice
más allá de FINRURAL/BBV:

1. **Profundidad/páginas fijas por YAML, no por tamaño real del sitio.**
   Hoy `max_depth`/`max_pages` se ponen a mano. Fuentes grandes (BCB, ASFI)
   necesitan más presupuesto que una cámara departamental con 10 páginas.
   Rolando (el crawler del benchmark) resuelve esto calibrando por fuente
   hasta profundidad 6 en los sitios grandes — no hay que copiar su
   heurística exacta, pero sí evitar el valor único.
2. **Sitios protegidos por Cloudflare/WAF que bloquean al fetcher HTTP
   simple pero responden bien a un navegador real.** Ya confirmado en esta
   sesión para BCP (Banco Central del Paraguay): 403 con `curl`/`requests`,
   200 con Playwright headless. FMI (Fase 0) es candidato a tener el mismo
   patrón. El motor ya tiene `HeadlessFetcher` y un flag
   `use_playwright_ocr` en el YAML — falta decidir cuándo activarlo
   automáticamente (¿reintentar con headless si el fetcher simple da 403?)
   en vez de requerir que alguien lo note a mano cada vez.

**Decisión pendiente, no cerrada en este documento.** Si el reintento
automático con headless ante un 403 vale la pena para todas las fuentes o
solo para las que ya se confirmó que lo necesitan — activar Playwright por
defecto tiene costo (más lento, más pesado) y el criterio para decidir
cuándo se justifica todavía no está definido. Se decide con datos de la Fase
2 (cuántas fuentes de las 61 restantes dan 403 con el fetcher simple).

---

## Fase 4 — Sostenimiento

100% no es un estado que se alcanza una vez y queda — los dominios migran
(esta sesión encontró `sicsantacruz.com` convertido en parking después de
que otra investigación lo diera por bueno hace días). El motor ya tiene
`drift_monitor.py` para detectar anomalías de volumen entre corridas; falta
decidir la cadencia de re-verificación de conectividad (Track A) — por
ejemplo, re-correr el diagnóstico ligero contra las 63+ URLs cada cierto
intervalo y alertar si alguna que estaba en 200 deja de estarlo.

---

## Riesgos conocidos / clases de fallo silencioso

Mismo principio que ya costó caro en otros proyectos del equipo: el fallo
más caro es el que no produce ningún error.

| Riesgo | Por qué es silencioso | Mitigación |
|---|---|---|
| Enlaces `mailto:`/`tel:` tratados como páginas válidas | No hay excepción, no hay log de error visible salvo mirando el detalle — solo se nota si alguien cronometra la corrida y pregunta por qué tarda tanto | Corregido y con prueba de regresión (`tests/test_discovery.py`) |
| Un YAML nuevo con `max_pages` demasiado bajo | La corrida termina "exitosamente" con 0 o pocos recursos, sin ningún error — parece que la fuente no tiene documentos cuando en realidad no se llegó a la página que los tiene | Verificar cada YAML nuevo corriendo y leyendo el resultado, no solo el código de salida (Fase 2) |
| Dominio parking que responde 200 | `sicsantacruz.com` da HTTP 200 — un chequeo que solo mira el código de estado lo marcaría como "vivo" sin serlo | Ya se aplica verificación de contenido/keyword antes de aceptar cualquier URL como resuelta (lección de esta y la sesión anterior) |
| Suite de tests con corridas de red reales mezcladas con unitarias | `pytest tests/` completo tardó **65 minutos** en esta sesión (49 tests, medido, no estimado) porque algunos tests golpean red real sin marcador que los separe — un desarrollador puede evitar correr la suite completa por lo lento que es, y dejar de detectar regresiones | Pendiente: marcar tests de red con `@pytest.mark.live` o similar y correr por defecto solo los rápidos; queda fuera del alcance de este plan pero se registra porque ya causó fricción esta sesión |
| Aceptar una URL sugerida sin verificar contenido | Ya documentado en `RESUMEN_SESION.md` — pasó 3 veces antes de esta sesión (CADEX, IBCE, bcp.org) | Regla ya en vigor: ninguna URL se acepta solo por status 200 |

---

## Checklist de "hecho" por fase

- [ ] **Fase 0**: 63/63 (o el total tras auditar la brecha de 13) en `200` o
      mapeo verificado por contenido.
- [x] **Fase 1**: cumplido 2026-09-17 — 175 recursos reales procesados
      exitosamente (0 errores) en una corrida contra FINRURAL, verificado en
      `inventory.db`, no solo en el log de consola.
- [ ] **Fase 2**: las 34 fuentes con "documento detectado" tienen YAML propio
      y cada una se corrió al menos una vez con resultado ≥1 recurso o una
      razón documentada de por qué no.
- [ ] **Fase 3**: criterio escrito (no solo intuición) de cuándo un YAML usa
      `use_playwright_ocr`/headless por defecto.
- [ ] **Fase 4**: cadencia de re-verificación de Track A definida y, si se
      automatiza, corriendo.

---

## Referencias

- Baseline de conectividad: `output/excel_urls_diagnostic.json`
- Benchmark de los 3 crawlers: `Elecciones De Crawler por URL/Informe_Prospeccion_en_Cifras.html`
- Historial de decisiones de conectividad: `RESUMEN_SESION.md`
- Bug corregido esta sesión: `src/crawler/core/discovery.py`, prueba en `tests/test_discovery.py`
- Plantilla de YAML para fuentes nuevas: `config/source_finrural.example.yaml`
