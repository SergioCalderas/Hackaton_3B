# Análisis de expedientes con LLM (LangChain + LangGraph)

Este módulo recibe los documentos de **un** inmueble (escritura, predial, alineamiento y número
oficial, uso de suelo) y produce el dictamen que pide el reto: estado **Cumple / Requiere revisión /
No cumple**, hallazgos con **evidencia por página**, requisitos cumplidos y no cumplidos, datos
extraídos y nivel de confianza. Todo el proceso tarda **menos de 1 minuto** por expediente con
`qwen3.5:9b` en local.

```
archivos ─► OCR paralelo ─► agentes extractores (LLM) ─► validador cruzado ─► dictaminador ─► JSON
            (Tesseract)       uno por tipo de documento     (reglas)            (LLM)
```

## Inicio rápido

```powershell
py -3.12 -m venv .venv                     # (3.11 también sirve)
.venv\Scripts\pip install -r requirements.txt -r requirements-llm.txt   # PaddleOCR es opcional aquí
# Modelos de Tesseract (tessdata/ está en .gitignore)
mkdir tessdata
curl.exe -L -o tessdata\spa_fast.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata
curl.exe -L -o tessdata\spa.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
# LLM local
ollama pull qwen3.5:9b
copy .env.example .env                     # opcional: los defaults ya usan Ollama

.venv\Scripts\streamlit run app_streamlit.py          # visor de pruebas en http://localhost:8501
.venv\Scripts\python benchmark_analisis.py            # todos los expedientes de ejemplo, OCR en frío
.venv\Scripts\python -m pytest                        # pruebas rápidas (sin OCR ni LLM, ~10 s)
```

## Switch local / online

Solo se cambia `.env` (ver [.env.example](.env.example)):

| Variable | Local (default) | Online |
|---|---|---|
| `LLM_PROVIDER` | `local` | `online` |
| Modelo | `OLLAMA_MODEL=qwen3.5:9b` | `CLAUDE_MODEL=claude-haiku-5-5` |
| Credencial | — | `ANTHROPIC_API_KEY=...` |

Las dos rutas usan los mismos agentes y esquemas de LangChain: Ollama con salida estructurada por
JSON Schema y Claude con *tool calling*. En modo online se envían hasta 40,000 caracteres por
documento, porque no hay costo de tiempo local.

> **Aviso:** en modo online, el texto OCR de los documentos se envía a la API de Anthropic. La página
> del reto pide no subir los documentos del reto a otros servicios. Confirmen con el comité antes de
> usar el modo online con esos documentos.

## Arquitectura multiagente

Grafo de LangGraph ([analisis/grafo.py](analisis/grafo.py)). Cada archivo recorre su propio subgrafo
**en paralelo** con los demás. Así el OCR de una escritura larga (CPU) corre mientras el LLM (GPU) ya
extrae los documentos cortos.

```
START ─Send(por archivo)─► analizar_documento:
                             agente_ocr ─► agente_clasificador ─┬─► extractor_escritura
                                                                ├─► extractor_predial
                                                                ├─► extractor_alineamiento
                                                                ├─► extractor_uso_suelo
                                                                └─► sin_tipo
                           ─► validador_cruzado ─► dictaminador ─► END
```

| Agente | Qué hace |
|---|---|
| `agente_ocr` | Texto nativo del PDF o Tesseract en paralelo. Reutiliza `ocr_pipeline`: contrato `Documento`, calidad y campos por regex |
| `agente_clasificador` | Tipo por palabras clave (`detectar_tipo` del equipo). Si no es concluyente, pregunta al LLM |
| `extractor_*` | Un agente por tipo, con su esquema y su prompt. Pide al LLM solo **valores**, sin páginas ni citas; eso hace corta (y rápida) la salida |
| `validador_cruzado` | Reglas deterministas entre documentos. Ver la tabla de abajo |
| `dictaminador` | El LLM redacta el resumen y las acciones. **Solo puede escalar el estado**: nunca aprueba lo que las reglas marcaron |

**Dos agentes que se verifican entre sí.** Cada dato del LLM se compara con el extractor por regex
del equipo. El campo `fuente` lo registra:
- `llm+reglas`: los dos coinciden.
- `reglas`: el LLM no lo encontró y se usó el valor de regex.
- `llm`: solo lo encontró el LLM.

Si el LLM falla (Ollama caído o *timeout*), el análisis sigue solo con regex y lo indica.

## Evidencia y trazabilidad

El LLM no inventa páginas. [analisis/evidencia.py](analisis/evidencia.py) **busca cada valor en el
texto OCR**: tolera acentos, mayúsculas, saltos de línea y errores de OCR, y reconoce fechas en otro
formato y claves con otros separadores. Con eso devuelve la página y la **cita literal**:

