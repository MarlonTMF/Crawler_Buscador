# Decisión B-33 · API y formularios en el pipeline de extracción

- **Fecha:** 2026-09-19
- **Decide:** Claude (auditor / líder técnico)
- **Responde a:** `docs/diagnostico_b33_api_formularios.md` (parada obligatoria de `docs/plan_bloques_fase2.md:170-175`)
- **Implementa:** Antigravity

---

## Veredicto

**SE PARTE EN DOS BLOQUES.** No se aprueba la propuesta acotada tal como está
escrita, porque mete dos mecanismos independientes —y de riesgo muy distinto—
en un solo commit, y solo uno de los dos tiene criterio de aceptación
verificable.

| Bloque | Alcance | Estimado | Condición |
|---|---|---:|---|
| **B-33a** | Consumo declarativo de endpoints JSON + SICSANTACRUZ | 70 min | Aprobado, se implementa |
| **B-33b** | Expansión de formularios GET en el descubrimiento | 45 min | **Condicionado**: se implementa solo si el Paso 0 encuentra un caso real |

### Por qué se parte

1. **El criterio de aceptación de B-33 solo mide la mitad API.** "SICSANTACRUZ
   pasa de 0 a ≥ 10 documentos vía la API" no dice nada sobre formularios. Un
   commit único haría entrar la integración de formularios al motor sin ninguna
   evidencia que la respalde — y el proyecto ya tiene cuatro incidentes
   registrados con esa misma forma.

2. **La mitad "formularios" no desbloquea los casos que el plan le asignó.** El
   propio diagnóstico (§1.B) establece que `FormAutomator` no maneja POST ni
   `__VIEWSTATE`, y que SICOES e INE son exactamente eso. Escribir la
   integración para esos dos casos es escribir superficie de motor sin usuario.
   De ahí el Paso 0 obligatorio de B-33b.

3. **El riesgo no es del mismo tipo.** El camino API es aditivo y aislado: si
   una fuente no declara endpoints, no pasa nada. La expansión de formularios
   escribe dentro del bucle BFS de `discover_from_seeds`, multiplicando
   producto cartesiano × páginas visitadas. Es la forma exacta del bug D-06
   —encolar basura y quemar el presupuesto de páginas sin error visible—. Los
   dos no comparten commit.

---

## Rechazo parcial: `api_detector.py` NO se conecta al pipeline

La propuesta del diagnóstico deja abierta la puerta a que
"`api_detector` descubra un endpoint soportado" y el extractor lo consuma
(§3.2). **Eso queda fuera de alcance, y no por tiempo: por diseño.**

- `probe_domain_for_apis` hace ~25 sondeos ciegos contra rutas conocidas por
  dominio. Aplicado al pipeline de extracción es **D-02 trasladado a APIs**:
  sondeo especulativo que en el 95% de los portales devuelve 404 y cuesta
  tiempo real.
- El diagnóstico ya concluye (§1.A) que el módulo no produce candidatos por sí
  solo. Conectarlo obliga a escribir igual la capa de traducción JSON →
  `DownloadCandidate`; el detector no ahorra ese trabajo, solo agrega la parte
  cara.
- Para SICSANTACRUZ el endpoint **ya está verificado y es conocido**. Un dato
  verificado se escribe en el YAML; no se re-descubre en cada corrida.

`api_detector.py` sigue siendo lo que es: el generador del reporte diagnóstico
`output/reporte_apis.md`. **Lo único que B-33a reutiliza de él es `RobotsGate`.**
Si en el futuro hace falta autodescubrir endpoints, será un bloque propio con
su propio criterio.

---

## Pautas de implementación — B-33a

### Alcance en archivos

- **Nuevo:** `src/crawler/core/api_consumer.py`.
- **Modificado (uno solo del motor):** `src/crawler/core/discovery.py`.
- **No se toca:** `orchestrator.py`, `api_detector.py`, `fetcher.py`,
  `generic_adapter.py`.
