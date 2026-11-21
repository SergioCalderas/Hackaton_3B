# Hackaton 3B — OCR y verificación de expedientes de inmuebles

Módulo **local y gratuito** que extrae el texto de documentos escaneados de un inmueble
(escritura, boleta predial, alineamiento y número oficial, licencia de uso de suelo), extrae
sus campos clave con evidencia, verifica la coherencia entre documentos y entrega un JSON
listo para un LLM (vía LangChain) que da el veredicto final.

```
Front (sube los documentos de UN inmueble)
  → Filtro previo (otro equipo: archivo válido y legible)
  → ESTE MÓDULO: OCR + extracción de campos + verificación
  → JSON (Documento / Expediente)
  → LLM con LangChain (veredicto)
```

## Instalación (Windows, CPU)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
```

### Tesseract (obligatorio para el motor por defecto)

1. Instala el binario con `winget install UB-Mannheim.TesseractOCR`. También sirve el instalador de
   https://github.com/UB-Mannheim/tesseract/wiki. Queda en `C:\Program Files\Tesseract-OCR\`.
2. Prepara la carpeta `tessdata/` del proyecto (está en `.gitignore`):
   ```bash
   mkdir tessdata
   curl -L -o tessdata/spa.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
   cp "/c/Program Files/Tesseract-OCR/tessdata/eng.traineddata" tessdata/
   cp "/c/Program Files/Tesseract-OCR/tessdata/osd.traineddata" tessdata/
   ```
3. El motor fija `TESSDATA_PREFIX=./tessdata` por su cuenta. La primera corrida genera también
   `tessdata/spa_words.txt`: un léxico de español de unas 179 mil palabras, extraído de
   `spa.traineddata` con `combine_tessdata` y `dawg2wordlist`. Se usa para calcular `CalidadTexto`.
4. Si Tesseract está en otra ruta, pasa `--tesseract-cmd`. Si falta, el programa lo detecta y
   explica cómo instalarlo, sin mostrar un traceback.

La primera vez que se usa PaddleOCR (el respaldo) se descargan sus modelos, unos 100 MB, a
`%USERPROFILE%\.paddlex`.

## Cómo funciona

| Paso | Qué hace |
|---|---|
| Texto nativo contra OCR | Si una página del PDF tiene 50 o más caracteres útiles en su capa de texto, se usa esa capa. Si no, se renderiza a 300 DPI |
| **Motor `hybrid`** (por defecto) | Primero Tesseract `spa`, sin preprocesamiento. Si su confianza es menor a 0.75 o su calidad menor a 0.70, prueba **PaddleOCR con preprocesamiento** y se queda con el resultado que tenga **más palabras válidas**. Nunca decide por la confianza, porque la de Paddle está mal calibrada |
| `CalidadTexto` | Proporción (0 a 1) de tokens válidos: palabras del léxico, números, montos y códigos. Las letras sueltas, rayas y símbolos cuentan como inválidos. Es el criterio para marcar `low_confidence` (menor a 0.65) |
| Extracción de campos | Usa regex y reglas por tipo de documento. Cada campo guarda `Valor`, `Normalizado`, `Pagina`, `Evidencia` y `Regla` |
| `TipoDetectado` | Se calcula por palabras clave, y la primera página pesa el triple. Si no coincide con `TipoDeclarado`, se registra en `Discrepancias` |
| Matching | Puntaje ponderado: ClaveCatastral o CuentaPredial 0.40, dirección 0.30, propietario 0.20 y superficie 0.10. Usa rapidfuzz para tolerar errores de OCR y aplica una penalización si no coinciden municipio o estado |

`compare_engines.py` contiene la comparación que justifica el motor híbrido. En la muestra,
Tesseract raw obtuvo 87.6 % de palabras válidas contra 73 % de Paddle, y fue más rápido
(3.9 s por página contra 5.0 s).

## Uso

### 1. Batch sobre las 4 carpetas (demo y pruebas)

```powershell
.venv\Scripts\activate
python run_ocr.py                                    # OCR de todo + documentos/expedientes JSON + Excel
python run_ocr.py --limit-per-folder 2 --order size  # prueba rápida
python run_ocr.py --folder Predial --force           # reprocesar una carpeta
python run_ocr.py --engine tesseract|paddle          # forzar un solo motor
python export_json.py                                # regenera JSON y Excel sin repetir OCR
python export_json.py --umbral 0.8 --umbral-revisar 0.6
python compare_engines.py                            # comparación de motores × preprocesamiento
```

La corrida es reanudable: los documentos ya procesados se saltan, y con `--force` se reprocesan.
Los archivos idénticos (mismo SHA-256) no repiten OCR y se marcan con `DuplicadoDe`.

**Salidas en `output/`:**

| Archivo | Contenido |
|---|---|
| `<Carpeta>/<archivo>.txt` / `.json` | Texto con separadores por página, y metadatos del OCR por página (método, motor, confianza, calidad y tiempo) |
| `resumen.csv` / `resumen.xlsx` | Una fila por documento con su estado en colores. La hoja `paginas` trae el texto por página |
| **`documentos.json`** | Lista de objetos `Documento` (ver más abajo) |
| **`expedientes.json`** | Lista de objetos `Expediente`. **Es la entrada del LLM** |
| `expedientes.xlsx` | Hojas `expedientes`, `campos` (con evidencia), `sin_match` y `revisar`. Las dos últimas traen la columna `PistaNombreArchivo`, que es solo visual: el nombre del archivo **no** entra al puntaje |
| `pipeline.log` | Log de la corrida |

**Cómo se arman los expedientes en batch:**
- Se agrupan los pares de documentos con puntaje de 0.75 o más, y como máximo hay un documento por tipo.
- Se permiten **varios prediales** si son de ejercicios fiscales distintos. Si dos prediales son del mismo ejercicio, se marca en `CamposNoCoinciden`.
- Dos documentos del mismo tipo con clave catastral **idéntica** (por ejemplo, constancia de alineamiento y constancia de número oficial) también se unen, con una alerta.
- Los pares con puntaje entre 0.55 y 0.75, o los que solo coinciden en propietario y municipio, van a la hoja `revisar`.
- Los documentos sin campos útiles no se fuerzan: van a `sin_match`.

### 2. API de Python (integración)

```python
from ocr_pipeline import procesar_documento, verificar_expediente

