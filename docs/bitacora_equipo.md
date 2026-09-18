# Bitácora del equipo — Antigravity + Claude

Registro de qué hizo cada uno, bloque por bloque, con veredicto y hallazgos.
Versión navegable publicada en `https://claude.ai/artifact/XUmPif2k5W9nTGYtaPwJMH`;
este archivo es la copia versionada, que es la que sobrevive.

**Estado al 2026-09-18:** 13 de 28 bloques cerrados · 24 commits ·
2 devoluciones · Track A cerrado en 64/67 (95.5%) · Etapa C en marcha.

---

## Reparto

| | Antigravity | Claude |
|---|---|---|
| Rol | Ejecuta los bloques con criterio de aceptación escrito | Planifica, decide lo ambiguo, audita |
| Entrega | `docs/entregas/B-NN.md` con evidencia pegada | `docs/auditorias/B-NN.md` con veredicto |
| Volumen | 13 bloques · ~3h 20m reales | 8 commits propios · 13 actas |

---

## Bloques cerrados

| # | Quién | Bloque | Est/Real | Veredicto | Hallazgo |
|---|---|---|---|---|---|
| B-01 | 🅰️ | Higiene de `.gitignore` | 20/11 | Aprob. c/obs | `.env.example` quedó excluido por una regla demasiado amplia |
| B-02 | 🅰️ | Fix de `mailto:`/`tel:` | 15/5 | Aprobado | El fix generaliza a 7 casos no probados; una capa sin cobertura (sin acción) |
| B-03 | 🅰️ | Separación de tests `live` | 15/21 | **Devuelto** → Aprob. | HEAD roto + descubrimiento de que toda verificación medía el árbol de trabajo |
| B-04 | 🅰️ | Resoluciones de URL | 20/6 | Aprobado | Detectó 4 entradas que violaban D-01, incluida una que se contradecía a sí misma |
| B-05 | 🅰️ | Agentes y hook | 20/6 | Aprob. c/obs | Verificó el hook por el mecanismo real; falta el caso de fallo |
| B-06 | 🅰️ | Decisiones y planes | 15/5 | Aprob. c/obs | Escribió 5 umbrales faltantes — se ajustó el protocolo |
| B-07 | 🅰️→🅲 | Diff del fetcher y dashboard | 45/20 | Aprobado | **La suite gastaba cuota real de Gemini sin que apareciera en ningún log** |
| B-07b | 🅰️ | Módulos sin trackear | 40/20 | **Devuelto** → Aprob. | La salida de pytest pegada no era de una corrida real |
| B-08 | 🅰️→🅲 | Brecha de alcance | 45/25 | Aprobado | La brecha era 15, no 14; seis "huecos" eran variantes de nombre |
| B-09 | 🅰️→🅲 | FMI | 30/20 | Aprobado | Un atajo que habría subido la cobertura sobre una fuente inservible |
| B-10 | 🅰️→🅲 | SICSANTACRUZ | 40/35 | Aprobado | Aplicó por su cuenta la lección de B-09 (verificar descarga real) |
| B-11 | 🅰️→🅲 | Cierre de Track A | 25/15 | Aprob. c/obs | Un "100%" que no era cobertura; una hipótesis convertida en hecho |
| B-12 | 🅰️ | Generador de YAML | 75/35 | Aprob. c/obs | Tres banderas del YAML que el motor no lee — **error mío** |
| B-13 | 🅰️ | Runner + headless | —/— | Aprob. c/obs | 127 de 257 "recursos" son checksums de 89 bytes, no documentos |

Trabajo propio de Claude, fuera de bloque: verificación en vivo del catálogo
completo (durante una reunión con una hora de plazo) y el descubrimiento de
que el catálogo curado no estaba versionado (D-09).

---

## Los hallazgos que más valieron

**Ninguna verificación medía lo que decía medir (B-03).** El paquete estaba
instalado en modo editable apuntando al repositorio, así que toda corrida de
pytest importaba el árbol de trabajo en vez de lo commiteado. Los "52 passed"
de tres bloques eran ciertos sobre el disco y no decían nada sobre git. Mi
propia primera verificación del problema también fue inválida por la misma
razón.

**La suite gastaba cuota real de la API de Gemini (B-07).** Dos tests
escapaban su propio mock y salían a la red de verdad. En una máquina con
clave configurada, cada corrida completa consumía cuota sin aparecer en
ningún registro — la misma cuota que el proyecto ya había agotado dos veces
sin saber por qué.

**Un atajo que habría inflado la cobertura (B-09).** Se encontró un portal
del FMI que responde 200 y lista 40 documentos de Bolivia. Al probar la
descarga, devuelven cero bytes. Mapear ahí habría subido la cifra a 95.6%
sobre una fuente de la que no sale un solo archivo.

**Un número correcto que cuenta la cosa equivocada (B-13).** De 257 recursos
extraídos, 127 son archivos de checksum de 89 bytes. Nada es falso —los 257
existen y se descargaron— y aun así la cifra no significa lo que parece.

**Una cifra heredada que nadie había verificado (B-08).** El "universo de 76
fuentes" venía de una resta de una sesión anterior. La brecha real era otra, y
seis de los supuestos huecos eran la misma fuente escrita con otro nombre —
una diferencia de un solo acento.

---

## Cómo evolucionó la cifra de cobertura

| Momento | Cifra | Qué cambió |
|---|---|---|
| Inicio | 59/63 · 93.7% | Dato heredado, sin re-verificar |
| Verificación en vivo | 58/62 · 93.5% | Duplicado fusionado, FUNDEMPRESA caída detectada |
| Tras B-08 | 62/68 · 91.2% | El universo creció: entraron 6 fuentes que faltaban |
| Tras redefinir la métrica | 64/68 · 94.1% | Dejar de contar como falla lo que funciona con navegador |
| Tras B-11 | **64/67 · 95.5%** | Registro basura depurado |

**El sistema no empeoró en ningún momento.** Cada cambio vino de medir mejor.
Un porcentaje de cobertura no significa nada sin su denominador y su
definición — y uno que solo sube probablemente no se está midiendo bien.