- **Nuevo:** `config/source_sicsantacruz.yaml`, `tests/test_api_consumer.py`.

Si la implementación empieza a necesitar tocar `orchestrator.py`, **parar**: el
diseño se desvió.

### Punto de enganche

Uno solo: dentro de `DiscoveryEngine.discover_from_seeds`, junto a
`self._add_passive_candidates(candidates)` (`discovery.py:322`). Mismo patrón
que wayback y search dorking, que ya está probado en producción. El consumidor
devuelve `DiscoveredCandidate` con `url_origin="api"` y desde ahí todo el flujo
—canonicalización, fecha, bytes, `inventory.db`, `mapa_<fuente>.json`— es el
existente, sin ramas nuevas.

`url_origin="api"` no es cosmético: es el mismo requisito de distinguir
procedencia que B-32 impuso para `wayback`.

### Configuración YAML

Sección nueva bajo `crawl:`:

```yaml
crawl:
  api_endpoints:
    - url: "https://ice.santacruz.gob.bo/api/estudios?populate=*"
      pagination: strapi_v4      # strapi_v4 | none
      max_pages: 10
```

**Ausencia de `api_endpoints` ⇒ cero peticiones y comportamiento idéntico al
actual.** Esa es la condición para que las 28 fuentes ya onboardeadas y los 52
tests rápidos sigan verdes sin tocar nada.

### Cómo se extraen las URLs del JSON — decisión de diseño

**Barrido recursivo del payload**: recorrer el JSON, y por cada valor string,
resolverlo con `urljoin` contra la URL del endpoint; si el resultado termina en
una de las `allowed_extensions` del adaptador, es candidato.

**No implementar JSONPath ni un mini-lenguaje de rutas configurable.** La ruta
que encontró el diagnóstico (`attributes.documento.data.attributes.url`) es
específica de una fuente y de una versión de Strapi; el barrido recursivo cubre
Strapi, CKAN y OData con menos código y sin configuración por fuente. Si alguna
fuente futura sobre-recoge, ahí se agrega un `items_path` opcional — no antes.
Esto es D-07 aplicado al modelo de API: declarativo y mínimo.

Las URLs de Strapi vienen relativas (`/uploads/ICE_..._d35da0e2d6.pdf`). El
`urljoin` no es opcional.

### Límites duros (esto es lo que evita el desborde)

- `max_pages` por endpoint, default 10, con tope absoluto en el código.
- Parar cuando una página no aporta candidatos nuevos, o cuando la respuesta no
  parsea como JSON. No reintentar en bucle.
- Respetar el `rate_limit` del adaptador entre páginas.
- `RobotsGate` sobre la URL del endpoint antes del primer GET.
- Las URLs resueltas pasan por `_is_allowed_domain` y `adapter.is_url_excluded`
  igual que cualquier enlace de HTML. Un endpoint no es excepción al dominio
  permitido.

### YAML de SICSANTACRUZ — dos trampas concretas

1. **`allowed_domains` debe incluir `ice.santacruz.gob.bo`.** Los documentos
   viven en `/uploads/` de ese mismo host; si falta, `_is_allowed_domain` los
   descarta en silencio y el bloque "corre bien" con 0 documentos.

2. **Escribir `dataset_rules` explícitas.**
   `GenericSourceAdapter.classify_dataset` (`generic_adapter.py:33`) devuelve
   `dataset_rules[0].id` para todo lo que no matchee. O sea: nada se descarta,
   pero **los 163 documentos caen en un único dataset** y el `mapa_` sale
   inútil. Separar al menos las series que el catálogo ya evidencia —boletín
   estadístico agropecuario y monitoreo de precios—.

**Sobre la identidad institucional (D-01):** ya está resuelta y no se reabre.
El catálogo registra `Final_Url: https://ice.santacruz.gob.bo/repositorio` con
`matched_keywords: ["sic santa cruz", "precios", "agropecuario"]`, resuelto en
B-10. Lo único que hay que confirmar es que `/api/estudios` cuelga de ese mismo
host — cosa que el diagnóstico ya verificó.

