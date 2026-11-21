# CLAUDE.md — Hackathon 3B · Análisis inteligente de expedientes inmobiliarios

Contexto del proyecto para quien (persona o agente) retome el trabajo. Mantenerlo al día
cuando se agregue una fase o cambie una decisión.

## 1. El reto

Sistema multiagente que revisa el expediente legal/administrativo de un inmueble para
**prefactibilidad de expansión comercial** (3B), detecta lo que falta o no coincide y emite
una recomendación **semáforo** sustentada en evidencia (documento, página, fragmento, coordenadas).

Documentos del expediente (uno de cada tipo, RF-01):

| Tipo | Carpeta de pruebas | Tabla BD | Clave en el filtro |
|---|---|---|---|
| Escrituras | `Escritura/` | `escrituras` | `escritura` |
| Predial | `Predial/` | `predial` | `predial` |
| Alineamiento y Número Oficial | `Alineamiento_y_Numero_Oficial/` | `aliniamiento` (sic) | `alineamiento` |
| Uso de Suelo | `Uso_de_suelo/` | `suelo` | `uso_suelo` |

> Ojo: el front (`src/lib/seed.js`) maneja **5** documentos (separa `numero_oficial` de
> `alineamiento`); los requerimientos y la BD manejan **4**. Pendiente de alinear con el equipo.

Fuentes de requerimientos (PDFs del 21-nov-2026, no están en el repo):
*Requerimientos_Analisis_Expedientes_Inmobiliarios.pdf* (v0.1), *Análisis inteligente de
expedientes inmobiliarios.pdf* (presentación) y *Revisión de expediente.pdf* (prototipo del dictamen).
Resumen de lo que importa:

- **RF-01** completitud: 4 de 4 tipos → "En revisión"; si falta alguno → "No validado" y se detiene.
- **RF-02** clasificar tipo + confianza; baja confianza → revisión humana; dividir archivos combinados.
- **RF-03** extraer campos con valor, valor normalizado, confianza y evidencia.
- **RF-04/05** validación cruzada VC-01…VC-07 (dirección, titular, superficie ±1 %, número oficial,
  clave predial, "otro inmueble", faltantes).
- **RF-06** riesgos RG-01…RG-05 (vigencia vencida, uso incompatible, restricciones, adeudo predial, autoridad).
- **RF-08** semáforo: verde (todo cumple), amarillo (revisión / severidad media-alta), rojo (crítico), gris (no validado).
- **RNF-01** precisión ≥98 % clasificación, ≥95 % extracción. **RNF-02** trazabilidad: SHA-256, regla y versión.
- Decisión clave de arquitectura: **"el LLM lee, el código decide"**. Comparación y semáforo son reglas deterministas versionadas.

## 2. Estrategia de costo (acordada)

Cascada: primero pasos gratuitos y locales, el LLM solo cuando haga falta.

| Etapa | Opción barata (local, CPU) | Respaldo |
|---|---|---|
| Texto / OCR | PyMuPDF (texto nativo) + RapidOCR (PaddleOCR en ONNX, modelo latino) | OCR en la nube solo si la confianza local es baja |
| Tipo de documento | Frases clave/regex (+ TF-IDF cuando haya más datos) | Embeddings + FAISS |
| Campos | Regex y plantillas (formatos fijos) | LLM barato con salida estructurada (escrituras) |
| Validez | Pydantic + reglas + (Isolation Forest a futuro) | Revisión humana |

## 3. Estructura del repo

