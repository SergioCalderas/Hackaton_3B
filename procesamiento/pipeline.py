"""Orden de las etapas y contrato entre ellas.

Cada etapa es una función  etapa(doc: Documento) -> ResultadoEtapa.
  - Lee lo que necesite de `doc` (archivo en disco, tipo, resultados de etapas previas).
  - Devuelve sus datos y si el documento puede continuar a la siguiente etapa.
El pipeline se detiene en la primera etapa que diga continuar=False.

Para agregar el siguiente filtro: implementa la función en su propio módulo y
agrégala a ETAPAS (ver etapa_extraccion.py como plantilla).
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import etapa_calidad, etapa_extraccion

DIR_TRABAJO = Path(__file__).resolve().parent / "_trabajo"     # ignorado por git
DIR_CACHE_OCR = DIR_TRABAJO / ".cache_ocr"                     # compartida por todas las etapas

# El motor OCR no es seguro entre hilos: una etapa con OCR a la vez.
CANDADO_OCR = threading.Lock()


@dataclass
class Documento:
    nombre: str
    ruta: Path                      # copia local del archivo
    tipo_declarado: str | None      # escritura | predial | alineamiento | uso_suelo | None
    tabla: str | None = None        # origen en BD, si aplica
    id: int | None = None
    resultados: dict = field(default_factory=dict)   # nombre_etapa -> datos


@dataclass
class ResultadoEtapa:
    datos: dict
    continuar: bool


ETAPAS: list[tuple[str, Callable[[Documento], ResultadoEtapa]]] = [
    ("calidad", etapa_calidad.ejecutar),        # Fase 1
    ("extraccion", etapa_extraccion.ejecutar),  # Fase 2 (ocr_pipeline: campos con evidencia)
    # La validación cruzada es por expediente, no por documento: etapa_verificacion.py
    # (la llama observaciones.de_operacion). Siguiente: ("riesgos", ...)
]


def procesar_bytes(contenido: bytes, nombre: str, tipo: str | None = None,
                   tabla: str | None = None, id_: int | None = None,
                   hasta: str | None = None) -> dict:
    """Corre el pipeline sobre un archivo en memoria. `hasta` = última etapa a correr."""
    carpeta = Path(tempfile.mkdtemp(prefix="doc_", dir=_dir_trabajo()))
    ruta = carpeta / (Path(nombre).name or f"documento-{uuid.uuid4().hex[:6]}.pdf")
    ruta.write_bytes(contenido)
    try:
        doc = Documento(nombre=Path(nombre).name, ruta=ruta, tipo_declarado=tipo, tabla=tabla, id=id_)
        return procesar(doc, hasta=hasta)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def procesar(doc: Documento, hasta: str | None = None) -> dict:
    t0 = time.time()
    etapas_corridas = []
    for nombre, etapa in ETAPAS:
        r = etapa(doc)
        doc.resultados[nombre] = r.datos
        etapas_corridas.append(nombre)
        if not r.continuar or nombre == hasta:
            break
    return {
        "nombre": doc.nombre,
        "tabla": doc.tabla,
        "id": doc.id,
        "tipo_declarado": doc.tipo_declarado,
        "etapas": etapas_corridas,
        "version_reglas": etapa_calidad.VERSION_REGLAS,
        "segundos": round(time.time() - t0, 1),
        **doc.resultados,
    }


def _dir_trabajo() -> Path:
    DIR_TRABAJO.mkdir(parents=True, exist_ok=True)
    return DIR_TRABAJO
