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
Tablas `escrituras`, `predial`, `suelo`, `aliniamiento` (mismas columnas: `direccion_real`,
`propietario`, `numero_oficial`, `superficie`, `estado` 0/1, `direccion_memoria` hash bcrypt).
`operacion_realizada` junta un documento de cada tabla (+ lat/long y semáforo 1 rojo, 2 amarillo, 3 verde).

**Los documentos NO se suben desde el front: el pipeline los toma de la BD.** Las tablas aún no
tienen columna para el archivo. `procesamiento/fuentes.py` lee la columna `FILTRO_COLUMNA_ARCHIVO`
(por omisión `archivo`) y acepta: `bytea`, URL http(s) (Supabase Storage) o ruta relativa al repo
o a `public/` (p. ej. `docs/predial/caso-001.pdf`). Propuesta de esquema en `procesamiento/sql/propuesta.sql`.

Variables del servidor para el pipeline:

| Variable | Uso |
|---|---|
| `DATABASE_URL` | conexión Postgres (ya la usa el login) |
| `FILTRO_COLUMNA_ARCHIVO` | columna con el archivo (default `archivo`) |
| `FILTRO_GUARDAR_RESULTADOS=1` | inserta cada resultado en `filtro_resultados` |

## 5. API del pipeline (registrada en `server/app.py`)

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/procesamiento/salud` | etapas activas y versión de reglas |
| GET | `/api/operaciones` | todas las operaciones con el último resultado guardado por documento (sin OCR, ~2 s) |
| GET | `/api/operaciones/<id>` (y GET `…/verificar`) | una operación, último resultado guardado; GET nunca vuelve a correr el filtro |
| POST | `/api/documentos/<tabla>/<id>/verificar` | corre el pipeline sobre un documento de la BD |
| POST | `/api/operaciones/<id>/verificar` | los 4 documentos de `operacion_realizada` + completitud RF-01 (`EN_REVISION` / `NO_VALIDADO`) |
| POST | `/api/documentos/verificar-archivo` | multipart `archivo` (+ `tipo`), solo para pruebas |

`?hasta=calidad` corre solo la Fase 1. Respuesta: `{nombre, tabla, id, tipo_declarado, etapas, version_reglas, calidad: {...}, extraccion: {...}}`.
Campos clave de `calidad`: `estado`, `motivo`, `mensaje` (texto para el usuario), `observaciones`,
`tipo_detectado`, `legibilidad`, `confianza_ocr`, `paginas_revisadas[]`, `sha256`.
Tablas válidas: `escrituras | predial | suelo | aliniamiento` (lista blanca, sin SQL dinámico).

### Front ↔ pipeline

`src/lib/filtro.jsx` (`FiltroProvider`, `useFiltro`) consulta `GET /api/operaciones` al iniciar y
`POST /api/operaciones/<id>/verificar?hasta=calidad` con el botón **Verificar documentos**.
- Caso del front `cN` ↔ `operacion_realizada.id = N` (los 8 casos se cargaron en ese orden).
- Tipos front → tablas: `escrituras→escrituras`, `predial→predial`, `uso_suelo→suelo`,
  `alineamiento→aliniamiento`, `numero_oficial→aliniamiento` (la BD los junta).
- UI: tarjeta "Filtro de calidad · Fase 1" en `CaseDetail.jsx` (estado del expediente + por documento),
  etiqueta por documento en la lista y bloque con mensaje/observaciones en `DocModal.jsx`.
- El resto del front (revisión del gestor, semáforos de validación, historial) sigue usando
  `src/lib/seed.js` + localStorage.

Datos cargados en la BD (21-nov-2026): 8 operaciones con sus 4 documentos; `archivo` apunta a
`public/docs/<tipo>/caso-00N.pdf` (caso 5 sin uso de suelo). `numero_oficial='S/N'` y `superficie=0`
son **provisionales** hasta que la Fase 2 los extraiga. Conexión: en redes sin IPv6 usar el
**Session pooler** de Supabase (`aws-1-us-east-1.pooler.supabase.com`), no `db.<ref>.supabase.co`.

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
