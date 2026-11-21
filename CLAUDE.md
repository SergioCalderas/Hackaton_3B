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
  etapa_extraccion.py                Fase 2 — PLANTILLA, aquí va el siguiente filtro
  fuentes.py                         obtiene el archivo desde la BD (bytea, URL o ruta)
  api.py                             endpoints /api/documentos/... y /api/operaciones/...
  sql/propuesta.sql                  columna `archivo` + tabla filtro_resultados (NO ejecutado)
filtro_calidad/                    Fase 1 como librería + CLI + app local de pruebas
  filtro.py                          motor del filtro (CLI por lotes)
  config.py                          umbrales, frases clave, negativos, mensajes
  app.py                             app local para subir archivos y probar (puerto 8000)
Escritura/ Predial/ Uso_de_suelo/ Alineamiento_y_Numero_Oficial/   documentos de prueba del reto
public/docs/<tipo>/caso-00N.pdf    PDFs que muestra hoy el front (8 casos)
```

Ramas: `main` (integración), `Wendy` (pipeline/filtro), `SabrinaMichaus` (front),
`SergioCalderas` (front + BD), `YaxLira` (comparación de motores OCR: `ocr_pipeline/`, Tesseract vs Paddle),
`AlbertoFlores` (vacía).

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

`?hasta=calidad` corre solo la Fase 1. Respuesta: `{nombre, tabla, id, tipo_declarado, etapas, version_reglas, calidad: {...}, extraccion: {...}}`.
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
  `src/lib/seed.js` + localStorage.

### Observaciones y dictamen (última etapa)

- `procesamiento/observaciones.py`: convierte resultados en observaciones uniformes
  `{id, tabla, documento, etapa, codigo, regla, severidad, bloquea, texto}`. Severidad CRITICA/ALTA/MEDIA/BAJA;
  códigos `FALTA-ARCHIVO`, `CAL-RECHAZO`, `CAL-COMBINADO`, `CAL-NO-COMPROBANTE`, `CAL-TIPO-DUDOSO`,
  `RIESGO-VIGENCIA` (RG-01), `RIESGO-ADEUDO`/`RIESGO-PERIODO` (RG-04), `CAL-IMAGEN`, `CAL-LECTURA`…
  Las fases futuras (VC-xx, RG-xx) deben agregar sus hallazgos con esta misma forma.
- `procesamiento/dictamen.py`: **el código decide el semáforo** (GRIS faltan/rechazados, ROJO crítico,
  AMARILLO media/alta, VERDE solo Fase 1) y **el LLM solo redacta** con salida JSON por esquema
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

## 7. Fase 2 — Extracción (SIGUIENTE)

Plantilla en `procesamiento/etapa_extraccion.py`. Recibe solo documentos `APROBADO`.

- `leer_paginas(doc)` devuelve texto y líneas OCR **con cajas** de todas las páginas, reutilizando la
  caché de la Fase 1 (`procesamiento/_trabajo/.cache_ocr/`, por SHA-256). Las cajas están en píxeles
  del render (lado mayor = 2000 px) → convertir a coordenadas PDF para la evidencia.
- Campos por tipo (los * son obligatorios): ver docstring del módulo o sección 2 de los requerimientos.
- Formatos fijos (predial, alineamiento, uso de suelo): regex + plantillas. Escrituras: localizar fragmentos
  ("superficie", "comparece", "ubicado en") y mandar solo eso a un LLM barato con salida estructurada.
- Cada campo: `valor`, `valor_normalizado`, `confianza`, `evidencia {pagina, fragmento, bbox}`.
- Para agregar etapas: nueva función `ejecutar(doc) -> ResultadoEtapa` y añadirla a `ETAPAS` en `pipeline.py`.

Después: normalización → validación cruzada VC → riesgos RG → evidencia → dictamen semáforo.

## 8. Cómo correr

```bash
# Front
npm install && npm run dev                          # https://localhost:5173

# Backend (login + pipeline)
pip install -r server/requirements.txt             # incluye filtro_calidad/requirements.txt
python server/app.py                               # http://127.0.0.1:5000

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
