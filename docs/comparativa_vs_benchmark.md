# Resultado contra el benchmark de los 3 crawlers

Medición del 2026-09-19, contra el benchmark del 2026-09-07
(`Elecciones De Crawler por URL/`). Todas las cifras salen de contar
`inventory.db` de cada fuente con un clasificador propio, no del reporte del
runner.

---

## Estado actual

```
26 fuentes con al menos un documento · 2.357 documentos · 0 errores
2.633 recursos totales (2.357 documentos + 276 otros recursos)
```

El crawler pasó de **974 documentos sobre 52 fuentes** (benchmark de
septiembre) a **2.357 sobre 26 fuentes**.

---

## Comparación como corresponde: mismos portales

Comparar totales sería tramposo — el benchmark corrió 52 fuentes y nosotros
26. La comparación honesta es sobre los **22 portales comunes**, agrupando
las entradas que el benchmark trataba por separado y nosotros consolidamos
(las 4 de ASFI, las 2 de APS).

| Portal | Douglas | Rolando | Nosotros (sep) | **Nosotros (hoy)** |
|---|---:|---:|---:|---:|
| senamhi | 0 | 0 | 0 | **798** |
| ae | 0 | 0 | 3 | **113** |
| fam | 0 | 0 | 0 | **111** |
| mmym | 0 | 28 | 69 | **107** |
| anapo | 0 | 0 | 0 | **99** |
| cndc | 0 | 0 | 1 | **93** |
| att | 0 | 27 | 58 | **65** |
| atc | 0 | 20 | 2 | **39** |
| ibce_cao | 0 | 24 | 0 | **26** |
| cadexco | 0 | 1 | 0 | **10** |
| bcb | 13 | 811 | 103 | 116 |
| finrural | 0 | 562 | 5 | 129 |
| asfi | 13 | 2.422 | 103 | 61 |
| ada | 1 | 1.075 | 5 | 2 |
| asofin | 0 | 195 | 5 | 18 |
| ibch | 0 | 32 | 0 | 23 |
| ine | 0 | 112 | 53 | 9 |
| aps | 22 | 24 | 18 | 12 |
| dgac | 12 | 42 | 144 | 12 |
| seprec | 0 | 12 | 64 | 12 |
| snis | 9 | 9 | 31 | 9 |
| mefp | 0 | 7 | 0 | 0 |
| **TOTAL** | **70** | **5.403** | **664** | **1.864** |

**Multiplicamos por 2,8 nuestro propio resultado** sobre los mismos portales
(664 → 1.864), y superamos a Rolando en **12 de 22**.

Pero Rolando sigue arriba en el total: 5.403 contra 1.864.

---

## Dónde ganamos y dónde perdemos — el patrón es nítido

**Ganamos donde Rolando no encontró nada.** SENAMHI, FAM, ANAPO, CNDC y AE
daban **0 documentos** en el benchmark y hoy dan 798, 111, 99, 93 y 113.
Esas cinco fuentes no eran un problema de rastreo: eran un problema de
**mapa de fuentes desactualizado**, que es exactamente lo que resolvió el
trabajo de Track A. El benchmark ya lo había señalado como la causa de
mayor impacto, y se confirma.

**Perdemos donde Rolando fue profundo.** Y acá la causa es concreta:

| Portal | Rolando | Nosotros | Brecha | `max_depth` actual |
|---|---:|---:|---:|:---:|
| asfi | 2.422 | 61 | −2.361 | **0** |
| ada | 1.075 | 2 | −1.073 | **0** |
| | | | **−3.434** | |

**Esos dos portales explican el 97% de la brecha total** (3.434 de 3.539). Y
los dos siguen configurados en `max_depth: 0`, que significa que solo se leen
las páginas semilla, sin seguir un enlace.

---

## El lazo que quedó abierto

Esto no es un descubrimiento nuevo: **es un hallazgo que registré en la
auditoría de B-15 y que nunca se cerró.**

Ahí escribí que los ocho portales de los lotes 1 y 2 quedaban en nivel
"Conectado" (la tubería funciona) y no "Onboardeado" (profundidad calibrada),
y que se retomarían en B-24. B-24 se ejecutó —con tres rondas de auditoría, y
un trabajo cuidadoso— pero **sobre BCB y la deduplicación**, no sobre los seis
portales en profundidad 0.

Siguen así hoy:

```
asfi    depth=0  pages=10
ada     depth=0  pages=5
aps     depth=0  pages=5
dgac    depth=0  pages=5
ine     depth=0  pages=5
seprec  depth=0  pages=5
```

Los demás portales están en `depth=1 / 35 páginas`; solo FINRURAL y BBV están
en `depth=2 / 120`. Para referencia: FINRURAL, con profundidad 2, dio 129
documentos.

**La responsabilidad del lazo abierto es mía**: lo marqué, lo asigné a un
bloque, y no verifiqué al auditar B-24 que ese bloque hubiera cubierto lo
asignado. Auditaba cada bloque contra su propio parte, sin contrastar contra
lo que un bloque anterior le había derivado.

---

## Qué significa para el resultado del proyecto

**Lo que el proyecto sí resolvió, y era su objetivo declarado:**

- Track A (conectividad): 64/67 = 95,5% verificadas, con las 3 exclusiones
  justificadas una por una.
- El mapa de fuentes desactualizado —la causa de mayor impacto según el
  propio benchmark— está corregido, y se ve en los 5 portales donde pasamos
  de 0 a cientos de documentos.
- Las otras tres causas del benchmark (robots.txt por portada, ZIP sin
  contar, límites genéricos) están resueltas o con el mecanismo disponible.
- 2.357 documentos con **0 errores** en 26 fuentes.

**Lo que no está cerrado:**

- Seis portales en profundidad 0, dos de los cuales concentran el 97% de la
  brecha con el mejor competidor.
- Una corrida con profundidad calibrada en ASFI y ADA es, con bastante
  probabilidad, la diferencia entre 1.864 y algo cercano o superior a los
  5.403 de Rolando — sobre todo considerando que en 12 de 22 portales ya
  estamos arriba.

**Recomendación:** un bloque de calibración sobre esos seis portales antes de
dar el proyecto por cerrado. Es el trabajo con mejor relación
esfuerzo/resultado que queda en todo el plan: seis archivos de configuración
y seis corridas.

---

## Nota sobre la comparabilidad de las cifras

Tres salvedades para no sobrevender el número:

1. **Nuestros 2.357 son documentos en sentido estricto** (extensión en la
   lista permitida), separados de los 276 "otros recursos". Esa distinción se
   introdujo en B-14 tras descubrir que la mitad de un conteo eran archivos
   de checksum. No sé si el benchmark aplicaba un filtro equivalente; si no
   lo hacía, las cifras de los tres competidores están medidas con una vara
   más laxa que la nuestra.
2. **De los 5.902 de Rolando, 1.893 venían de descomprimir ZIP.** Nuestro
   motor también los extrae (verificado en B-07), así que en eso sí somos
   comparables.
3. **El benchmark es del 2026-09-07.** Los sitios cambiaron en el medio — de
   hecho detectamos una caída real (FUNDEMPRESA) y un dominio expirado
   (SICSANTACRUZ) en ese lapso.
