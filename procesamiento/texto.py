"""Texto extraído de un documento, para la sección "Texto extraído del documento" del caso.

No toca la BD: el texto por página vive en una caché en disco por SHA-256
(procesamiento/_trabajo/.cache_texto/<sha256>.json, ignorada por git). La llenan:
  - la Fase 2 (etapa_extraccion.py) cada vez que extrae un documento, y
  - este módulo bajo demanda (endpoints GET /api/texto y GET /api/documentos/<tabla>/<id>/texto),
  - o el precalentado antes de una demo:  python -m procesamiento.texto --precalentar

Los campos para resaltar (propietario, clave, etc.) se recalculan en cada consulta a partir del
texto en caché (milisegundos, sin OCR), así siempre corresponden al tipo pedido.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

VERSION_TEXTO = "texto v1"
RAIZ_REPO = Path(__file__).resolve().parents[1]
DIR_CACHE = Path(__file__).resolve().parent / "_trabajo" / ".cache_texto"
DIR_PUBLICO = RAIZ_REPO / "public"
EXTENSIONES = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

# tipo del front / del pipeline -> tipo de ocr_pipeline
TIPO_OCR = {
    "escrituras": "Escritura", "escritura": "Escritura", "predial": "Predial",
    "uso_suelo": "UsoDeSuelo", "suelo": "UsoDeSuelo", "alineamiento": "Alineamiento",
    "numero_oficial": "Alineamiento", "aliniamiento": "Alineamiento",
}
CAMPOS_RESALTAR = ("Propietario", "ClaveCatastral", "CuentaPredial", "NumeroOficial", "SuperficieTerreno",
                   "Direccion", "Calle", "Colonia", "Folio", "NumeroEscritura")


class TextoError(Exception):
    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.http = http


# ---------------------------------------------------------------------------
# Caché en disco
# ---------------------------------------------------------------------------
def _ruta_cache(sha: str) -> Path:
    return DIR_CACHE / f"{sha}.json"


def leer_cache(sha: str) -> dict | None:
    try:
        datos = json.loads(_ruta_cache(sha).read_text(encoding="utf-8"))
        return datos if datos.get("version") == VERSION_TEXTO else None
    except (OSError, ValueError):
        return None


def guardar_cache(sha: str, doc_completo: dict) -> dict:
    """Guarda el texto por página de un Documento de ocr_pipeline en modo completo."""
    datos = {
        "version": VERSION_TEXTO, "sha256": sha, "nombre": doc_completo.get("NombreArchivo"),
        "estado": doc_completo.get("Estado"), "calidad_texto": doc_completo.get("CalidadTexto"),
        "num_paginas": doc_completo.get("NumPaginas"),
        "paginas": [{"numero": p["Numero"], "texto": p.get("Texto") or "", "metodo": p["Metodo"],
                     "motor": p.get("Motor"), "calidad": p.get("CalidadTexto")} for p in doc_completo.get("Paginas", [])],
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    tmp = _ruta_cache(sha).with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _ruta_cache(sha))
    return datos


# ---------------------------------------------------------------------------
# Generación y respuesta
# ---------------------------------------------------------------------------
def _campos(datos: dict, tipo_ocr: str | None) -> dict:
    """Campos extraídos del texto en caché (sin OCR) -> {campo: {valor, pagina}} para resaltar."""
    from ocr_pipeline.fields import extraer_campos
    pages = [(p["numero"], p["texto"]) for p in datos["paginas"] if p["texto"]]
    if not pages:
        return {}
    campos = extraer_campos(pages, tipo_ocr)
    return {k: {"valor": c["Valor"], "pagina": c["Pagina"]} for k, c in campos.items() if k in CAMPOS_RESALTAR}


def respuesta(datos: dict, tipo: str | None, origen: str, segundos: float) -> dict:
    motores = []
    for p in datos["paginas"]:
        m = "texto nativo" if p["metodo"] == "native" else (p["motor"] or p["metodo"])
        if m not in motores:
            motores.append(m)
    return {
        "estado": "OK" if any(p["texto"] for p in datos["paginas"]) else "SIN_TEXTO",
        "estado_documento": datos["estado"], "sha256": datos["sha256"], "nombre": datos["nombre"],
        "num_paginas": datos["num_paginas"], "calidad_texto": datos["calidad_texto"], "motores": motores,
        "paginas": datos["paginas"], "campos": _campos(datos, TIPO_OCR.get(tipo or "")),
        "origen": origen, "segundos": round(segundos, 1), "generado_en": datos.get("generado_en"),
        "version": VERSION_TEXTO,
    }


def de_bytes(contenido: bytes, nombre: str, tipo: str | None = None, generar: bool = True) -> dict:
    """Texto de un archivo: desde la caché si existe; si no (y generar=True), con ocr_pipeline."""
    t0 = time.time()
    sha = hashlib.sha256(contenido).hexdigest()
    datos = leer_cache(sha)
    if datos:
        return respuesta(datos, tipo, "cache", time.time() - t0)
    if not generar:
        return {"estado": "SIN_EXTRAER", "sha256": sha, "nombre": nombre,
                "mensaje": "Aún no se ha extraído el texto de este documento."}

    from ocr_pipeline.servicio import procesar_documento
    from .pipeline import CANDADO_OCR

    with tempfile.TemporaryDirectory(prefix="texto_") as tmp:
        ruta = Path(tmp) / (Path(nombre).name or "documento.pdf")
        ruta.write_bytes(contenido)
        with CANDADO_OCR:  # una etapa con OCR a la vez (convención del pipeline)
            doc = procesar_documento(ruta, TIPO_OCR.get(tipo or ""), nombre_original=Path(nombre).name, modo="completo")
    datos = guardar_cache(sha, doc)
    return respuesta(datos, tipo, "ocr", time.time() - t0)


def ruta_publica(ruta: str) -> Path:
    """Valida una ruta del front (p. ej. "/docs/escrituras/caso-003.pdf") y la resuelve dentro de public/.
    Solo archivos locales: nada de URLs ni rutas fuera de public/."""
    if not ruta or "://" in ruta or ruta.startswith("//"):
        raise TextoError("Ruta no válida: solo se aceptan archivos de public/ (p. ej. /docs/predial/caso-001.pdf).")
    p = (DIR_PUBLICO / ruta.lstrip("/\\")).resolve()
    if DIR_PUBLICO.resolve() not in p.parents or p.suffix.lower() not in EXTENSIONES:
        raise TextoError("Ruta no válida: solo se aceptan documentos dentro de public/.")
    if not p.is_file():
        raise TextoError(f"No existe el archivo '{ruta}'.", 404)
    return p


def de_ruta_publica(ruta: str, tipo: str | None = None, generar: bool = True) -> dict:
    p = ruta_publica(ruta)
    return de_bytes(p.read_bytes(), p.name, tipo, generar)


# ---------------------------------------------------------------------------
# Precalentado (antes de una demo): python -m procesamiento.texto --precalentar
# ---------------------------------------------------------------------------
def precalentar(carpeta: Path = DIR_PUBLICO / "docs") -> None:
    """Genera la caché de texto de todos los documentos de public/docs/<tipo>/ (el tipo sale de la carpeta)."""
    archivos = sorted(p for p in carpeta.rglob("*") if p.suffix.lower() in EXTENSIONES)
    print(f"Precalentando {len(archivos)} documentos en {carpeta} -> {DIR_CACHE}", flush=True)
    t_total = time.time()
    for i, p in enumerate(archivos, 1):
        tipo = p.parent.name
        try:
            r = de_bytes(p.read_bytes(), p.name, tipo)
            print(f"[{i:>2}/{len(archivos)}] {r['origen']:<5} {r['segundos']:>6.1f}s  {p.relative_to(carpeta).as_posix():<40} "
                  f"págs={r['num_paginas']} calidad={r['calidad_texto']}", flush=True)
        except Exception as e:  # noqa: BLE001 — seguir con los demás
            print(f"[{i:>2}/{len(archivos)}] ERROR {p.relative_to(carpeta).as_posix()}: {e.__class__.__name__}: {e}", flush=True)
    print(f"Listo en {(time.time() - t_total) / 60:.1f} min.", flush=True)


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, str(RAIZ_REPO))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--precalentar", action="store_true", help="Generar la caché de texto de public/docs/")
    ap.add_argument("--carpeta", type=Path, default=DIR_PUBLICO / "docs")
    args = ap.parse_args()
    if args.precalentar:
        precalentar(args.carpeta)
    else:
        ap.print_help()
