"""Agentes por documento: clasificador y extractores especializados (uno por tipo).

Cada extractor:
  1. arma el contexto (páginas relevantes) y pide al LLM un JSON con el esquema de su tipo;
  2. localiza cada valor en el texto OCR -> evidencia (página + cita literal);
  3. lo contrasta con el extractor por reglas del equipo (regex): si ambos coinciden, la confianza
     sube; si el LLM no encontró un dato que las reglas sí, se usa el de reglas (fuente="reglas").
Si el LLM falla (servidor caído, timeout), el documento queda solo con los datos de reglas.
"""
from __future__ import annotations

import logging
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from ocr_pipeline.normalize import parse_date

from . import prompts
from .comparar import MAPA_REGLAS, coincide
from .config import Ajustes
from .contexto import limpiar_texto, preparar_contexto
from .esquemas import ESQUEMA_EXTRACCION, ETIQUETAS, TIPOS, CampoExtraido, Clasificacion, DocumentoAnalizado
from .evidencia import TextoDocumento, evidencia_de_campo_reglas, localizar
from .llm import llm_estructurado

log = logging.getLogger("analisis")

CAMPOS_SIN_EVIDENCIA = {"compatible_comercial", "cita_compatibilidad"}


# ---------------------------------------------------------------------------------------
# Clasificador
# ---------------------------------------------------------------------------------------
def clasificar(doc: dict, aj: Ajustes) -> tuple[str | None, str]:
    """(tipo, método). Usa el tipo detectado por palabras clave (ocr_pipeline.fields.detectar_tipo);
    si no hay detección ni tipo declarado, pregunta al LLM con la primera página."""
    detectado, declarado = doc.get("TipoDetectado"), doc.get("TipoDeclarado")
    if detectado:
        return detectado, "palabras clave" + (" (difiere del declarado)" if declarado and declarado != detectado else "")
    if declarado:
        return declarado, "declarado (contenido no concluyente)"
    texto = limpiar_texto(" ".join((p.get("Texto") or "") for p in doc.get("Paginas", [])[:2]))[:2500]
    if len(texto) < 80:
        return None, "sin texto legible"
    try:
        r = llm_estructurado(aj, Clasificacion, "clasificacion").invoke(
            [SystemMessage(prompts.CLASIFICADOR), HumanMessage(f"Archivo: {doc.get('NombreArchivo')}\n\n{texto}")])
        return (r.tipo if r.tipo in TIPOS else None), "LLM"
    except Exception as e:  # noqa: BLE001
        log.warning("Clasificador LLM falló: %s", e)
        return None, f"LLM no disponible ({type(e).__name__})"


# ---------------------------------------------------------------------------------------
# Extractores
# ---------------------------------------------------------------------------------------
def solo_calle(v: str) -> str:
    """'Calle Fresno No. 28, Lote 14, Col. La Loma' -> 'Calle Fresno' ; 'FRESNO 28' -> 'FRESNO'."""
    t = re.split(r",|;|\bCOL(?:ONIA)?\b\.?|\bLOTE\b|\bLT\b\.?|\bMZ(?:A|NA)?\b\.?|\bMANZANA\b", v, maxsplit=1,
                 flags=re.I)[0]
    t = re.sub(r"\s+(?:N[OoÚú]\.?|NUM(?:ERO)?\.?|#)\s*\S+.*$", "", t, flags=re.I)
    t = re.sub(r"\s+(?:S/N|SN|\d+[A-Z]?)\s*$", "", t, flags=re.I)
    return t.strip(" .,;:") or v


def _limpiar_valor(campo: str, v):
    if isinstance(v, str):
        v = re.sub(r"\s+", " ", v).strip(" .,;:")
        if not v or v.lower() in ("null", "none", "n/a", "no aplica", "no especificado", "desconocido"):
            return None
        if campo == "calle":
            v = solo_calle(v)
        if campo.startswith("fecha") and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return parse_date(v) or v
    if isinstance(v, list):
        v = [x for x in (_limpiar_valor(campo, x) for x in v) if x]
        return v or None
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v <= 0 and campo != "ejercicio_fiscal":
        return None
    return v


def _valor_reglas(doc: dict, campo_equipo: str):
    c = (doc.get("CamposExtraidos") or {}).get(campo_equipo)
    if not c:
        return None
    n = c.get("Normalizado")
    return n if campo_equipo in ("EjercicioFiscal", "SuperficieTerreno", "SuperficieConstruccion") else c.get("Valor")