doc = procesar_documento("boleta.pdf", tipo_declarado="Predial")   # dict con formato Documento

exp = verificar_expediente([                                       # dict con formato Expediente
    ("escritura.pdf", "Escritura"),
    ("boleta.pdf", "Predial"),
    ("alineamiento.pdf", "Alineamiento"),
    ("licencia.pdf", "UsoDeSuelo"),       # también acepta "uso de suelo", "uso_de_suelo"…
])
exp["CamposNoCoinciden"], exp["DocumentosFaltantes"], exp["PuntajeMatch"], exp["Alertas"]
```

- `verificar_expediente` **asume que todos los documentos son del mismo inmueble** y verifica su
  coherencia; no los agrupa. Si un documento no cuadra con el resto, aparece una alerta de
  "posible documento de otro inmueble".
- El motor OCR se carga **una sola vez por proceso**. Los resultados se cachean por SHA-256, así
  que procesar el mismo archivo otra vez tarda milisegundos. Es seguro usarlo desde varios hilos.
- `ocr_pipeline.servicio.configurar(PipelineConfig(engine="tesseract", dpi=200))` cambia la
  configuración del OCR.

### 3. API HTTP con FastAPI (local, opcional)

```powershell
uvicorn api:app --host 127.0.0.1 --port 8000      # documentación en http://127.0.0.1:8000/docs
```

```bash
curl -F "archivo=@boleta.pdf" -F "tipo_declarado=Predial" http://127.0.0.1:8000/documento
curl -F "archivos=@escritura.pdf" -F "tipos=Escritura" \
     -F "archivos=@boleta.pdf"    -F "tipos=Predial"   http://127.0.0.1:8000/expediente
