# Hackaton 3B — Pipeline OCR local

Extrae texto de los documentos de cada inmueble (`Alineamiento_y_Numero_Oficial`, `Escritura`,
`Predial`, `Uso_de_suelo`). Todo corre local y gratis: PyMuPDF + PaddleOCR (principal) y
Tesseract (alternativo), con preprocesamiento opcional en OpenCV.

## Instalación (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
```

La primera ejecución de PaddleOCR descarga sus modelos (~100 MB) a `%USERPROFILE%\.paddlex`.

### Tesseract (opcional, para comparar)

1. Instalar el binario: `winget install UB-Mannheim.TesseractOCR`
   (o el instalador de https://github.com/UB-Mannheim/tesseract/wiki). Queda en
   `C:\Program Files\Tesseract-OCR\`.
2. El proyecto usa su propia carpeta `tessdata/` (ignorada por git) y no la de la instalación.
   Para prepararla:
   ```bash
   mkdir tessdata
   curl -L -o tessdata/spa.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
   cp "/c/Program Files/Tesseract-OCR/tessdata/eng.traineddata" tessdata/
   cp "/c/Program Files/Tesseract-OCR/tessdata/osd.traineddata" tessdata/
   ```
3. El motor fija `TESSDATA_PREFIX` a `./tessdata` automáticamente. Se usa la variable y no
   `--tessdata-dir` para evitar problemas de comillas en Windows. Para usar otra carpeta, pasa
   `--tessdata-dir RUTA`. Si `tesseract.exe` no está en el PATH ni en la ruta por defecto,
   pasa `--tesseract-cmd RUTA`.

Si falta Tesseract o el idioma `spa`, el programa lo detecta, imprime cómo instalarlo y termina
sin traceback. `compare_engines.py` simplemente omite ese motor.

## Uso

```powershell
.venv\Scripts\activate
python run_ocr.py                                   # todo, PaddleOCR, sin preprocesamiento
python run_ocr.py --limit-per-folder 2 --order size # prueba: 2 docs más pequeños por carpeta
python run_ocr.py --folder Predial --limit 3
python run_ocr.py --engine tesseract --output output_tess
python run_ocr.py --preprocess --pre-steps deskew,denoise
python run_ocr.py --force                           # reprocesa aunque ya exista salida
python run_ocr.py -h                                # todas las opciones

python compare_engines.py                           # 2 docs/carpeta × {paddle,tesseract} × {raw,pre}
python compare_engines.py --per-folder 3 --max-pages 2 --pick shortest
```

## Salida (`output/`)

| Archivo | Contenido |
|---|---|
| `<Carpeta>/<archivo>.txt` | Texto completo con encabezado (fuente, SHA-256) y separadores `===== Página N / M \| método \| confianza =====` |
| `<Carpeta>/<archivo>.json` | Metadatos: origen, tipo, páginas, método/motor/confianza/tiempo por página, confianza promedio, caracteres, estado, errores, `duplicate_of` |
| `resumen.csv` | Una fila por documento (UTF-8 con BOM, para que Excel abra bien los acentos) |
| `resumen.xlsx` | Hoja `documentos` (con estado coloreado y vista previa) y hoja `paginas` (texto por página) |
| `pipeline.log` | Log completo de la corrida |

Cada salida se nombra con el nombre original del archivo, incluida su extensión
(`02 Predial...pdf.txt`), para que siempre se pueda rastrear el documento de origen.

**Estados:** `ok`; `low_text` (menos de 80 caracteres por página: borroso, vacío o solo sellos);
`low_confidence` (confianza menor a 0.80); `partial` (falló alguna página); `error`.

**Comportamiento:**
- **Texto nativo contra OCR:** una página de PDF usa su capa de texto si tiene 50 o más
  caracteres alfanuméricos (`--min-native-chars`). Si no, se renderiza a 300 DPI y se le
  aplica OCR. Con `--no-native` se fuerza OCR siempre.
- **Duplicados:** un archivo con el mismo SHA-256 que otro ya procesado no se vuelve a pasar
  por OCR. Se reutiliza el texto y se marca `duplicate_of`.
- **Reanudable:** un documento cuyo `.json` ya existe (con estado distinto de `error`) se salta.
  Para reprocesar, usa `--force`. El CSV y el Excel se regeneran al final con todo lo que haya
  en `output/`.

## Estructura del código

```
ocr_pipeline/
  config.py       parámetros (dataclasses)
  loaders.py      PDF/imagen → texto nativo o imagen renderizada; SHA-256
  preprocess.py   escala de grises, mediana, deskew (perfil de proyección), binarización
  engines/        interfaz OCREngine + PaddleEngine + TesseractEngine (registro en __init__.py)
  pipeline.py     descubrimiento, procesamiento por página, dedupe, reanudación
  outputs.py      .txt, .json, CSV y Excel
run_ocr.py        CLI principal
compare_engines.py
```

**Agregar un motor** (p. ej. EasyOCR): crea una subclase de `OCREngine` en `engines/` con
`check_available()` y `ocr(image) -> OCRResult`, y regístrala en `ENGINES`, en
`engines/__init__.py`.
