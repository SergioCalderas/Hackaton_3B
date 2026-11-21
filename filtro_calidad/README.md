# Filtro de calidad de documentos — Fase 1 (Recepción)

Primer filtro del pipeline, **antes** de extraer información. Para cada archivo decide:

| Estado | Qué significa | Qué pasa |
|---|---|---|
| `APROBADO` | Abre bien, es legible y es uno de los 4 tipos (el que se declaró) | Pasa a extracción de campos |
| `REVISION_MANUAL` | Dudoso: tipo ambiguo, lectura baja en algunas páginas, formato de pago en vez de comprobante, etc. | Lo revisa una persona |
| `VOLVER_A_SUBIR` | Mala calidad o documento equivocado | Se le pide al usuario subirlo de nuevo, con un mensaje claro |

Motivos de `VOLVER_A_SUBIR`: `formato_no_soportado`, `archivo_invalido` (corrupto o con contraseña),
`archivo_grande`, `en_blanco`, `ilegible`, `parcialmente_ilegible`, `otro_documento`
(recibo de luz, agua, INE, estado de cuenta, SAT…), `tipo_no_reconocido`, `tipo_incorrecto`
(p. ej. un predial subido como uso de suelo).

## Cómo decide (en cascada, de lo más barato a lo más caro, todo local en CPU)

1. **Formato** — extensión, tamaño, que abra, sin contraseña. SHA-256 del archivo (trazabilidad).
2. **Texto** — si el PDF trae texto nativo se usa directo (costo cero). Si es escaneo/foto,
   OCR local con RapidOCR (modelo PP-OCRv5 latino, el de PaddleOCR en ONNX). Se revisan como
   máximo 5 páginas: las 3 primeras, la de en medio y la última.
3. **Legibilidad por página** — en blanco (desviación de grises), caracteres leídos con confianza
   ≥ 0.80 y confianza media del OCR. Si casi no hay texto, prueba la página girada 90°/270°.
   Nitidez (Laplaciano), dpi y "foto de celular" solo generan observaciones: la decisión la toma
   lo que el OCR realmente logró leer.
4. **Tipo de documento** — frases clave por tipo (encabezado vale más) y frases de documentos
   que no son del expediente (CFE, INE, banco…). Si el tipo detectado no coincide con la carpeta
   declarada → `tipo_incorrecto`.
5. **Segunda opinión** — similitud TF-IDF (n-gramas de caracteres, tolerante a errores del OCR)
   contra los demás aprobados. Si no coincide con las frases clave → `REVISION_MANUAL`.
6. **Observaciones no bloqueantes** — posible vigencia vencida, adeudos. El riesgo formal
   (RG-01, RG-04) se evalúa en la fase de reglas, después de extraer.

Todos los umbrales y frases están en [`config.py`](config.py).

## Uso

```bash
pip install -r filtro_calidad/requirements.txt
python filtro_calidad/filtro.py <carpeta_entrada> --salida <carpeta_salida>
```

La carpeta de entrada puede tener subcarpetas por tipo (`Escritura/`, `Predial/`,
`Alineamiento_y_Numero_Oficial/`, `Uso_de_suelo/`); el nombre de la subcarpeta es el tipo declarado.

Salida:

```
<salida>/
  APROBADO/<Tipo>/...          copias de los aprobados
  REVISION_MANUAL/...
  VOLVER_A_SUBIR/<motivo>/...
  reporte.csv                  una fila por archivo (estado, motivo, mensaje, métricas)
  reporte.json                 detalle por página, puntajes, evidencia del tipo, umbrales usados
  .cache_ocr/                  OCR guardado por hash: volver a correr para ajustar umbrales es instantáneo
```

Los archivos originales no se mueven ni se modifican.

## App local para pruebas

```bash
python filtro_calidad/app.py          # http://127.0.0.1:8000
python filtro_calidad/app.py --red    # también accesible desde otras PCs de la misma red
```

Arrastra uno o varios archivos, elige el tipo declarado (o "Detectar automáticamente") y pulsa
**Verificar**. Para cada archivo muestra estado, mensaje para el usuario, observaciones,
miniatura y el detalle por página (caracteres leídos, confianza OCR, nitidez, dpi). Arriba se ve
la completitud del expediente (cuántos de los 4 tipos ya están aprobados).
Los archivos subidos quedan en `filtro_calidad/_subidas/` (ignorado por git). El historial se
borra al reiniciar la app o con **Limpiar**.

## Límites

- No prueba autenticidad: un documento alterado pero legible pasa. Eso requiere QR/folio y consulta a la autoridad.
- Inconsistencias de contenido entre documentos (otro predio, otro titular) se detectan en la validación cruzada (VC-01…07), no aquí.
- No divide archivos que traen varios documentos juntos.