curl http://127.0.0.1:8000/salud
```

`POST /documento` devuelve un `Documento` y `POST /expediente` devuelve un `Expediente`. Los
archivos se guardan en una carpeta temporal que se borra al terminar. Nada sale a la nube.

## Contrato JSON (`VersionEsquema` 1.0.0)

Los modelos Pydantic están en `ocr_pipeline/schemas.py` y su JSON Schema en
`schemas/*.schema.json`. Para regenerarlos: `python -m ocr_pipeline.schemas`. Toda salida se
valida contra estos modelos antes de escribirse o devolverse.

### Documento

| Campo | Descripción |
|---|---|
| `NombreArchivo`, `RutaArchivo` | Trazabilidad al archivo original |
| `TipoDocumento` | `Predial` \| `Alineamiento` \| `Escritura` \| `UsoDeSuelo`. Toma el declarado si existe y, si no, el detectado |
| `TipoDeclarado` / `TipoDetectado` | El que dio el usuario o la carpeta, y el inferido del contenido |
| `TextoExtraido` | Texto completo, con las páginas unidas por doble salto de línea |
| `Paginas[]` | `Numero`, `Texto`, `Metodo` (native/ocr), `Motor` (tesseract/paddle) y `CalidadTexto` |
| `Estado` | `ok` \| `low_text` \| `low_confidence` \| `partial` \| `error` |
| `CalidadTexto`, `NumPaginas`, `Hash`, `DuplicadoDe` | Calidad 0 a 1, número de páginas, SHA-256 corto y duplicado de qué archivo |
| `CamposExtraidos` | `{Campo: {Valor, Normalizado, Pagina, Evidencia, Regla}}`. Campos posibles: ClaveCatastral, CuentaPredial, Propietario, Vendedor, Direccion, Calle, NumeroOficial, Lote, Manzana, Colonia, Municipio, Estado, CodigoPostal, SuperficieTerreno, SuperficieConstruccion, NumeroEscritura, Volumen, Folio, FechaDocumento (ISO) y EjercicioFiscal |
| `Discrepancias` | Problemas propios del documento: tipo que no coincide, calidad baja o falta de campos |
| `ExpedienteId` | Expediente al que se asignó, o `null` |

Ejemplo real, recortado (`Predial/02 Predial.pdf`):

```json
{
  "VersionEsquema": "1.0.0",
  "NombreArchivo": "02 Predial.pdf",
  "RutaArchivo": "Predial/02 Predial.pdf",
  "TipoDocumento": "Predial", "TipoDeclarado": "Predial", "TipoDetectado": "Predial",
  "TextoExtraido": "MUNICIPIO DE SAN JERÓNIMO ATLACO, ESTADO DE MÉXICO\nTESORERÍA MUNICIPAL - CATASTRO E IMPUESTO PREDIAL\n\nRECIBO OFICIAL DE PAGO …",
  "Paginas": [{"Numero": 1, "Texto": "MUNICIPIO DE SAN JERÓNIMO ATLACO …", "Metodo": "ocr", "Motor": "tesseract", "CalidadTexto": 0.919}],
  "Estado": "ok", "CalidadTexto": 0.919, "NumPaginas": 1, "Hash": "1e1d4c78a6ddbf71", "DuplicadoDe": null,
  "CamposExtraidos": {
    "ClaveCatastral": {"Valor": "112 03 145 18 00 0000", "Normalizado": "1120314518000000", "Pagina": 1,
                       "Evidencia": "… DATOS DEL PREDIO CLAVE CATASTRAL 112 03 145 18 00 0000 PROPIETARIO / POSEEDOR QUINTANAR …",
                       "Regla": "clave catastral"},
    "Propietario":    {"Valor": "QUINTANAR LEDESMA ROSA MARIA", "Normalizado": "QUINTANAR LEDESMA ROSA MARIA", "Pagina": 1,
                       "Evidencia": "… PROPIETARIO / POSEEDOR QUINTANAR LEDESMA ROSA MARIA UBICACIÓN FRESNO 28, COL. LA LOMA …",
                       "Regla": "propietario/poseedor"},
    "EjercicioFiscal": {"Valor": "2025", "Normalizado": ["2025"], "Pagina": 1, "Evidencia": "…", "Regla": "tabla año"}
  },
  "Discrepancias": [],
  "ExpedienteId": "EXP-1120314518000000"
}
```

### Expediente

| Campo | Descripción |
|---|---|
| `ExpedienteId` | `EXP-<clave catastral>`, o `EXP-<hash>` si no hay clave |
| `CamposConsolidados` | `{Campo: {Valor, Normalizado, Fuentes[]}}`. Toma el valor más frecuente y conserva cada fuente con su documento y página |
| `PuntajeMatch`, `NivelMatch` | Promedio de los puntajes entre pares (0 a 1) y su nivel: `alto` (0.75 o más), `medio` (0.55 o más), `bajo` o `sin_datos` |
| `CamposCoinciden` | Campos donde todos los documentos coinciden |
| `CamposNoCoinciden[]` | `{Campo, Detalle, Similitud, Valores[]}`, con el valor de cada documento para que el LLM vea la discrepancia completa |
| `TiposPresentes`, `DocumentosFaltantes` | Cuáles de los 4 tipos hay y cuáles faltan |
| `Alertas` | Tipos repetidos, documentos ilegibles, un documento que no cuadra con el resto, etc. |
| `Comparaciones[]` | Puntaje y campos que coinciden o no, por cada par de documentos |
| `Documentos[]` | Los objetos `Documento` completos: el expediente es autocontenido |

Ejemplo real, recortado (expediente con discrepancias, `EXP-0980122309000000`):

```json
{
  "VersionEsquema": "1.0.0",
  "ExpedienteId": "EXP-0980122309000000",
  "CamposConsolidados": {"ClaveCatastral": {"Valor": "098 01 223 09 00 0000", "Normalizado": "0980122309000000", "Fuentes": ["…"]}},
  "PuntajeMatch": 0.8669, "NivelMatch": "alto",
  "CamposCoinciden": ["Calle", "Colonia", "Municipio", "Estado", "Lote", "Manzana"],
  "CamposNoCoinciden": [
    {"Campo": "ClaveCatastral", "Detalle": "difieren levemente (posible error de OCR o alteración)", "Similitud": 0.85,
     "Valores": [{"Documento": "Escritura/01 Escriturav.pdf", "TipoDocumento": "Escritura", "Valor": "098 01 223 09 00 0000", "Normalizado": "0980122309000000", "Pagina": 1},
                 {"Documento": "Predial/02 Predialv.pdf", "TipoDocumento": "Predial", "Valor": "098 01 223 19 00 0000", "Normalizado": "0980122319000000", "Pagina": 1}]},
    {"Campo": "Propietario", "Detalle": "valores distintos entre documentos", "Similitud": 0.593, "Valores": ["… JUAN CARLOS BENÍTEZ ARROYO vs BENITEZ ARROYO JORGE ARMANDO …"]},
    {"Campo": "NumeroOficial", "Detalle": "valores distintos entre documentos", "Similitud": 0.0, "Valores": ["… 15 vs 51 …"]},
    {"Campo": "SuperficieTerreno", "Detalle": "valores distintos entre documentos", "Similitud": 0.5, "Valores": ["… 312.50 vs 290.00 …"]}
  ],
  "TiposPresentes": ["Predial", "Alineamiento", "Escritura", "UsoDeSuelo"],
  "DocumentosFaltantes": [],
  "Alertas": [],
  "Comparaciones": [{"DocumentoA": "…Alineamiento…v.pdf", "DocumentoB": "Escritura/01 Escriturav.pdf", "Puntaje": 1.0, "Coinciden": ["ClaveCatastral", "…"], "NoCoinciden": []}, "…"],
  "Documentos": ["… objetos Documento completos …"]
}
```

## Estructura del código

```
ocr_pipeline/
  config.py         parámetros (dataclasses)
  loaders.py        PDF o imagen → texto nativo o imagen renderizada; SHA-256
  preprocess.py     OpenCV: escala de grises, mediana, deskew, binarización
  engines/          interfaz OCREngine + Tesseract, Paddle e Hybrid (registro en __init__.py)
  quality.py        léxico de español y CalidadTexto
  pipeline.py       batch: descubrimiento, OCR por página, dedupe, reanudación
  normalize.py      normalización: acentos, abreviaturas, nombres, fechas, números, claves
  fields.py         extracción de campos y detección de tipo
  matching.py       comparación por campo, agrupación batch y verificación de expediente
  schemas.py        contrato Pydantic + exportación de JSON Schema
  export.py         documentos.json, expedientes.json, expedientes.xlsx
  servicio.py       API de Python: procesar_documento / verificar_expediente
run_ocr.py  export_json.py  compare_engines.py  api.py
schemas/            JSON Schema de Campo, Pagina, Documento y Expediente
```

**Para agregar un motor OCR** (por ejemplo EasyOCR): crea una subclase de `OCREngine` en
`engines/` y regístrala en `ENGINES`.

**Para agregar un campo:** agrega la regla en `fields.py`. Si el campo debe compararse entre
documentos, agrega también su comparador en `COMPARADORES`, en `matching.py`.

## Limitaciones conocidas

- Las escrituras antiguas a máquina y los títulos de propiedad de varias páginas tienen menos
  cobertura de campos. Sus datos vienen en prosa, sin etiquetas.
- Algunos recibos reales traen la etiqueta **debajo** del valor. Se cubren los formatos vistos
  (Formato Universal de Pago del Edomex y formularios de Tlahuelilpan); otros formatos pueden
  necesitar reglas nuevas.
- `CalidadTexto` mide si el texto "parece español"; no garantiza que los dígitos sean correctos.
  Por eso las claves que difieren en un dígito se reportan como discrepancia y no se ocultan.