```
src/, index.html, vite.config.js   Front React + Vite (Sabrina). Proxy /api -> http://127.0.0.1:5000
server/app.py                      Backend Flask: /api/login (tabla usuarios) + registra el pipeline
procesamiento/                     Pipeline de documentos (Wendy)
  pipeline.py                        orden de etapas y contrato Documento / ResultadoEtapa
  etapa_calidad.py                   Fase 1 (envuelve filtro_calidad/)
  etapa_extraccion.py                Fase 2 — adaptador sobre ocr_pipeline (campos con evidencia)
  etapa_verificacion.py              validación cruzada VC-xx del expediente -> observaciones
  observaciones.py / dictamen.py     observaciones uniformes + semáforo determinista + LLM
  fuentes.py                         obtiene el archivo desde la BD (bytea, URL o ruta)
  api.py                             endpoints /api/documentos/... y /api/operaciones/...
  sql/propuesta.sql                  columna `archivo` + tabla filtro_resultados (NO ejecutado)
filtro_calidad/                    Fase 1 como librería + CLI + app local de pruebas
  filtro.py                          motor del filtro (CLI por lotes)
  config.py                          umbrales, frases clave, negativos, mensajes
  app.py                             app local para subir archivos y probar (puerto 8000)
ocr_pipeline/                      Fase 2 + validación cruzada (Yax). Ver ocr_pipeline/README.md
  servicio.py                        API: procesar_documento() / verificar_expediente()
  fields.py, matching.py             extracción (regex + reglas) y comparación (rapidfuzz)
  schemas.py                         contrato Pydantic (Documento, Campo, Expediente; VersionEsquema)
  requirements-servidor.txt          deps para el backend (sin Paddle); las incluye server/requirements.txt
api.py, demo/                      modo independiente: FastAPI (/documento, /expediente, /docs, /demo)
run_ocr.py, export_json.py         modo independiente: batch sobre las 4 carpetas -> output/ (ignorado)
tests/                             pytest (ocr_pipeline + integración con procesamiento/), sin OCR ni BD
Escritura/ Predial/ Uso_de_suelo/ Alineamiento_y_Numero_Oficial/   documentos de prueba del reto
public/docs/<tipo>/caso-00N.pdf    PDFs que muestra hoy el front (8 casos)
```

Ramas: `main` (integración), `Wendy` (pipeline/filtro), `SabrinaMichaus` (front),
`SergioCalderas` (front + BD), `YaxLira` (Fase 2 de extracción + validación cruzada: `ocr_pipeline/`,
`procesamiento/etapa_extraccion.py`, `procesamiento/etapa_verificacion.py`; PR hacia `main`),
`AlbertoFlores` (hoy apunta al mismo commit que una versión anterior de `YaxLira`; no tiene trabajo propio).

## 4. Base de datos (Supabase Postgres, proyecto "Hackaton")

Detalle en `README.md`. Conexión en `.env` local (no se sube): `DATABASE_URL`, `SUPABASE_URL`, …
Tablas `escrituras`, `predial`, `suelo`, `aliniamiento` (mismas columnas: `direccion_memoria`,
`direccion_real`, `propietario`, `numero_oficial`, `superficie`, `estado` 0/1, `archivo`).
`operacion_realizada` junta un documento de cada tabla (+ lat/long y semáforo 1 rojo, 2 amarillo, 3 verde).

**Los documentos NO se suben desde el front: el pipeline los toma de la BD.** Esquema actual
(el equipo lo reorganizó el 21-nov-2026):
- Los archivos viven en **Supabase Storage**, bucket público `documentos`, con carpetas
  `escrituras/`, `predial/`, `uso_de_suelo/`, `alineamiento/` (los 60 PDFs/JPG del reto).
- **`direccion_memoria` guarda la ruta del objeto en el bucket** (p. ej. `predial/02 Predial.pdf`).
  Los campos de datos (`direccion_real`, `propietario`, `numero_oficial`, `superficie`, `estado`)
  aceptan NULL: los llenará la Fase 2.
- `operacion_realizada` está vacía por ahora; mientras tanto el front arma el expediente a mano
  (pestaña "Filtro de documentos" → `POST /api/dictamen`).

`procesamiento/fuentes.py` toma el archivo de la primera columna no vacía de `FILTRO_COLUMNA_ARCHIVO`
(por omisión `archivo,direccion_memoria`). Acepta `bytea`, URL http(s), ruta relativa al repo o a
`public/`, o **ruta dentro del bucket** (descarga de `SUPABASE_URL/storage/v1/object/public/<bucket>/<ruta>`).
Un hash bcrypt en la columna se trata como "sin archivo".

Variables del servidor para el pipeline:

