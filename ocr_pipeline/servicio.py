"""API de Python para integrar el módulo en el sistema (front -> filtro -> ESTE MÓDULO -> LLM).

    from ocr_pipeline import procesar_documento, verificar_expediente

    doc = procesar_documento("boleta.pdf", tipo_declarado="Predial")
    exp = verificar_expediente([("escritura.pdf", "Escritura"), ("boleta.pdf", "Predial"),
                                ("alineamiento.pdf", "Alineamiento"), ("uso.pdf", "UsoDeSuelo")])

- El motor OCR se carga una sola vez por proceso y se reutiliza (thread-safe con un lock).
- Los resultados se cachean por SHA-256 del archivo: subir el mismo archivo dos veces no repite OCR.
- Las salidas cumplen los modelos Documento / Expediente de schemas.py (se validan antes de devolverse).
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

from .config import PipelineConfig
from .export import build_document
from .loaders import sha256_file
from .matching import MatchConfig, canonical_tipo, enriquecer_documento, verificar
from .pipeline import EngineProvider, process_document
from .schemas import VERSION_ESQUEMA, Documento, Expediente

log = logging.getLogger("ocr_pipeline")

_lock = threading.Lock()
_provider: EngineProvider | None = None
_cfg: PipelineConfig | None = None
_cache: OrderedDict[str, dict] = OrderedDict()
CACHE_MAX = 256


def configurar(cfg: PipelineConfig | None = None) -> None:
    """Cambia la configuración del OCR (motor, DPI...). Reinicia el motor y la caché."""
    global _provider, _cfg
    with _lock:
        _cfg = cfg or PipelineConfig()
        _provider = None
        _cache.clear()


def _get() -> tuple[PipelineConfig, EngineProvider]:
    global _provider, _cfg
    if _cfg is None:
        _cfg = PipelineConfig()
    if _provider is None:
        _provider = EngineProvider(_cfg)
    return _cfg, _provider


def precargar() -> str:
    """Carga el motor OCR por adelantado (útil al arrancar un servidor)."""
    with _lock:
        cfg, provider = _get()
        engine = provider.get(cfg.engine)
        return engine.name


def procesar_documento(ruta: str | Path, tipo_declarado: str | None = None,
                       nombre_original: str | None = None) -> dict:
    """OCR + extracción de campos de UN documento. Devuelve un dict con el formato `Documento`.

    tipo_declarado: "Predial" | "Alineamiento" | "Escritura" | "UsoDeSuelo" (acepta variantes como
    "uso de suelo"); si no se da, se usa el tipo detectado por contenido.
    nombre_original: nombre con el que el usuario subió el archivo (para NombreArchivo/RutaArchivo).
    """
    path = Path(ruta)
    if not path.is_file():
        raise FileNotFoundError(path)
    nombre = nombre_original or path.name
    tipo = canonical_tipo(tipo_declarado)
    sha = sha256_file(path)

    with _lock:
        cached = _cache.get(sha)
        if cached is None:
            cfg, provider = _get()
            meta, txt = process_document(path, Path(nombre), sha, cfg, provider)
            cached = {"meta": meta, "txt": txt}
            _cache[sha] = cached
            while len(_cache) > CACHE_MAX:
                _cache.popitem(last=False)
        else:
            _cache.move_to_end(sha)

    meta = {**cached["meta"], "source_file": nombre, "doc_type": ""}
    doc = build_document(meta, cached["txt"], tipo_declarado=tipo)
    doc = enriquecer_documento(doc, tipo)
    Documento.model_validate(doc)
    return doc


def verificar_expediente(documentos: Iterable[tuple[str | Path, str | None] | str | Path | dict],
                         cfg: MatchConfig | None = None) -> dict:
    """Verifica la coherencia de los documentos de UN inmueble.

    documentos: lista de (ruta, tipo_declarado), rutas sueltas, o dicts ya devueltos por
    procesar_documento. Devuelve un dict con el formato `Expediente` (CamposCoinciden,
    CamposNoCoinciden, DocumentosFaltantes, PuntajeMatch, Alertas, Documentos...).
    """
    docs = []
    for item in documentos:
        if isinstance(item, dict):
            docs.append(item)
        elif isinstance(item, (tuple, list)):
            ruta, tipo = (list(item) + [None])[:2]
            docs.append(procesar_documento(ruta, tipo))
        else:
            docs.append(procesar_documento(item))
    if not docs:
        raise ValueError("Se requiere al menos un documento")
    exp = {"VersionEsquema": VERSION_ESQUEMA, **verificar(docs, cfg)}
    Expediente.model_validate(exp)
    return exp
