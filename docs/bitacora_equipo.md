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
| B-14 | 🅰️ | Lote 1 (BCP, INE, ASFI, BCB) | 80/80 | Aprobado | Calibración inicial de primeros portales de Etapa C |
| B-15 | 🅰️ | Lote 2 (APS, ADA, DGAC, SEPREC) | 80/80 | Aprob. c/obs | Hallazgo de max_depth 0; consolidación de portales |
| B-16 | 🅰️ | Lote 3 (IBCE-CAO, CNDC, ASOFIN, ATT) | 80/90 | Aprob. c/obs | Subsanación de fetch_head resilience y calibración ASOFIN |
| B-17 | 🅰️ | Lote 4 (AE, ANAPO, ATC, MMYM) | 80/65 | Aprobado | Extracción masiva en ATC y MMYM |
| B-18 | 🅰️ | Lote 5 (AN, SENAMHI, CADEXCO, FAM) | 80/55 | Aprobado | SENAMHI supera 800 recursos |
| B-19 | 🅰️ | Lote 6 (IN, SNIS, CADECO, MIN_EDUCACION) | 80/65 | Aprobado | Cierre de lote de entidades públicas |
| B-20 | 🅰️ | Lote 7 (IBCH) + cierre Etapa C | 40/45 | Aprobado | Cierre de 25 portales externos en Track B |
| B-23 | 🅰️ | Calibración de fuentes problemáticas | 60/45 | Aprobado | Ajuste de patrones de descarte y selectores |
| B-24 | 🅰️ | Calibración volumétrica | 45/30 | Aprobado | Afinamiento de umbrales y consistencia |
| B-25 | 🅰️ | Re-verificación de Track A | 50/40 | Aprobado | Verificación de 64/67 URLs reproducibles |
| B-26 | 🅰️ | Reporte de cobertura reproducible | 45/35 | Aprobado | Script reporte_cobertura.py con salida dual y --strict |
| B-27 | 🅰️ | Cierre Fase 1: README y estado final | 40/35 | Aprob. c/obs | Cierre de 26 bloques; desacoplamiento D-04 verificado |
| B-28 | 🅰️ | Profundidad en 6 portales (Fase 2) | 90/45 | Aprob. c/obs | ADA (1.090) y DGAC (1.196) superan benchmark; ASFI sube a 582 (ZIPs en JS); fix extractor |
| B-29 | 🅰️ | Activar headless en BCP y BCRP | 50/40 | Aprob. c/obs | BCP pasa de 25 a 1.711 docs y BCRP de 0 a 223 docs; DBs acumulan corridas previas |
| B-31 | 🅰️ | Sitemaps en todos los portales | 60/45 | Aprob. c/obs | 15 de 28 portales con sitemap; delta +52 docs en muestra (ibce_cao +34, ae +18); max_sitemaps truncaba |
| B-32 | 🅰️ | Series históricas y Wayback (Fase 2) | 90/150 | **Devuelto** → Aprob. c/obs | 206 PDFs históricos reales (188 vivo + 18 Wayback). Fix transversal en allowed_extensions (fuga de .sha) y D-11 |
| B-30 | 🅰️ | Extracción de ZIP en prod (Fase 2) | 60/40 | Aprob. c/obs | 57 docs extraídos en ASFI y 1 en IN; hallazgo: 11 ZIPs de ASFI (79 MB, .xlsm/.ods) descargados sin extraer ni advertir |
| B-34 | 🅰️ | Onboarding Lote 1 (12 con doc) | 95/75 | Entregado (aud. agrupada) | Onboarding 12 fuentes con sitemap y wayback a profundidad 2; +2.060 docs reales (BBV 326, BM 106, ICCO 852, ITU 143, MDRyT 170, UNDATA 66, OTROS HIST 392, DST 5) |

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

**El estado PROCESADO_EXITOSAMENTE no significa descargado (B-33a).** Con
`content_hashing.enabled: false`, el pipeline finaliza con 201 filas en estado
exitoso pero con `file_size_bytes` y `content_sha256` en NULL, sin tocar la red
para transferir los archivos. La verificación real de inventario exige filtrar
por `file_size_bytes > 0`.

**El nombre del host dentro de las reglas de clasificación es un catch-all encubierto (B-33a).**
Incluir `"ice"` en `dataset_rules` matcheó `ice.santacruz.gob.bo`, capturando el
80% de los documentos en una sola categoría. Los patrones de dataset deben
apuntar a rutas temáticas y nombres de archivo, nunca a subcadenas del dominio.

**Imports con prefijo `src.` anulan la verificación de entorno limpio (B-33a).**
Usar `from src.crawler...` en vez de `from crawler...` resuelve por directorio
local en vez de `PYTHONPATH`, haciendo que un test pase en el árbol de trabajo
pero falle en un checkout aislado.

**`content_hashing: enabled: true` como default obligatorio (D-13 / B-34 / B-35).**
Para evitar filas en `inventory.db` sin bytes de descarga real, D-13 establece
que toda fuente nueva se configura con hashing activado. El onboarding del
Lote 1 (rebote) alcanzó 902 documentos con bytes verificados y SHA-256; y el
Lote 2 aportó 79 documentos con bytes reales (53 CEPROBOL, 26 BCB_BRASIL).

---

## Cómo evolucionó la cifra de cobertura

| Momento | Cifra | Qué cambió |
|---|---|---|
| Inicio | 59/63 · 93.7% | Dato heredado, sin re-verificar |
| Verificación en vivo | 58/62 · 93.5% | Duplicado fusionado, FUNDEMPRESA caída detectada |
| Tras B-08 | 62/68 · 91.2% | El universo creció: entraron 6 fuentes que faltaban |
| Tras redefinir la métrica | 64/68 · 94.1% | Dejar de contar como falla lo que funciona con navegador |
| Tras B-11 | **64/67 · 95.5%** | Registro basura depurado |
| Tras B-33a | **SICSANTACRUZ integrado** | Onboarding vía API Strapi: 201 docs con bytes y SHA verificados |
| Tras B-33b | **64/67 · 95.5%** | Paso 0: sin fuentes con formularios GET en catálogo; cerrado s/impl |
| Tras B-34 / B-35 (Rebote) | **49/67 con crawler_source** | Lote 1 re-descargado (902 docs c/bytes) + Lote 2 (79 docs c/bytes) · Aprobados (`ac89f06`) |
| Tras B-36 (Lote 3) | **53/67 con crawler_source** | Lote 3 onboarded: MHE (13 docs c/bytes), FIFA (62 docs c/bytes), Data.Gov (0, portal info), FEGASACRUZ (0, sitio en construcción) |
| Tras B-37 (Lote 4) | **57/67 con crawler_source** | Lote 4 onboarded: OBA (106 docs c/bytes), SABSA (24 docs c/bytes), OMC (10 docs c/bytes), NIH (5 docs c/bytes) |
| Tras B-38 (Lote 5) | **61/67 con crawler_source** | Lote 5 onboarded: VIPFE (667 docs c/bytes), SISPAM (10 docs c/bytes), TRANSTATS (10 docs c/bytes), SICOES (0, ASPX POST) |

**El sistema no empeoró en ningún momento.** Cada cambio vino de medir mejor.
Un porcentaje de cobertura no significa nada sin su denominador y su
definición — y uno que solo sube probablemente no se está midiendo bien.
