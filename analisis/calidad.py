"""Fase 1 del equipo (filtro de calidad, procesamiento/etapa_calidad.py) dentro del análisis con IA.

Antes de extraer, cada documento pasa por el filtro que decide si es un documento válido:
  APROBADO        -> se extrae y entra a la validación cruzada
  REVISION_MANUAL -> se extrae, pero queda un hallazgo "revisar" con el motivo del filtro
  VOLVER_A_SUBIR  -> NO se extrae (otro documento, ilegible, en blanco, tipo incorrecto…): cuenta como
                     faltante y el semáforo queda GRIS ("No validado"), igual que en el pipeline de main.
El filtro corre en paralelo con el OCR del mismo documento para no sumar tiempo.
Si sus dependencias (rapidocr, onnxruntime…) no están instaladas, el análisis sigue sin él.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger("analisis")

# tipo de analisis/ocr_pipeline -> tipo del pipeline del equipo
TIPO_PIPELINE = {"Escritura": "escritura", "Predial": "predial", "Alineamiento": "alineamiento",
                 "UsoDeSuelo": "uso_suelo"}
CAMPOS = ("estado", "motivo", "mensaje", "observaciones", "tipo_detectado", "tipo_detectado_nombre",
          "legibilidad", "confianza_ocr", "sha256")


def disponible() -> bool:
    if os.environ.get("FILTRO_CALIDAD", "1").strip().lower() in ("0", "no", "false"):
        return False
    try:
        from procesamiento import etapa_calidad  # noqa: F401
        return True
    except Exception as e:  # noqa: BLE001 - dependencias del filtro ausentes
        log.info("Filtro de calidad no disponible: %s", e)
        return False


def evaluar(ruta: str | Path, nombre: str, tipo: str | None) -> dict | None:
    """Resultado de la Fase 1 ({estado, motivo, mensaje, observaciones, ...}) o None si no hay filtro."""
    if not disponible():
        return None
    from procesamiento import etapa_calidad
    from procesamiento.pipeline import Documento

    carpeta = Path(tempfile.mkdtemp(prefix="calidad_"))
    try:
        copia = carpeta / (Path(nombre).name or Path(ruta).name)
        shutil.copyfile(ruta, copia)
        doc = Documento(nombre=Path(nombre).name, ruta=copia, tipo_declarado=TIPO_PIPELINE.get(tipo or ""))
        datos = etapa_calidad.ejecutar(doc).datos
        return {k: datos.get(k) for k in CAMPOS}
    except Exception as e:  # noqa: BLE001 - el filtro nunca debe tumbar el análisis
        log.warning("Filtro de calidad falló en %s: %s", nombre, e)
        return None
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