### Tests (regla CLAUDE.md #3: verlos fallar antes)

1. **Extracción sobre payload fijo**, fixture en disco, sin red: N URLs
   extraídas, relativas resueltas, `max_pages` respetado. Marcado `not live`.
2. **No-regresión:** un YAML sin `api_endpoints` no dispara ninguna petición —
   mock del fetcher, aserción sobre `call_count == 0`. Esta es la prueba que
   protege a las otras 28 fuentes.

Ambas tienen que verse en rojo antes del fix, y esa salida va pegada en el
parte. La disciplina de D-06 no es opcional acá: el bloque toca el motor.

### Evidencia de aceptación (qué va pegado en `docs/entregas/B-33a.md`)

```bash
python -m src.crawler.main --config config/source_sicsantacruz.yaml --output-dir output
```

- Conteo **leído de `inventory.db` con SQL**, nunca del log de consola.
- Primeros bytes de **3** archivos descargados al azar (`%PDF`, `PK`), no solo
  el status HTTP.
- Suite rápida contra worktree limpio de HEAD con `PYTHONPATH`
  (`docs/protocolo_equipo.md`, §Verificación contra HEAD limpio).

**No poner tope artificial en 10.** El criterio dice "≥ 10"; hay 163
disponibles. Correr el endpoint completo y reportar el número real obtenido.

**Commit:** `feat: consumo declarativo de endpoints json en el descubrimiento`

---

## Pautas de implementación — B-33b (condicionado)

### Paso 0, obligatorio, antes de escribir una línea de código (15 min)

Identificar en el catálogo **al menos una fuente con un `<form method="get">`
real cuyas combinaciones devuelvan documentos**. Evidencia: el HTML del
formulario y una URL generada a mano que descargue bytes.

- **Si no aparece ninguna**, B-33b cierra como **no implementado**, con esa
  evidencia escrita. Es un resultado válido y se registra en `AI_LOG.md`. No se
  agrega maquinaria al motor para cero usuarios.
- **Si aparece**, se implementa con las pautas de abajo y ese caso pasa a ser el
  criterio de aceptación del bloque.

### Si se implementa

- Detrás de un flag `crawl.expand_get_forms`, **default `false`**.
- `max_combinations` configurable y bajado del 200 actual a lo que el sitio
  concreto justifique.
- Las URLs generadas entran a la cola **con `depth + 1`** y **cuentan contra
  `max_pages`**. Nunca fuera del presupuesto de páginas: ese es el punto donde
  el bloque se puede convertir en D-06 otra vez.
- Criterio de aceptación: la fuente del Paso 0 pasa de N a > N documentos
  verificados por bytes, **y** una fuente sin formularios no cambia su conteo
  entre dos corridas (no-regresión medida, no asumida).

### Fuera de alcance, explícitamente

**SICOES e INE se retiran como casos objetivo.** Son POST con `__VIEWSTATE` /
CSRF; `FormAutomator` no puede expresarlos y forzarlos sería exactamente lo que
D-07 prohíbe. Quedan anotados para la fase de conectores especializados, junto
a CEPAL (D-10).

**Commit:** `feat: expansion de formularios get en el descubrimiento`

---

## Ambigüedad adicional detectada y resuelta

`docs/decisiones.md` D-11, punto 2, dice que los **generadores paramétricos de
URL** para series históricas quedan "formalizados en B-33 para ASFI-IFD". No
están implementados —no hay nada parecido en `src/` ni en `config/`— y **no
entran en B-33a ni en B-33b**.

Razón: es un tercer mecanismo, independiente de API y de formularios, y con su
propio riesgo (enumerar rutas inventadas es D-02 aplicado a documentos). Meterlo
acá desbordaría el bloque por la misma vía que el diagnóstico quería evitar.

Queda como pendiente explícito con destino propio. Se registra en `AI_LOG.md` y
la referencia a "B-33" en D-11 pasa a leerse como "pendiente, bloque sin
asignar".
