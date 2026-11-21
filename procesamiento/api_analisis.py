"""Análisis multiagente con LLM (paquete analisis/) expuesto al servidor Flask del prototipo.

  POST /api/analisis          multipart: archivos=<file> (varios), tipos=<tipo> (opcional, uno por archivo)
                              tipos: escritura | predial | alineamiento | uso_suelo (o vacío = detectar)
                              -> ResultadoExpediente (estado, hallazgos con evidencia por página, datos, tiempos)
  GET  /api/analisis/salud    proveedor y modelo configurados, estado de Ollama

El proveedor sale de LLM_PROVIDER=local|online en .env (ver .env.example y README_ANALISIS.md).
Complementa al pipeline de procesamiento/ (filtro de calidad + semáforo por operación en BD): este
endpoint analiza un expediente completo en < 60 s con OCR paralelo y extracción con LLM.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request

bp = Blueprint("analisis_llm", __name__, url_prefix="/api")

TIPOS = {"escritura": "Escritura", "escrituras": "Escritura", "predial": "Predial", "alineamiento": "Alineamiento",
         "aliniamiento": "Alineamiento", "uso_suelo": "UsoDeSuelo", "suelo": "UsoDeSuelo", "usodesuelo": "UsoDeSuelo"}
EXTENSIONES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


@bp.get("/analisis/salud")
def salud():
    from analisis.config import Ajustes
    from analisis.llm import estado_ollama

    aj = Ajustes.desde_entorno()
    return jsonify(proveedor=aj.proveedor, modelo=aj.modelo,
                   ollama=estado_ollama(aj) if aj.es_local else None)


@bp.post("/analisis")
def analizar():
    from analisis import ConfiguracionError, analizar_expediente

    archivos = request.files.getlist("archivos")
    tipos = request.form.getlist("tipos")
    if not archivos:
        return jsonify(error="Envía al menos un archivo en el campo 'archivos'."), 400
    if tipos and len(tipos) != len(archivos):
        return jsonify(error="Si envías 'tipos', debe haber uno por archivo y en el mismo orden."), 400
    carpeta = Path(tempfile.mkdtemp(prefix="analisis_"))
    try:
        entradas = []
        for i, f in enumerate(archivos):
            nombre = Path(f.filename or f"archivo_{i}.pdf").name
            if Path(nombre).suffix.lower() not in EXTENSIONES:
                return jsonify(error=f"Extensión no soportada: {nombre}"), 415
            destino = carpeta / f"{i:02d}_{nombre}"
            f.save(destino)
            t = (tipos[i] or "").strip().lower() if tipos else ""
            entradas.append({"ruta": str(destino), "nombre": nombre, "tipo": TIPOS.get(t, t or None) or None})
        return jsonify(analizar_expediente(entradas))
    except ConfiguracionError as e:
        return jsonify(error=str(e)), 503
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
