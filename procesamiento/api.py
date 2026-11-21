"""Endpoints del pipeline. server/app.py los registra (Vite hace proxy de /api al puerto 5000).

  GET  /api/procesamiento/salud
  GET  /api/operaciones                              lista + último resultado guardado por documento (sin OCR)
  GET  /api/operaciones/<id>                         una operación (también responde en GET .../verificar)
  POST /api/documentos/<tabla>/<id>/verificar        tabla: escrituras | predial | suelo | aliniamiento
  POST /api/operaciones/<id>/verificar               los 4 documentos de operacion_realizada + completitud
  POST /api/documentos/verificar-archivo             multipart (campo "archivo", opcional "tipo"); solo pruebas

Parámetro opcional ?hasta=calidad para correr solo la Fase 1.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from . import fuentes
from .etapa_calidad import TIPOS, VERSION_REGLAS
from .pipeline import ETAPAS, procesar_bytes

bp = Blueprint("procesamiento", __name__, url_prefix="/api")


def _hasta():
    h = request.args.get("hasta")
    return h if h in {n for n, _ in ETAPAS} else None


def _procesar_bd(tabla: str, id_: int) -> dict:
    a = fuentes.desde_bd(tabla, id_)
    r = procesar_bytes(a.contenido, a.nombre, a.tipo, a.tabla, a.id, hasta=_hasta())
    fuentes.guardar_resultado(r)
    return r


@bp.errorhandler(fuentes.FuenteError)
def _error_fuente(e: fuentes.FuenteError):
    return jsonify(error=str(e)), e.http


@bp.get("/procesamiento/salud")
def salud():
    return jsonify(ok=True, etapas=[n for n, _ in ETAPAS], version_reglas=VERSION_REGLAS,
                   tablas=sorted(fuentes.TABLAS))


@bp.post("/documentos/<tabla>/<int:id_>/verificar")
def verificar_documento(tabla: str, id_: int):
    return jsonify(_procesar_bd(tabla, id_))


@bp.post("/operaciones/<int:operacion_id>/verificar")
def verificar_operacion(operacion_id: int):
    ids = fuentes.ids_de_operacion(operacion_id)
    documentos, faltantes = {}, []
    for tabla, id_ in ids.items():
        if id_ is None:
            faltantes.append(tabla)
            continue
        try:
            documentos[tabla] = _procesar_bd(tabla, id_)
        except fuentes.FuenteError as e:
            documentos[tabla] = {"tabla": tabla, "id": id_, "error": str(e)}
            faltantes.append(tabla)
    aprobados = [t for t, d in documentos.items() if d.get("calidad", {}).get("estado") == "APROBADO"]
    volver = [t for t, d in documentos.items() if d.get("calidad", {}).get("estado") == "VOLVER_A_SUBIR"]
    # RF-01: con los 4 aprobados -> "En revisión"; si no -> "No validado"
    return jsonify(
        operacion_id=operacion_id,
        expediente="EN_REVISION" if len(aprobados) == 4 else "NO_VALIDADO",
        aprobados=aprobados, volver_a_subir=volver, faltantes=faltantes,
        documentos=documentos,
    )


@bp.get("/operaciones")
def listar_operaciones():
    """Operaciones con el último resultado guardado del filtro (rápido, no corre OCR)."""
    return jsonify(fuentes.resumen_operaciones())


@bp.get("/operaciones/<int:operacion_id>")
@bp.get("/operaciones/<int:operacion_id>/verificar")
def ver_operacion(operacion_id: int):
    """GET no vuelve a correr el filtro: devuelve lo último guardado.
    Para correrlo de nuevo: POST /api/operaciones/<id>/verificar."""
    datos = fuentes.resumen_operaciones(operacion_id)
    if not datos:
        return jsonify(error=f"No existe la operación {operacion_id}."), 404
    return jsonify({**datos[0], "nota": "Resultado guardado. Para volver a verificar usa POST en "
                                        f"/api/operaciones/{operacion_id}/verificar."})


@bp.post("/documentos/verificar-archivo")
def verificar_archivo():
    f = request.files.get("archivo")
    if not f or not f.filename:
        return jsonify(error="Falta el campo 'archivo'."), 400
    tipo = request.form.get("tipo")
    tipo = tipo if tipo in TIPOS else None
    return jsonify(procesar_bytes(f.read(), f.filename, tipo, hasta=_hasta()))