```json
{"documento": "Predial/02 Predial.pdf", "tipo_documento": "Predial", "pagina": 1,
 "cita": "…CLAVE CATASTRAL 112 03 145 18 00 0000 PROPIETARIO / POSEEDOR QUINTANAR…",
 "valor": "112 03 145 18 00 0000", "verificada": true}
```

`verificada: false` significa que el valor no se encontró en el texto, y el front debe mostrarlo como
no verificado. Para el **acceso directo** a la página basta con `<url del archivo>#page=<pagina>`:
los visores PDF de Chrome, Edge y Firefox abren esa página. El visor Streamlit lo implementa así:
"Como se visualiza en la *página 1* de **Predial**". Al pasar el mouse por "página 1" aparece la
miniatura de la página, la cita y el enlace "Abrir página 1 ↗" (ver
[analisis/visor.py](analisis/visor.py)).

## Cómo se decide el estado

| Regla | Resultado si falla | Severidad |
|---|---|---|
| Faltan documentos (los 4 tipos mínimos) | No cumple | crítica |
| El uso de suelo **no** permite el uso requerido (`USO_REQUERIDO`) | No cumple | crítica |
| Documento de **otro inmueble**: difieren la clave catastral **y** la calle o el municipio, con otro titular | No cumple | crítica |
| Lo mismo, pero con el mismo titular o sin clave comparable (esquina, colindante, escritura antigua) | Requiere revisión | revisión |
| Clave catastral, calle, número oficial, colonia, municipio, lote o manzana distintos | Requiere revisión | revisión |
| Propietario de la escritura distinto al del predial | Requiere revisión | revisión |
| Superficie de terreno con diferencia mayor a `SUPERFICIE_TOLERANCIA` (5 %) | Requiere revisión | revisión |
| Licencia o alineamiento vencidos a la `FECHA_REFERENCIA` | Requiere revisión | revisión |
| Predial con ejercicio anterior al de referencia (`PREDIAL_TOLERANCIA_ANIOS`) | Requiere revisión | revisión |
| Afectación o restricción en el alineamiento | Requiere revisión | revisión |
| Documento ilegible o con menos de 2 datos clave | Requiere revisión | revisión |
| Los agentes LLM y de reglas discrepan sobre la compatibilidad del uso de suelo | Requiere revisión | revisión |
| S/N contra número, titular del trámite distinto, restricciones de la licencia | informativo | info |

Para no rechazar expedientes que pueden continuar (criterio de evaluación del reto), "No cumple"
solo aparece cuando hay un impedimento definitivo. Los umbrales son variables de entorno. Cuando el
comité entregue los criterios oficiales, se ajustan en [analisis/reglas.py](analisis/reglas.py).

**Fecha de referencia.** Por defecto es hoy. Varios documentos de ejemplo vencían en 2026, y con la
fecha actual (nov. 2026) ya están vencidos. Si el dictamen de referencia del comité usa otra fecha,
configúrenla en `FECHA_REFERENCIA`.

**Confianza** (0 a 1, alta/media/baja): combina la calidad del OCR, la cobertura de datos clave, la
evidencia verificada, el acuerdo entre agentes y la completitud.

## Contrato JSON para front y backend

`analizar_expediente()` devuelve un `ResultadoExpediente`
([analisis/esquemas.py](analisis/esquemas.py), JSON Schema en
[schemas/ResultadoExpediente.schema.json](schemas/ResultadoExpediente.schema.json)):

```
ResultadoExpediente
├── expediente_id, estado, estado_reglas, estado_llm, confianza, nivel_confianza, factores_confianza
├── resumen, observaciones[], dictamen_por (llm|reglas), uso_requerido, fecha_referencia
├── documentos_recibidos[], documentos_faltantes[], requisitos_cumplidos[], requisitos_no_cumplidos[]
├── hallazgos[]   {id, regla, categoria, resultado (cumple|no_cumple|revisar|informativo), severidad,
│                  descripcion, evidencias[] {documento, tipo_documento, pagina, cita, valor, verificada}}
├── documentos[]  {nombre_archivo, ruta_archivo, tipo, calidad_texto, estado_ocr, paginas_enviadas_llm,
│                  campos{campo: {etiqueta, valor, evidencia, fuente, valor_reglas, coincide_reglas}},
│                  error_llm, tiempos}
└── proveedor_llm, modelo_llm, tiempos {total_s, ocr_max_s, llm_extraccion_max_s, dictamen_s, carga_modelo_s, …}
```

