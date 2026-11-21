"""API HTTP mínima (local) para que el front se conecte al módulo.

    uvicorn api:app --host 127.0.0.1 --port 8000
    # Documentación interactiva: http://127.0.0.1:8000/docs

POST /documento   multipart: archivo=<file>, tipo_declarado=<Predial|Alineamiento|Escritura|UsoDeSuelo> (opcional)
POST /expediente  multipart: archivos=<file> (varios), tipos=<tipo> (opcional, uno por archivo y en el mismo orden)
GET  /salud
"""
from __future__ import annotations

import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from ocr_pipeline.config import SUPPORTED_EXTENSIONS
from ocr_pipeline.schemas import VERSION_ESQUEMA, Documento, Expediente
from ocr_pipeline.servicio import precargar, procesar_documento, verificar_expediente


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.motor = precargar()  # el motor OCR se carga una sola vez al arrancar
    yield


app = FastAPI(title="OCR expedientes de inmuebles", version=VERSION_ESQUEMA, lifespan=lifespan)


def _guardar(upload: UploadFile, carpeta: Path, i: int = 0) -> tuple[Path, str]:
    nombre = Path(upload.filename or f"archivo_{i}").name
    ext = Path(nombre).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Extensión no soportada: {ext or '(sin extensión)'}. "
                                 f"Soportadas: {sorted(SUPPORTED_EXTENSIONS)}")
    destino = carpeta / f"{i:03d}_{re.sub(r'[^A-Za-z0-9._-]', '_', nombre)}"
    with open(destino, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return destino, nombre


@app.get("/salud")
def salud():
    return {"estado": "ok", "motor": getattr(app.state, "motor", None), "VersionEsquema": VERSION_ESQUEMA}


# Endpoints síncronos a propósito: FastAPI los corre en un threadpool y el OCR (CPU) no bloquea el loop.
@app.post("/documento", response_model=Documento)
def post_documento(archivo: UploadFile = File(...), tipo_declarado: Optional[str] = Form(None)):
    with tempfile.TemporaryDirectory(prefix="ocr_") as tmp:
        ruta, nombre = _guardar(archivo, Path(tmp))
        try:
            return procesar_documento(ruta, tipo_declarado, nombre_original=nombre)
        except Exception as e:
            raise HTTPException(422, f"No se pudo procesar {nombre}: {type(e).__name__}: {e}")


@app.post("/expediente", response_model=Expediente)
def post_expediente(archivos: list[UploadFile] = File(...), tipos: list[str] = Form(default=[])):
    if tipos and len(tipos) != len(archivos):
        raise HTTPException(400, "Si envías 'tipos', debe haber uno por archivo y en el mismo orden")
    with tempfile.TemporaryDirectory(prefix="ocr_") as tmp:
        docs = []
        for i, up in enumerate(archivos):
            ruta, nombre = _guardar(up, Path(tmp), i)
            tipo = (tipos[i] or None) if tipos else None
            try:
                docs.append(procesar_documento(ruta, tipo, nombre_original=nombre))
            except Exception as e:
                raise HTTPException(422, f"No se pudo procesar {nombre}: {type(e).__name__}: {e}")
        return verificar_expediente(docs)
