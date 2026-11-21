"""Análisis multiagente con LLM (paquete analisis/) expuesto al servidor Flask del prototipo.

  POST /api/analisis          multipart: archivos=<file> (varios), tipos=<tipo> (opcional, uno por archivo)
                              tipos: escritura | predial | alineamiento | uso_suelo (o vacío = detectar)
                              -> ResultadoExpediente (estado, hallazgos con evidencia por página, datos, tiempos)
  POST /api/analisis/caso     JSON {documentos: [{ruta: "/docs/escrituras/caso-001.pdf", tipo: "escrituras"}],
                              forzar: false} -> ResultadoExpediente de los PDFs de un caso del front (public/).
                              Las evidencias traen documento=<ruta pública> para enlazar <ruta>#page=N.
                              El resultado se guarda en memoria por SHA-256 de los archivos (forzar=true lo repite).
  GET  /api/analisis/miniatura?ruta=/docs/...&pagina=N   vista previa JPEG de una página (hover del front)
  GET  /api/analisis/salud    proveedor y modelo configurados, estado de Ollama

El proveedor sale de LLM_PROVIDER=local|online en .env (ver .env.example y README_ANALISIS.md).
Complementa al pipeline de procesamiento/ (filtro de calidad + semáforo por operación en BD): este
endpoint analiza un expediente completo en < 60 s con OCR paralelo y extracción con LLM.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("analisis_llm", __name__, url_prefix="/api")

TIPOS = {"escritura": "Escritura", "escrituras": "Escritura", "predial": "Predial", "alineamiento": "Alineamiento",
         "aliniamiento": "Alineamiento", "numero_oficial": "Alineamiento", "uso_suelo": "UsoDeSuelo",
         "suelo": "UsoDeSuelo", "usodesuelo": "UsoDeSuelo"}
_resultados: OrderedDict[str, dict] = OrderedDict()     # análisis de casos ya hechos (por SHA-256)
_miniaturas: OrderedDict[tuple, bytes] = OrderedDict()
_candado_caso = threading.Lock()                         # un análisis a la vez: la GPU es una sola
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


@bp.post("/analisis/caso")
def analizar_caso():
    from analisis import ConfiguracionError, analizar_expediente
    from analisis.config import Ajustes

    from . import texto

    cuerpo = request.get_json(silent=True) or {}
    docs = cuerpo.get("documentos") or []
    if not docs:
        return jsonify(error="Envía 'documentos': [{ruta, tipo}] con los PDFs del caso."), 400
    try:
        entradas = []
        for d in docs:
            ruta = texto.ruta_publica(str(d.get("ruta") or ""))      # solo archivos de public/
            t = str(d.get("tipo") or "").strip().lower()
            entradas.append({"ruta": str(ruta), "nombre": "/" + ruta.relative_to(texto.DIR_PUBLICO).as_posix(),
                             "tipo": TIPOS.get(t)})
    except texto.TextoError as e:
        return jsonify(error=str(e)), e.http
    aj = Ajustes.desde_entorno()
    clave = hashlib.sha256("|".join(
        [hashlib.sha256(Path(e["ruta"]).read_bytes()).hexdigest() + str(e["tipo"]) for e in entradas]
        + [aj.proveedor, aj.modelo, aj.fecha_referencia.isoformat()]).encode()).hexdigest()
    if not cuerpo.get("forzar") and clave in _resultados:
        return jsonify({**_resultados[clave], "desde_cache": True})
    try:
        with _candado_caso:
            res = analizar_expediente(entradas, aj)
    except ConfiguracionError as e:
        return jsonify(error=str(e)), 503
    _resultados[clave] = res
    while len(_resultados) > 50:
        _resultados.popitem(last=False)
    return jsonify({**res, "desde_cache": False})


@bp.get("/analisis/miniatura")
def miniatura():
    import fitz

    from . import texto

    try:
        ruta = texto.ruta_publica(request.args.get("ruta", ""))
        pagina = max(1, int(request.args.get("pagina", "1")))
    except texto.TextoError as e:
        return jsonify(error=str(e)), e.http
    except ValueError:
        return jsonify(error="pagina debe ser un número"), 400
    clave = (str(ruta), pagina)
    if clave not in _miniaturas:
        from analisis.ocr_rapido import _render_lock   # PyMuPDF no es seguro entre hilos

        try:
            with _render_lock:
                if ruta.suffix.lower() == ".pdf":
                    with fitz.open(ruta) as doc:
                        pix = doc[min(pagina, doc.page_count) - 1].get_pixmap(dpi=50)
                else:
                    pix = fitz.Pixmap(str(ruta))
                _miniaturas[clave] = pix.tobytes("jpg", jpg_quality=70)
        except Exception as e:  # noqa: BLE001
            return jsonify(error=f"No se pudo generar la vista previa: {e}"), 422
        while len(_miniaturas) > 300:
            _miniaturas.popitem(last=False)
    return Response(_miniaturas[clave], mimetype="image/jpeg", headers={"Cache-Control": "max-age=3600"})
