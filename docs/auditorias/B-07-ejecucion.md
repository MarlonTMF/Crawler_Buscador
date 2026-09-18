# Auditoría B-07 · ejecución (Commits A y B)

- **Auditado por:** Claude
- **Fecha:** 2026-09-18
- **Parte revisado:** `docs/entregas/B-07.md` (versión de ejecución)
- **Commits:** `4410b57` (Commit A) · `2d86d9a` (Commit B)
- **Veredicto:** **APROBADO**

> La decisión previa de este bloque está en `docs/auditorias/B-07.md`. Este
> documento audita la ejecución de esa decisión.

## Verificación independiente

Reproduje la verificación en mi propio worktree, sin reusar el suyo:

```
$ git worktree add --detach <mi-worktree> HEAD
HEAD is now at 2d86d9a feat: integra el diagnóstico de Gemini y muestras de
                        documentos en el dashboard

$ PYTHONPATH=<mi-worktree>/src python -m pytest tests/ -q -m "not live"
....................................                                     [100%]
36 passed in 10.35s

$ PYTHONPATH=<mi-worktree>/src python -m pytest tests/ -m "live" --collect-only -q
no tests collected (36 deselected) in 1.03s
```

**Los dos objetivos del bloque se cumplieron y son verificables:**

1. **0 tests marcados `live`.** El marcador quedó sin uso porque ya no hace
   falta: los dos tests que lo requerían ahora corren aislados y en verde.
   Esto cierra el umbral que la propia D-08 se había fijado.
2. **36 passed contra el código de HEAD**, no contra el árbol de trabajo —
   el procedimiento que E-05 obligó a adoptar, aplicado correctamente.

Los tres cambios del fix que decidí están aplicados tal como se especificaron
(`self.session.post`, `gemini_api_key=None` explícito, `time.sleep` mockeado),
y Antigravity agregó por su cuenta dos refuerzos razonables que no había
pedido: `fetcher.gemini_api_key = None` redundante tras el constructor, y
actualizar los dos tests de Gemini para mockear `fetcher.session.post` en vez
de `requests.post` — consistente con el cambio de `_generate_gemini_content`.
Sin ese segundo ajuste esos tests habrían quedado mockeando un camino que el
código ya no usa, es decir, pasando sin probar nada. Buena captura.

## Sondeo

La prueba que más me interesaba —que Antigravity reporta como "test con
`requests.post` y `Session.post` envenenados pasando en 0.28s"— es el
control correcto: si ambos caminos de red están saboteados para lanzar
excepción y los tests igual pasan, entonces ninguno se invoca. Es
exactamente la forma de demostrar la ausencia de una llamada, que es más
difícil que demostrar su presencia.

`headless_fetcher.py` conserva `wait_until="networkidle"`, como decidí — no
se tocó de paso. La disciplina de alcance se sostuvo.

## Hallazgos

Ninguno.

## Anotaciones para AI_LOG.md

Cierra E-06. El diagnóstico de las 3 causas resultó exacto y el fix derivado
funcionó a la primera: la suite pasó de "65 minutos con 2 tests colgados y
consumo silencioso de cuota real de Gemini" a "36 tests en 10 segundos, 0
marcados live, 0 llamadas de red". Vale registrar la cifra de cierre porque
es el tipo de mejora que se olvida: el problema no era la lentitud, era que
nadie corría la suite completa **y** que cada corrida costaba cuota.