```python
from analisis import analizar_expediente

res = analizar_expediente([
    ("Escritura/01 Escritura.pdf", "Escritura"),          # tipo declarado o None para detectarlo
    ("Predial/02 Predial.pdf", "Predial"),
    ("Alineamiento_y_Numero_Oficial/03 Alineamiento y Numero Oficial.pdf", "Alineamiento"),
    ("Uso_de_suelo/04 Licencia de Uso de Suelo.pdf", "UsoDeSuelo"),
], al_progresar=print)                                    # callback opcional: eventos por agente
```

El modelo se carga una sola vez por proceso y se mantiene en la GPU (`OLLAMA_KEEP_ALIVE`). Si no está
cargado, `analizar_expediente` lo precarga y lo reporta aparte en `tiempos.carga_modelo_s` (unos 14 s
en frío). Ese tiempo no cuenta en el minuto.

## Rendimiento

Equipo de pruebas: i7-13700H (20 hilos), 16 GB de RAM y RTX 4060 Laptop de 8 GB. `qwen3.5:9b` Q4_K_M
con Ollama en su configuración por defecto (una petición a la vez). OCR **en frío**, sin caché:

BENCHMARK_TABLA

Decisiones que lo hacen posible (cada una medida):

| Cambio | Efecto |
|---|---|
| OCR de todas las páginas en paralelo (`OMP_THREAD_LIMIT=1` por proceso), renderizado en PGM gris y en pipeline | Escritura de 25 páginas: **13 s** contra ~140 s del motor en serie |
| `spa_fast` en vez de `spa` (best) en paralelo | 3x más rápido con la misma calidad (0.888 contra 0.878 de palabras válidas) |
| 250 DPI | −25 % de tiempo sin perder calidad en la muestra |
| `reasoning=False` (qwen3.5 "piensa" por defecto) | Evita cientos de tokens de razonamiento por llamada |
| `num_gpu=99` (todas las capas en GPU) | 22 → 30 tokens/s |
| El LLM solo devuelve valores; la evidencia se calcula en Python | Salida de ~150 tokens por documento |
| Contexto: primera página más las más relevantes, hasta 12,000 caracteres | La escritura de 50 páginas cabe en 8k tokens |
| Todas las propiedades del JSON Schema son obligatorias | Sin esto, qwen3.5 omitía el uso autorizado y el giro |

**Recomendado: `OLLAMA_NUM_PARALLEL=4`** (variable de usuario de Windows; después hay que reiniciar
Ollama). Las 4 extracciones corren a la vez en la GPU y el tiempo de LLM baja ~40 %. Medido: el
Sintético A pasó de 32.7 s a 19.8 s, con las 33 capas en GPU y 6.7 GB de VRAM.

## Pruebas

```powershell
.venv\Scripts\python -m pytest                       # 86 rápidas: reglas, evidencia, switch, grafo con LLM simulado, visor
.venv\Scripts\python -m pytest -m "llm and not slow" # extracción con Ollama real
.venv\Scripts\python -m pytest -m "slow and llm" -s  # 10 expedientes reales: estado esperado y < 60 s, OCR en frío
```

## Estructura

```
analisis/
  config.py      variables de entorno (switch local/online, OCR, reglas)
  llm.py         ChatOllama / ChatAnthropic, salida estructurada, precarga
  ocr_rapido.py  agente OCR en paralelo (reutiliza ocr_pipeline)
  contexto.py    selección de páginas y limpieza del texto para el LLM
  esquemas.py    esquemas de extracción por tipo + contrato de salida
  prompts.py     prompts de los agentes
  agentes.py     clasificador y extractores (evidencia + doble verificación)
  evidencia.py   localiza cada valor en el texto: página y cita
  comparar.py    normalización y similitud entre documentos
  reglas.py      validador cruzado, estado y confianza
  dictamen.py    agente dictaminador
  grafo.py       grafo LangGraph + analizar_expediente()
  ejemplos.py    expedientes de ejemplo armados con los documentos del reto
  visor.py       enlaces a página, miniaturas y diagrama para Streamlit
app_streamlit.py  benchmark_analisis.py  .env.example  requirements-llm.txt
```

## Limitaciones conocidas

- Los expedientes de ejemplo no sintéticos se armaron por nombre de archivo. La escritura de Melchor
  Ocampo III es antigua (otro titular y nomenclatura anterior) y queda en revisión.
- Tesseract no detecta páginas giradas; PaddleOCR sí, pero es más lento. Si aparecen escaneos
  rotados, se puede activar el motor `hybrid` del equipo para esas páginas.
- Las reglas son una propuesta basada en la página del reto. Hay que alinearlas con los criterios
  oficiales y con el dictamen de referencia cuando los entregue el comité.
