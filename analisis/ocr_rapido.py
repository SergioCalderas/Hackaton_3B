"""Agente OCR: Tesseract en paralelo con todos los núcleos, compatible con el contrato del equipo.

Diferencias con ocr_pipeline.pipeline.process_document (que procesa página por página):
  * Todas las páginas de TODOS los documentos comparten un pool de hilos: cada hilo lanza un
    proceso tesseract.exe con OMP_THREAD_LIMIT=1, así se usan todos los núcleos.
  * La página se renderiza en escala de grises a PGM (sin PNG ni conversión RGB) y se manda a OCR
    en cuanto está lista (render y OCR se solapan).
  * Idioma spa_fast y 250 DPI por defecto: en la escritura de 25 páginas de Tepeji, 13 s contra
    ~140 s del motor en serie, con la misma calidad de texto (0.885 vs 0.878 de palabras válidas).
La salida es un `Documento` (ocr_pipeline/schemas.py) con CamposExtraidos por reglas (regex).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

from ocr_pipeline.config import DEFAULT_TESSERACT_CMDS, IMAGE_EXTENSIONS, PDF_EXTENSIONS, PipelineConfig
from ocr_pipeline.engines.base import EngineUnavailableError
from ocr_pipeline.export import build_document
from ocr_pipeline.loaders import load_image_file, sha256_file, useful_chars
from ocr_pipeline.matching import canonical_tipo, enriquecer_documento
from ocr_pipeline.pipeline import compute_status, page_header
from ocr_pipeline.quality import load_lexicon, text_quality

from .config import RAIZ, Ajustes

log = logging.getLogger("analisis")

TESSDATA_PROYECTO = RAIZ / "tessdata"
CACHE_DIR = RAIZ / "output" / "cache_analisis"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_render_lock = threading.Lock()      # PyMuPDF no es thread-safe
_pool_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None
_pool_size = 0
_cache_mem: dict[str, tuple[dict, str]] = {}


# ---------------------------------------------------------------------------------------
# Tesseract
# ---------------------------------------------------------------------------------------
def tesseract_cmd() -> str:
    for c in (shutil.which("tesseract"), *DEFAULT_TESSERACT_CMDS):
        if c and Path(c).is_file():
            return c
    raise EngineUnavailableError("No se encontró Tesseract. Instálalo con: winget install UB-Mannheim.TesseractOCR")


def resolver_idioma(idioma: str) -> tuple[str, Path]:
    """(idioma, carpeta tessdata). Si no existe spa_fast, usa spa (proyecto o instalación)."""
    sistema = Path(tesseract_cmd()).parent / "tessdata"
    for lang in dict.fromkeys([idioma, "spa"]):
        for td in (TESSDATA_PROYECTO, sistema):
            if (td / f"{lang}.traineddata").is_file():
                if lang != idioma:
                    log.warning("No hay %s.traineddata; se usa %s de %s (más lento). Ver README_ANALISIS.md",
                                idioma, lang, td)
                return lang, td
    raise EngineUnavailableError(f"No hay modelo de idioma {idioma} ni spa en {TESSDATA_PROYECTO} ni en {sistema}")


def _pool_ocr(hilos: int) -> ThreadPoolExecutor:
    global _pool, _pool_size
    with _pool_lock:
        if _pool is None or _pool_size != hilos:
            if _pool is not None:
                _pool.shutdown(wait=False)
            _pool = ThreadPoolExecutor(max_workers=hilos, thread_name_prefix="ocr")
            _pool_size = hilos
        return _pool


def _ocr_imagen(img: Path, lang: str, tessdata: Path) -> str:
    env = {**os.environ, "OMP_THREAD_LIMIT": "1", "TESSDATA_PREFIX": str(tessdata)}
    r = subprocess.run([tesseract_cmd(), str(img), "stdout", "-l", lang, "--oem", "1", "--psm", "3"],
                       capture_output=True, env=env, timeout=180, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "ignore").strip()[:300] or f"tesseract salió con {r.returncode}")
    return r.stdout.decode("utf-8", "ignore").strip()


def _guardar_pgm_imagen(path: Path, destino: Path) -> None:
    import cv2

    gray = cv2.cvtColor(load_image_file(path), cv2.COLOR_BGR2GRAY)
    ok, buf = cv2.imencode(".pgm", gray)
    if not ok:
        raise RuntimeError("No se pudo convertir la imagen")
    buf.tofile(str(destino))


# ---------------------------------------------------------------------------------------
# OCR de un documento -> (meta, txt) con el mismo formato que ocr_pipeline.pipeline
# ---------------------------------------------------------------------------------------
def _ocr_crudo(path: Path, nombre: str, sha: str, aj: Ajustes) -> tuple[dict, str]:
    t0 = time.perf_counter()
    lang, tessdata = resolver_idioma(aj.ocr_idioma)
    meta: dict = {
        "source_file": nombre, "source_path": str(path), "doc_type": "", "file_type": path.suffix.lower().lstrip("."),
        "sha256": sha, "size_bytes": path.stat().st_size, "num_pages": 0, "engine": f"tesseract:{lang}",
        "dpi": aj.ocr_dpi, "preprocess": [], "pages": [], "methods_count": {}, "avg_confidence": None,
        "text_quality": None, "total_chars": 0, "processing_time_s": None, "status": None, "duplicate_of": None,
        "errors": [], "processed_at": datetime.now().isoformat(timespec="seconds"), "pipeline_version": "analisis-1.0",
    }
    pool = _pool_ocr(aj.hilos_ocr)
    ext = path.suffix.lower()
    textos: dict[int, str | Future] = {}
    with tempfile.TemporaryDirectory(prefix="ocr3b_") as tmp:
        if ext in IMAGE_EXTENSIONS:
            meta["num_pages"] = 1
            destino = Path(tmp) / "p0001.pgm"
            _guardar_pgm_imagen(path, destino)
            textos[1] = pool.submit(_ocr_imagen, destino, lang, tessdata)
        elif ext in PDF_EXTENSIONS:
            with _render_lock:
                doc = fitz.open(path)
                if doc.needs_pass and not doc.authenticate(""):
                    raise RuntimeError("PDF protegido con contraseña")
                meta["num_pages"] = doc.page_count
            for i in range(meta["num_pages"]):
                try:
                    with _render_lock:
                        page = doc[i]
                        nativo = page.get_text("text") or ""
                        if useful_chars(nativo) >= 50:      # misma regla que el pipeline del equipo
                            textos[i + 1] = nativo.strip()
                            continue
                        destino = Path(tmp) / f"p{i + 1:04d}.pgm"
                        page.get_pixmap(dpi=aj.ocr_dpi, colorspace=fitz.csGRAY, alpha=False).save(str(destino))
                    textos[i + 1] = pool.submit(_ocr_imagen, destino, lang, tessdata)
                except Exception as e:  # noqa: BLE001 - una página dañada no tumba el documento
                    fallo: Future = Future()
                    fallo.set_exception(e)
                    textos[i + 1] = fallo
            with _render_lock:
                doc.close()
        else:
            raise ValueError(f"Extensión no soportada: {ext}")

        secciones = []
        for n in range(1, meta["num_pages"] + 1):
            v = textos[n]
            pagina = {"page": n, "method": "native" if isinstance(v, str) else "ocr:tesseract",
                      "engine": None if isinstance(v, str) else "tesseract", "chars": 0, "confidence": None,
                      "time_s": None, "error": None}
            try:
                texto = v if isinstance(v, str) else v.result()
            except Exception as e:  # noqa: BLE001 - una página mala no tumba el documento
                texto = ""
                pagina["error"] = f"{type(e).__name__}: {e}"
                meta["errors"].append(f"Página {n}: {pagina['error']}")
            pagina["chars"] = len(texto)
            q = text_quality(texto) if texto else None
            pagina["text_quality"] = round(q, 4) if q is not None else None
            meta["pages"].append(pagina)
            cuerpo = texto if not pagina["error"] else f"[ERROR EN PÁGINA: {pagina['error']}]"
            secciones.append(page_header(n, meta["num_pages"], pagina["method"] or "error", None) + "\n" + cuerpo)

    meta["methods_count"] = dict(Counter(p["method"] or "error" for p in meta["pages"]))
    meta["total_chars"] = sum(p["chars"] for p in meta["pages"])
    qp = [p for p in meta["pages"] if p.get("text_quality") is not None and p["chars"]]
    if qp:
        meta["text_quality"] = round(sum(p["text_quality"] * p["chars"] for p in qp) / sum(p["chars"] for p in qp), 4)
    meta["processing_time_s"] = round(time.perf_counter() - t0, 2)
    meta["status"] = compute_status(meta, PipelineConfig())
    txt = (f"# Fuente: {nombre}\n# Tipo: \n# Páginas: {meta['num_pages']}\n# SHA-256: {sha}\n\n"
           + "\n\n".join(secciones) + "\n")
    return meta, txt


def _clave_cache(sha: str, aj: Ajustes) -> str:
    return f"{sha[:24]}_{aj.ocr_idioma}_{aj.ocr_dpi}"


def ocr_documento(ruta: str | Path, nombre: str | None = None, tipo_declarado: str | None = None,
                  aj: Ajustes | None = None) -> tuple[dict, dict]:
    """OCR + campos por reglas de UN archivo.

    Devuelve (documento, info): `documento` cumple el modelo Documento del equipo;
    `info` = {"ocr_s": segundos, "cache": bool}.
    """
    aj = aj or Ajustes.desde_entorno()
    path = Path(ruta)
    nombre = nombre or path.name
    t0 = time.perf_counter()
    sha = sha256_file(path)
    clave = _clave_cache(sha, aj)
    cache = False
    if aj.ocr_cache and clave in _cache_mem:
        meta, txt = _cache_mem[clave]
        cache = True
    elif aj.ocr_cache and (CACHE_DIR / f"{clave}.json").is_file():
        d = json.loads((CACHE_DIR / f"{clave}.json").read_text(encoding="utf-8"))
        meta, txt = d["meta"], d["txt"]
        _cache_mem[clave] = (meta, txt)
        cache = True
    else:
        meta, txt = _ocr_crudo(path, nombre, sha, aj)
        if meta["status"] != "error":
            _cache_mem[clave] = (meta, txt)
            if aj.ocr_cache:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (CACHE_DIR / f"{clave}.json").write_text(json.dumps({"meta": meta, "txt": txt}, ensure_ascii=False),
                                                       encoding="utf-8")
    meta = {**meta, "source_file": nombre, "source_path": str(path)}
    tipo = canonical_tipo(tipo_declarado)
    documento = enriquecer_documento(build_document(meta, txt, tipo_declarado=tipo), tipo)
    return documento, {"ocr_s": round(time.perf_counter() - t0, 2), "cache": cache}


def precalentar_ocr(aj: Ajustes) -> None:
    """Carga el léxico de calidad y valida Tesseract antes del primer análisis."""
    resolver_idioma(aj.ocr_idioma)
    load_lexicon()
    _pool_ocr(aj.hilos_ocr)