def construir_campos(doc: dict, datos: dict, paginas_llm: list[int]) -> dict[str, CampoExtraido]:
    """Une la salida del LLM con el extractor por reglas y calcula la evidencia de cada campo."""
    texto = TextoDocumento.desde_documento(doc)
    campos: dict[str, CampoExtraido] = {}
    for campo, valor in datos.items():
        valor = _limpiar_valor(campo, valor)
        if valor is None:
            continue
        ev = None
        if campo == "compatible_comercial":
            # la cita del LLM; si la parafraseó, la línea del uso o del giro autorizado
            cita = _limpiar_valor("cita", datos.get("cita_compatibilidad"))
            ev = localizar(texto, "cita", cita, paginas_preferidas=paginas_llm, umbral=80) if cita else None
            for alterno in ("giro", "uso_autorizado"):
                if (ev is None or not ev.verificada) and datos.get(alterno):
                    ev = localizar(texto, alterno, datos[alterno], paginas_preferidas=paginas_llm)
        elif campo == "restricciones":
            ev = localizar(texto, campo, valor[0], paginas_preferidas=paginas_llm, umbral=75)
        elif campo not in CAMPOS_SIN_EVIDENCIA:
            ev = localizar(texto, campo, valor, extras={"calle": datos.get("calle")}, paginas_preferidas=paginas_llm)
        valor_reglas, coinc, fuente = None, None, "llm"
        if campo in MAPA_REGLAS:
            campo_eq, tipo_cmp = MAPA_REGLAS[campo]
            valor_reglas = _valor_reglas(doc, campo_eq)
            coinc = coincide(tipo_cmp, valor, valor_reglas)
            if coinc:
                fuente = "llm+reglas"
                if ev is not None and not ev.verificada:
                    ev = evidencia_de_campo_reglas(doc, campo_eq) or ev
        campos[campo] = CampoExtraido(campo=campo, etiqueta=ETIQUETAS.get(campo, campo), valor=valor, evidencia=ev,
                                      fuente=fuente, valor_reglas=valor_reglas, coincide_reglas=coinc)
    # Datos que el LLM no reportó pero el extractor por reglas sí
    for campo, (campo_eq, _tipo) in MAPA_REGLAS.items():
        if campo in campos or campo not in datos:
            continue
        v = _valor_reglas(doc, campo_eq)
        if v in (None, "", []):
            continue
        if campo == "ejercicio_fiscal" and isinstance(v, list):
            v = max(int(x) for x in v)
        campos[campo] = CampoExtraido(campo=campo, etiqueta=ETIQUETAS.get(campo, campo), valor=v,
                                      evidencia=evidencia_de_campo_reglas(doc, campo_eq), fuente="reglas",
                                      valor_reglas=v, coincide_reglas=None)
    return campos


def extraer(doc: dict, tipo: str, aj: Ajustes) -> DocumentoAnalizado:
    """Agente extractor especializado para `tipo` (Escritura | Predial | Alineamiento | UsoDeSuelo)."""
    esquema = ESQUEMA_EXTRACCION[tipo]
    contexto, paginas = preparar_contexto(doc, tipo, aj.max_chars_doc)
    t0 = time.perf_counter()
    error = None
    datos: dict = {}
    if contexto:
        try:
            r = llm_estructurado(aj, esquema, "extraccion").invoke([
                SystemMessage(prompts.prompt_extractor(tipo, aj.uso_requerido)),
                HumanMessage(f"Archivo: {doc.get('NombreArchivo')}\n\n{contexto}"),
            ])
            datos = r.model_dump()
        except Exception as e:  # noqa: BLE001 - se degrada a solo reglas
            error = f"{type(e).__name__}: {str(e)[:200]}"
            log.warning("Extractor %s falló en %s: %s", tipo, doc.get("NombreArchivo"), error)
    else:
        error = "Sin texto legible para el LLM"
    if not datos:  # degradado: solo reglas
        datos = {k: None for k in esquema.model_fields}
    t_llm = round(time.perf_counter() - t0, 2)
    return DocumentoAnalizado(
        nombre_archivo=doc.get("NombreArchivo", ""), ruta_archivo=doc.get("RutaArchivo", ""), tipo=tipo,
        tipo_declarado=doc.get("TipoDeclarado"), tipo_detectado=doc.get("TipoDetectado"),
        num_paginas=doc.get("NumPaginas", 0), calidad_texto=doc.get("CalidadTexto"), estado_ocr=doc.get("Estado", "ok"),
        paginas_enviadas_llm=paginas, campos=construir_campos(doc, datos, paginas), error_llm=error,
        tiempos={"llm_s": t_llm},
    )


def documento_sin_tipo(doc: dict, motivo: str) -> DocumentoAnalizado:
    return DocumentoAnalizado(
        nombre_archivo=doc.get("NombreArchivo", ""), ruta_archivo=doc.get("RutaArchivo", ""), tipo=None,
        tipo_declarado=doc.get("TipoDeclarado"), tipo_detectado=doc.get("TipoDetectado"),
        num_paginas=doc.get("NumPaginas", 0), calidad_texto=doc.get("CalidadTexto"),
        estado_ocr=doc.get("Estado", "ok"), error_llm=motivo)