| Variable | Uso |
|---|---|
| `DATABASE_URL` | conexión Postgres (ya la usa el login). En redes sin IPv6 usar el **Session pooler** (`aws-1-us-east-1.pooler.supabase.com`), no `db.<ref>.supabase.co` |
| `SUPABASE_URL` | para descargar del bucket |
| `FILTRO_COLUMNA_ARCHIVO` | columnas con el archivo, en orden (default `archivo,direccion_memoria`) |
| `FILTRO_BUCKET` | bucket de Storage (default `documentos`) |
| `FILTRO_GUARDAR_RESULTADOS=1` | inserta cada resultado en `filtro_resultados` (bitácora; la API usa el más reciente) |
| `DICTAMEN_LLM=1` | activa el LLM en el dictamen (sin esto: plantilla determinista, costo cero) |
| `DICTAMEN_MODELO` / `DICTAMEN_EFFORT` | default `claude-opus-5-5` / `low` |
| `ANTHROPIC_API_KEY` | credencial del LLM (o perfil de `ant auth login`) |

## 5. API del pipeline (registrada en `server/app.py`)

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/procesamiento/salud` | etapas activas y versión de reglas |
| GET | `/api/operaciones` | todas las operaciones con el último resultado guardado por documento (sin OCR, ~2 s) |
| GET | `/api/operaciones/<id>` (y GET `…/verificar`) | una operación, último resultado guardado; GET nunca vuelve a correr el filtro |
| GET | `/api/documentos` | todos los documentos con último resultado y **observaciones** (sin OCR) |
| POST | `/api/documentos/<tabla>/<id>/verificar` | corre el pipeline sobre un documento de la BD |
| GET | `/api/operaciones/<id>/observaciones` | observaciones estructuradas + semáforo determinista |
| POST | `/api/operaciones/<id>/dictamen` | manda las observaciones a la última etapa (LLM o plantilla) |
| POST | `/api/dictamen` | igual, con documentos elegidos `{escrituras, predial, suelo, aliniamiento}: id` |
| POST | `/api/operaciones/<id>/verificar` | los 4 documentos de `operacion_realizada` + completitud RF-01 (`EN_REVISION` / `NO_VALIDADO`) |
| POST | `/api/documentos/verificar-archivo` | multipart `archivo` (+ `tipo`), solo para pruebas |
| GET | `/api/texto?ruta=/docs/<tipo>/caso-00N.pdf` | texto extraído por página de un PDF de `public/` (vista del caso). `?tipo=` para resaltar campos, `?solo_cache=1` no corre OCR (responde `SIN_EXTRAER`) |
| GET | `/api/documentos/<tabla>/<id>/texto` | igual, para un documento de la BD |

`?hasta=calidad` corre solo la Fase 1 (sin él corren Fase 1 + Fase 2; el botón *Verificar* de
`Filtro.jsx` ya corre ambas). Respuesta: `{nombre, tabla, id, tipo_declarado, etapas, version_reglas, calidad: {...}, extraccion: {...}}`.
Campos clave de `extraccion`: `estado` (OK | SIN_CAMPOS | ERROR), `campos {campo: {valor, valor_normalizado,
confianza, evidencia {pagina, fragmento, bbox, regla}}}`, `documento` (Documento compacto de `ocr_pipeline`,
lo usa la validación cruzada), `calidad_texto`, `version_esquema`.
Campos clave de `calidad`: `estado`, `motivo`, `mensaje` (texto para el usuario), `observaciones`,
`tipo_detectado`, `legibilidad`, `confianza_ocr`, `paginas_revisadas[]`, `sha256`.
Tablas válidas: `escrituras | predial | suelo | aliniamiento` (lista blanca, sin SQL dinámico).

### Front ↔ pipeline

- **Pestaña "Filtro de documentos"** (`src/views/Filtro.jsx`, gestor y admin): lista los documentos de la
  BD por tipo con su estado, mensaje y **observaciones** (severidad, código, regla), botón *Verificar* por
  documento y *Usar en dictamen* para armar el expediente; **Generar dictamen** muestra semáforo,
  justificación con ids citados, acciones sugeridas, quién la redactó (LLM o plantilla) y el JSON enviado al LLM.
- `src/lib/filtro.jsx` (`FiltroProvider`, `useFiltro`): resultados por operación para `CaseDetail.jsx`
  (tarjeta "Filtro de calidad", observaciones por documento) y `DocModal.jsx`. Caso `cN` ↔ operación `N`;
  hoy no hay operaciones, la tarjeta remite a la pestaña nueva.
- Tipos front → tablas: `escrituras→escrituras`, `predial→predial`, `uso_suelo→suelo`,
  `alineamiento→aliniamiento`, `numero_oficial→aliniamiento` (la BD los junta).
- El resto del front (revisión del gestor, semáforos de validación, historial) sigue usando
  `src/lib/seed.js` + localStorage. **Las "Validaciones" del `DocModal` son datos demo de `seed.js`.**
- **"Texto extraído del documento"** (`src/components/TextoExtraido.jsx`, en `DocModal.jsx` debajo de
  Aceptar/Denegar): consulta `GET /api/texto?ruta=<d.pdf>&tipo=<d.type>&solo_cache=1` (instantáneo); si no
  hay texto, el botón *Verificar* lo extrae con OCR. Muestra motor, calidad y páginas, selector de página,
  extracto de 1,800 caracteres con *Ver todo*, valores de los campos resaltados y *Copiar texto*.
  Como hoy no hay operaciones, se enlaza por el PDF que muestra el caso (los 39 de `public/docs/` son copias
  idénticas de documentos del reto, así que comparten caché con los de la BD por SHA-256).

### Observaciones y dictamen (última etapa)

- `procesamiento/observaciones.py`: convierte resultados en observaciones uniformes
  `{id, tabla, documento, etapa, codigo, regla, severidad, bloquea, texto}`. Severidad CRITICA/ALTA/MEDIA/BAJA;
  códigos `FALTA-ARCHIVO`, `CAL-RECHAZO`, `CAL-COMBINADO`, `CAL-NO-COMPROBANTE`, `CAL-TIPO-DUDOSO`,
  `RIESGO-VIGENCIA` (RG-01), `RIESGO-ADEUDO`/`RIESGO-PERIODO` (RG-04), `CAL-IMAGEN`, `CAL-LECTURA`…
  La validación cruzada agrega sus hallazgos (`VC-*`, etapa `validacion_cruzada`, tabla `expediente`,
  con `evidencia[]` de cada documento) en `de_operacion()`; los riesgos (RG-xx) deben seguir la misma forma.
- `procesamiento/dictamen.py`: **el código decide el semáforo** (GRIS faltan/rechazados, ROJO crítico,
  AMARILLO media/alta, VERDE sin observaciones; si hubo validación cruzada, el VERDE lo dice y
  `etapas_completadas` incluye `extraccion` y `validacion_cruzada`) y **el LLM solo redacta** con salida JSON por esquema
  (`resumen`, `puntos[{texto, observaciones_citadas}]`, `acciones_sugeridas`). Citas a ids inexistentes se
  eliminan y el punto queda marcado `sin_evidencia`. Llamada: `client.beta.messages.create`,
  `claude-opus-5-5`, `effort=low`, `fallbacks="default"` (beta `server-side-fallback-2026-07-01`).
  Ante cualquier fallo (sin credencial, rechazo, límite, red) cae a la plantilla con una nota.
- Probado sin gastar: la petición se interceptó con un transporte simulado (`httpx2.MockTransport`).
  Falta probar contra la API real con una credencial.
- Windows + Python de la Store: `pip install anthropic` falla por rutas >260 caracteres. Habilitar
  rutas largas (`LongPathsEnabled`) o usar un venv en una ruta corta.

## 6. Fase 1 — Filtro de calidad (HECHO)

Decide antes de extraer si el archivo sirve. Estados:

- `APROBADO` → pasa a extracción.
- `REVISION_MANUAL` → dudoso (tipo ambiguo, archivo con varios documentos, formato de pago en lugar de comprobante, lectura baja).
- `VOLVER_A_SUBIR` → motivos: `formato_no_soportado`, `archivo_invalido`, `archivo_grande`, `en_blanco`,
  `ilegible`, `parcialmente_ilegible`, `otro_documento` (CFE, agua, INE, banco, SAT, acta, teléfono, arrendamiento),
  `tipo_no_reconocido`, `tipo_incorrecto` (p. ej. predial cargado como uso de suelo).

Cómo decide (en cascada): formato → texto nativo u OCR (máx. 5 páginas: 3 primeras, mitad, última;
rota 90/270 si casi no lee) → legibilidad por página (caracteres leídos con conf ≥0.80 y confianza
media; nitidez/dpi/foto solo son observaciones) → tipo por frases clave (encabezado ×6, fuertes ×3,
débiles ×1) vs. negativos → tipo por página para detectar archivos combinados → observaciones de
vigencia y adeudos (no bloquean: los evalúa RG-01/RG-04 después).

Calibración con los 63 documentos del reto: **54 aprobados, 6 revisión, 3 volver a subir**;
6/6 negativos sintéticos rechazados con el motivo correcto. Lecciones:

- Casi todos los PDFs son escaneos (sin texto nativo): el OCR es obligatorio.
- La varianza del Laplaciano sola **no** sirve para decidir legibilidad (fotos legibles salen "borrosas");
  lo que decide es cuánto texto con confianza logra leer el OCR.
- "predial", "cuenta predial" y "clave catastral" salen en todos los tipos → solo cuentan como débiles.
- Frases legales genéricas ("sin efectos", "no surte efectos") dan falsos positivos; no usarlas como señal.
- Alineamiento y Uso de Suelo comparten formato municipal: TF-IDF los confunde; solo desempata.
- Archivos reales combinados: escritura + boleta predial, uso de suelo + predial, título agrario (RAN) + CFDI.
- Convención de los documentos sintéticos del reto: `...` = borroso (ilegible), `!!` = foto / contenido con
  riesgos (vigencia vencida, adeudos, afectaciones), `v` = otra variante válida. Las variantes `!!` y
  algunas `...` (Alineamiento) son legibles: sus problemas son de contenido y los detecta la validación cruzada.

Límites: no prueba autenticidad (requiere QR/folio y consulta a la autoridad); no divide archivos combinados.

## 7. Fase 2 — Extracción y validación cruzada (HECHO)

Implementadas como **adaptadores delgados** sobre `ocr_pipeline/` (toda la lógica vive ahí; ver
`ocr_pipeline/README.md`). Diseño "el código decide": reglas deterministas, sin LLM.

**Extracción** (`procesamiento/etapa_extraccion.py`, etapa `extraccion` en `ETAPAS`). Solo recibe documentos
`APROBADO` (el pipeline se detiene antes si no). Bajo `CANDADO_OCR` llama a
`ocr_pipeline.servicio.procesar_documento(ruta, tipo, nombre, modo="compacto")`:
- OCR propio con **Tesseract `spa`** (el motor híbrido usa Paddle como respaldo solo si está instalado; en el
  servidor no se instala, ver §8). Texto nativo del PDF si lo hay. ~3–20 s por documento además de la Fase 1.
- Campos con evidencia: ClaveCatastral, CuentaPredial, Propietario, Vendedor, Direccion (Calle, NumeroOficial,
  Lote, Manzana, Colonia, Municipio, Estado, CodigoPostal), SuperficieTerreno/Construccion, NumeroEscritura,
  Volumen, Folio, FechaDocumento (ISO), EjercicioFiscal. `bbox` aún es `null` (evidencia = página + fragmento + regla).
- El resultado va en `detalle->'extraccion'` de `filtro_resultados` (no hay columnas nuevas). **No se escriben**
  las columnas `direccion_real`, `propietario`, `numero_oficial`, `superficie` (decisión pendiente del equipo).
- Pendiente: reutilizar el texto de RapidOCR de la Fase 1 (`leer_paginas`) para evitar el doble OCR; las
  reglas están calibradas con Tesseract y habría que re-validarlas.

**Texto extraído** (`procesamiento/texto.py`): el texto completo por página **no va a la BD**. Vive en una
caché en disco por SHA-256 (`procesamiento/_trabajo/.cache_texto/`, ignorada por git) que llenan la Fase 2
al extraer, los endpoints `/texto` bajo demanda, o el precalentado antes de una demo:
`python -m procesamiento.texto --precalentar` (los 39 PDFs de `public/docs/`; los documentos largos tardan
~2 min, p. ej. la escritura de Tepeji, 25 págs: 116 s). Los campos a resaltar se recalculan del texto en
caché en cada consulta (sin OCR).

**Validación cruzada** (`procesamiento/etapa_verificacion.py`): es por expediente, no por documento. La llama
`observaciones.de_operacion()` con los `documento` guardados de los APROBADOS y usa
`ocr_pipeline.servicio.verificar_expediente` (rapidfuzz, tolera errores de OCR). Regla de severidad:

| Hallazgo | Regla | Severidad | Semáforo |
|---|---|---|---|
| ClaveCatastral / CuentaPredial distinta | VC-05 | CRITICA | ROJO |
| Propietario distinto | VC-02 | CRITICA | ROJO |
| SuperficieTerreno distinta | VC-03 | ALTA | AMARILLO |
| NumeroOficial distinto | VC-04 | ALTA | AMARILLO |
| Calle, colonia, municipio, estado, CP, lote, manzana | VC-01 | MEDIA | AMARILLO |
| Puntaje < 0.55 o "posible documento de otro inmueble" | VC-06 | ALTA | AMARILLO |
| Dos prediales del mismo ejercicio | VC-07 | MEDIA | AMARILLO |
| APROBADO sin extracción (se verificó con `?hasta=calidad`) | SIN-EXTRAER | MEDIA | AMARILLO |

Probado sin BD (`procesar_bytes` → observaciones → dictamen): expediente sintético base → validación
cruzada 1.0 sin discrepancias (el semáforo queda AMARILLO solo por RG-01: la licencia de uso de suelo
sintética venció el 03-mar-2026); expediente `v` → ROJO con VC-05, VC-02, VC-04 y VC-03.

Después: normalización fina → riesgos RG → bbox en la evidencia → dictamen.

## 8. Cómo correr

```bash
# Front
npm install && npm run dev                          # https://localhost:5173

