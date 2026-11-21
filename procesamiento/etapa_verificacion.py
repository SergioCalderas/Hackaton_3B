"""Validación cruzada del expediente (VC-01…VC-07). Adaptador delgado sobre ocr_pipeline.

No corre OCR: toma los campos que la Fase 2 dejó guardados para cada documento
(filtro_resultados.detalle -> 'extraccion' -> 'documento', o el resultado en memoria) y llama a
ocr_pipeline.servicio.verificar_expediente. Sus hallazgos se convierten en observaciones con el
mismo formato que las de la Fase 1 (observaciones.py), así el semáforo determinista de
dictamen.py y el front las usan sin cambios.

Regla de severidad (documentada en CLAUDE.md):
  ClaveCatastral / CuentaPredial no coinciden ...... VC-05  CRITICA  -> ROJO
  Propietario no coincide .......................... VC-02  CRITICA  -> ROJO
  SuperficieTerreno no coincide .................... VC-03  ALTA     -> AMARILLO
  NumeroOficial no coincide ........................ VC-04  ALTA     -> AMARILLO
  Calle / Colonia / Municipio / Estado / CP / Lote / Manzana  VC-01  MEDIA  -> AMARILLO
  PuntajeMatch < 0.55 o documento de otro inmueble . VC-06  ALTA     -> AMARILLO
  Dos prediales del mismo ejercicio fiscal ......... VC-07  MEDIA    -> AMARILLO
  Documento aprobado sin extracción ................ SIN-EXTRAER MEDIA -> AMARILLO
Los faltantes ya los cubre la Fase 1 (FALTA-ARCHIVO, bloquea -> GRIS).
"""
from __future__ import annotations

VERSION_VERIFICACION = "verificacion v0.1"

# tabla de la BD -> nombre legible (mismo que observaciones.NOMBRE_TABLA)
NOMBRE_TABLA = {"escrituras": "Escrituras", "predial": "Predial", "suelo": "Uso de Suelo",
                "aliniamiento": "Alineamiento y Número Oficial"}
NOMBRE_TIPO = {"Escritura": "Escrituras", "Predial": "Predial", "UsoDeSuelo": "Uso de Suelo",
               "Alineamiento": "Alineamiento y Número Oficial"}

REGLA_CAMPO = {
    "ClaveCatastral": ("VC-05", "CRITICA", "Clave catastral"),
    "CuentaPredial": ("VC-05", "CRITICA", "Cuenta predial"),
    "Propietario": ("VC-02", "CRITICA", "Propietario o titular"),
    "SuperficieTerreno": ("VC-03", "ALTA", "Superficie del terreno"),
    "NumeroOficial": ("VC-04", "ALTA", "Número oficial"),
    "Calle": ("VC-01", "MEDIA", "Calle"),
    "Colonia": ("VC-01", "MEDIA", "Colonia"),
    "Municipio": ("VC-01", "MEDIA", "Municipio"),
    "Estado": ("VC-01", "MEDIA", "Estado"),
    "CodigoPostal": ("VC-01", "MEDIA", "Código postal"),
    "Lote": ("VC-01", "MEDIA", "Lote"),
    "Manzana": ("VC-01", "MEDIA", "Manzana"),
    "EjercicioFiscal": ("VC-07", "MEDIA", "Ejercicio fiscal del predial"),
}
UMBRAL_PUNTAJE = 0.55


def _extraccion(doc_op: dict) -> dict | None:
    """La extracción guardada de un documento de la operación (o None)."""
    return ((doc_op or {}).get("filtro") or {}).get("extraccion")


def documentos_extraidos(op: dict) -> tuple[list[dict], list[str]]:
    """([Documento de ocr_pipeline], [tablas aprobadas sin extracción])."""
    docs, sin_extraer = [], []
    for tabla, d in op.get("documentos", {}).items():
        filtro = d.get("filtro") or {}
        if filtro.get("estado") != "APROBADO":
            continue  # la Fase 1 ya genera su observación (rechazo, revisión o falta)
        ext = _extraccion(d) or {}
        if ext.get("documento"):
            docs.append(ext["documento"])
        else:
            sin_extraer.append(tabla)
    return docs, sin_extraer


def verificar(op: dict) -> dict | None:
    """Expediente de ocr_pipeline (modo compacto) o None si hay menos de 2 documentos extraídos."""
    docs, _ = documentos_extraidos(op)
    if len(docs) < 2:
        return None
    from ocr_pipeline.servicio import verificar_expediente
    return verificar_expediente(docs, modo="compacto")


def _valores_texto(x: dict) -> str:
    return " · ".join(f"{NOMBRE_TIPO.get(v['TipoDocumento'], v['TipoDocumento'] or '?')}: «{v['Valor']}» (pág. {v['Pagina']})"
                      for v in x["Valores"])


def resumen(op: dict) -> dict:
    """Resumen para el dictamen: si hubo validación cruzada, puntaje y campos que coinciden."""
    exp = verificar(op)
    if exp is None:
        return {"realizada": False}
    return {"realizada": True, "version": VERSION_VERIFICACION, "puntaje": exp["PuntajeMatch"],
            "nivel": exp["NivelMatch"], "coinciden": exp["CamposCoinciden"],
            "no_coinciden": [x["Campo"] for x in exp["CamposNoCoinciden"]],
            "documentos": len(exp["Documentos"])}


def observaciones(op: dict) -> list[dict]:
    """Observaciones de validación cruzada con el formato de observaciones.py."""
    salida: list[dict] = []

    def agregar(codigo, regla, severidad, texto, evidencia=None):
        o = {"id": f"vc-{len(salida) + 1}", "tabla": "expediente", "documento": "Expediente",
             "etapa": "validacion_cruzada", "codigo": codigo, "regla": regla, "severidad": severidad,
             "bloquea": False, "texto": texto}
        if evidencia:
            o["evidencia"] = evidencia
        salida.append(o)

    _, sin_extraer = documentos_extraidos(op)
    for tabla in sin_extraer:
        agregar("SIN-EXTRAER", "RF-03", "MEDIA",
                f"{NOMBRE_TABLA.get(tabla, tabla)}: aprobado por el filtro pero sin extracción de campos; "
                "vuelve a verificarlo para incluirlo en la validación cruzada.")

    exp = verificar(op)
    if exp is None:
        return salida

    for x in exp["CamposNoCoinciden"]:
        regla, sev, nombre = REGLA_CAMPO.get(x["Campo"], ("VC-01", "MEDIA", x["Campo"]))
        agregar(f"VC-{x['Campo'].upper()}", regla, sev,
                f"{nombre} no coincide entre documentos ({x['Detalle']}): {_valores_texto(x)}.",
                evidencia=[{"documento": v["Documento"], "tipo": v["TipoDocumento"], "valor": v["Valor"],
                            "pagina": v["Pagina"]} for v in x["Valores"]])

    otro = [a for a in exp["Alertas"] if "otro inmueble" in a]
    for a in otro:
        agregar("VC-OTRO-INMUEBLE", "VC-06", "ALTA", a)
    if exp["PuntajeMatch"] is not None and exp["PuntajeMatch"] < UMBRAL_PUNTAJE and not otro:
        agregar("VC-PUNTAJE-BAJO", "VC-06", "ALTA",
                f"Los documentos se parecen poco entre sí (puntaje {exp['PuntajeMatch']:.2f} < {UMBRAL_PUNTAJE}): "
                "podrían ser de inmuebles distintos.")
    return salida
