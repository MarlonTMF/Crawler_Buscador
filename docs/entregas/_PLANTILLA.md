# B-NN · <título del bloque, igual que en docs/plan_bloques.md>

- **Ejecutado por:** Antigravity
- **Fecha:** YYYY-MM-DD
- **Estimado:** NN min · **Real:** NN min · **Desvío:** +NN%
- **Commit:** `abc1234` — primera línea del mensaje

## Qué se hizo

Dos o tres frases. Qué cambió en el repositorio, en términos de efecto, no de
archivos tocados.

## Criterio de aceptación — evidencia

> Copiar acá el criterio textual del bloque, tal como está en
> `docs/plan_bloques.md`.

Y debajo, la **salida real** del comando que lo verifica:

```
$ comando exacto que se corrió
salida real, pegada sin editar
```

Si el criterio pedía ver algo fallar (por ejemplo, una prueba de regresión),
van las dos salidas: la de la corrida en rojo y la de la corrida en verde.

```
$ comando con el fix revertido
... falló como se esperaba

$ comando con el fix aplicado
... pasó
```

## Desviaciones del plan

Qué se hizo distinto de lo escrito, y por qué. **"Ninguna" es una respuesta
válida y frecuente** — no hay que inventar desviaciones para llenar la
sección.

## Dudas / escalamientos

Lo que no se decidió porque no correspondía decidirlo (ver "Condiciones de
parada" en `docs/protocolo_equipo.md`). Vacío si no hubo.

## Estado

`LISTO PARA AUDITORÍA` | `BLOQUEADO: <razón concreta>`