# Backend (login + pipeline)
pip install -r server/requirements.txt             # incluye filtro_calidad/ y ocr_pipeline/requirements-servidor.txt
python server/app.py                               # http://127.0.0.1:5000
# La Fase 2 necesita Tesseract + tessdata/ (una vez por máquina; ver ocr_pipeline/README.md):
#   winget install UB-Mannheim.TesseractOCR
#   mkdir tessdata && curl -L -o tessdata/spa.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
#   copiar eng.traineddata y osd.traineddata de "C:\Program Files\Tesseract-OCR\tessdata\" a tessdata/
# ⚠ No instales requirements.txt (raíz, con Paddle) en el mismo venv del servidor: Paddle trae
#   opencv-contrib-python y el filtro opencv-python-headless; ambos instalan cv2 y se pisan.

# Pruebas (sin OCR ni BD)
python -m pytest

# Antes de una demo: texto de los 39 PDFs de los casos en caché (con el venv del servidor)
python -m procesamiento.texto --precalentar

# Filtro por lotes sobre una carpeta (subcarpeta = tipo declarado)
python filtro_calidad/filtro.py <carpeta> --salida <carpeta_salida>

# App local de pruebas (subir archivos a mano, ver resultado y detalle por página)
python filtro_calidad/app.py                       # http://127.0.0.1:8000  (--red para la LAN)
```

La primera ejecución descarga los modelos de RapidOCR (~20 MB). ~10 s por documento en CPU.
En Windows con Python de la Store: si se usa `python -I`, no ve los paquetes instalados con `--user`.

## 9. Convenciones

- Código, mensajes y documentación en español. Mensajes al usuario claros y accionables.
- Todo lo ajustable (umbrales, frases) vive en `filtro_calidad/config.py`; subir `VERSION_REGLAS` al cambiarlo.
- Decisiones deterministas y reproducibles; cada resultado guarda SHA-256 y versión de reglas.
- No subir documentos reales ni resultados: `_trabajo/`, `_subidas/`, `.env*` están en `.gitignore`.

## 10. Preguntas abiertas

- ¿4 o 5 documentos (número oficial separado)? Front vs. requerimientos/BD.
- ¿Dónde vivirán los archivos: Supabase Storage (recomendado) o bytea? Nombre final de la columna.
- Vigencia válida para Alineamiento y Uso de Suelo; giro comercial requerido.
- Conseguir 50–100 documentos negativos reales para calibrar el clasificador (TF-IDF/embeddings).
