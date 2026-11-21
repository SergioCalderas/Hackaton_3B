"""Fase 2: extracción de campos. Adaptador delgado sobre ocr_pipeline (módulo de Yax).

Llega aquí solo un documento APROBADO por la Fase 1 (el pipeline se detiene antes si no).
El OCR es el paralelo de analisis/ocr_rapido.py (texto.ocr_completo; motor serial de respaldo) y
la extracción de campos la de ocr_pipeline: OCR (Tesseract),
campos con evidencia, detección de tipo y calidad del texto. Aquí solo se traduce la entrada y
la salida al contrato del pipeline. Ver ocr_pipeline/README.md.

Salida (ResultadoEtapa.datos):
  estado            OK | SIN_CAMPOS | ERROR
  tipo              tipo del pipeline (escritura | predial | alineamiento | uso_suelo)
  campos            {campo: {valor, valor_normalizado, confianza, evidencia {pagina, fragmento, bbox, regla}}}
  documento         Documento de ocr_pipeline en modo compacto (sin texto completo): lo usa la
                    validación cruzada (etapa_verificacion.py) y queda guardado en
                    filtro_resultados.detalle -> 'extraccion' -> 'documento'
El texto completo por página NO va a la BD: se guarda en la caché en disco de texto.py
(la usa la sección "Texto extraído del documento" del caso).
  calidad_texto, version_esquema, segundos, mensaje
"""
from __future__ import annotations

import time
from pathlib import Path

# tipo del pipeline -> tipo de ocr_pipeline
TIPO_OCR = {"escritura": "Escritura", "predial": "Predial", "alineamiento": "Alineamiento", "uso_suelo": "UsoDeSuelo"}
TIPO_PIPELINE = {v: k for k, v in TIPO_OCR.items()}


def leer_paginas(doc, paginas: list[int] | None = None) -> list[dict]:
    """[{numero, texto, lineas: [(texto, confianza, caja[[x,y]x4])]}] usando la caché OCR de la Fase 1.
    Las coordenadas de las cajas están en píxeles del render (lado mayor = 2000 px).
    (No lo usa la extracción actual; se conserva para etapas futuras.)"""
    from .etapa_calidad import F
    from .pipeline import CANDADO_OCR, DIR_CACHE_OCR

    with CANDADO_OCR:
        pags = F.leer_documento(Path(doc.ruta), DIR_CACHE_OCR, paginas)
    return [{"numero": p.numero, "origen": p.origen, "texto": p.texto, "lineas": p.lineas} for p in pags]


def nombre_trazable(doc) -> str:
    """Identificador estable del documento dentro del expediente: '<tabla>/<archivo>' si viene de la BD."""
    return f"{doc.tabla}/{doc.nombre}" if doc.tabla else doc.nombre


def _campo_equipo(c: dict, calidad: float | None) -> dict:
    """Campo de ocr_pipeline -> formato de campo del equipo (CLAUDE.md, Fase 2)."""
    return {
        "valor": c["Valor"],
        "valor_normalizado": c["Normalizado"],
        "confianza": calidad,  # aún no hay confianza por campo: se usa la calidad del texto de su página
        "evidencia": {"pagina": c["Pagina"], "fragmento": c["Evidencia"], "bbox": None, "regla": c["Regla"]},
    }


def ejecutar(doc):
    import hashlib

    from ocr_pipeline.matching import aplicar_modo
    from ocr_pipeline.schemas import VERSION_ESQUEMA
    from . import texto
    from .pipeline import ResultadoEtapa

    t0 = time.time()
    calidad = doc.resultados.get("calidad", {})
    tipo = doc.tipo_declarado or calidad.get("tipo_detectado")
    try:
        # OCR paralelo de analisis/ (texto.ocr_completo); cae al motor serial si no está disponible
        completo = texto.ocr_completo(Path(doc.ruta), TIPO_OCR.get(tipo), nombre_trazable(doc))
        # El texto por página va a la caché en disco (texto.py), no a la BD; a la BD va el modo compacto.
        try:
            texto.guardar_cache(hashlib.sha256(Path(doc.ruta).read_bytes()).hexdigest(), completo)
        except OSError as e:
            print(f"[procesamiento] No se guardó la caché de texto: {e}", flush=True)
        d = aplicar_modo(completo, "compacto", es_expediente=False)
    except Exception as e:  # noqa: BLE001 — un fallo aquí no debe tumbar el servidor
        return ResultadoEtapa(datos={"estado": "ERROR", "tipo": tipo, "campos": {}, "documento": None,
                                     "mensaje": f"No se pudo extraer: {e.__class__.__name__}: {e}",
                                     "segundos": round(time.time() - t0, 1)}, continuar=False)

    calidad_pag = {p["Numero"]: p["CalidadTexto"] for p in d["Paginas"]}
    campos = {k: _campo_equipo(c, calidad_pag.get(c["Pagina"], d["CalidadTexto"]))
              for k, c in d["CamposExtraidos"].items()}
    estado = "OK" if campos else "SIN_CAMPOS"
    return ResultadoEtapa(
        datos={
            "estado": estado,
            "tipo": TIPO_PIPELINE.get(d["TipoDocumento"], tipo),
            "campos": campos,
            "calidad_texto": d["CalidadTexto"],
            "discrepancias": d["Discrepancias"],
            "documento": d,
            "version_esquema": VERSION_ESQUEMA,
            "segundos": round(time.time() - t0, 1),
            "mensaje": (f"{len(campos)} campos extraídos." if campos
                        else "No se encontraron campos útiles (clave, dirección, propietario, superficie)."),
        },
        continuar=True,
    )
