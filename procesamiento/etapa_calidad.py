"""Fase 1: filtro de calidad. Envuelve filtro_calidad/filtro.py.

Continúa a la siguiente etapa solo si el estado es APROBADO.
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "filtro_calidad"))
import config as C  # noqa: E402
import filtro as F  # noqa: E402

VERSION_REGLAS = C.VERSION_REGLAS
TIPOS = list(C.TIPOS)
# El filtro toma el tipo declarado del nombre de la carpeta
_CARPETA = {"escritura": "Escritura", "predial": "Predial",
            "alineamiento": "Alineamiento_y_Numero_Oficial", "uso_suelo": "Uso_de_suelo"}


def ejecutar(doc):
    from .pipeline import CANDADO_OCR, DIR_CACHE_OCR, ResultadoEtapa

    raiz = doc.ruta.parent
    carpeta = raiz / _CARPETA.get(doc.tipo_declarado or "", "_sin_tipo")
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / doc.ruta.name
    shutil.copy2(doc.ruta, ruta)
    DIR_CACHE_OCR.mkdir(parents=True, exist_ok=True)

    with CANDADO_OCR:
        r = F.evaluar(ruta, raiz, DIR_CACHE_OCR)

    datos = {k: v for k, v in asdict(r).items() if k != "texto"}
    datos["archivo"] = doc.nombre
    datos["tipo_declarado_nombre"] = C.TIPOS[r.tipo_declarado]["nombre"] if r.tipo_declarado else None
    datos["tipo_detectado_nombre"] = C.TIPOS[r.tipo_detectado]["nombre"] if r.tipo_detectado else None
    return ResultadoEtapa(datos=datos, continuar=r.estado == "APROBADO")
