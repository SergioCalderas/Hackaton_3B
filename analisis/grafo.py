"""Arquitectura multiagente con LangGraph.

    START ──Send(por archivo)──► [subgrafo "analizar_documento"]  (todos los archivos EN PARALELO)
                                   agente_ocr ─► agente_clasificador ─┬─► extractor_escritura
                                                                      ├─► extractor_predial
                                                                      ├─► extractor_alineamiento
                                                                      ├─► extractor_uso_suelo
                                                                      └─► sin_tipo
                                 ──► validador_cruzado ──► dictaminador ──► END

Por qué cumple el minuto: el OCR (CPU, todos los núcleos) de los documentos largos corre mientras
el LLM (GPU) ya extrae los documentos cortos; el validador es determinista (milisegundos).
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
import operator
import time
from pathlib import Path
from typing import Annotated, Callable, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ocr_pipeline.normalize import digits_only

from . import agentes, reglas
from .config import Ajustes
from .dictamen import dictaminar
from .esquemas import NOMBRE_TIPO, TIPOS, DocumentoAnalizado, Hallazgo, ResultadoExpediente
from .llm import estado_ollama, precalentar
from . import calidad as calidad_mod
from .ocr_rapido import ocr_documento
from ocr_pipeline.matching import canonical_tipo

log = logging.getLogger("analisis")

EXTRACTORES = {"Escritura": "extractor_escritura", "Predial": "extractor_predial",
               "Alineamiento": "extractor_alineamiento", "UsoDeSuelo": "extractor_uso_suelo"}


def _aj(config: RunnableConfig) -> Ajustes:
    return config["configurable"]["ajustes"]


# ---------------------------------------------------------------------------------------
# Subgrafo por documento
# ---------------------------------------------------------------------------------------
def _acumular(previo, nuevo) -> list:
    return (previo or []) + (nuevo if isinstance(nuevo, list) else [nuevo])


class EstadoDocumento(TypedDict, total=False):
    archivo: dict                   # {"ruta", "nombre", "tipo"}
    doc_ocr: dict                   # Documento (contrato de ocr_pipeline) con campos por reglas
    info_ocr: dict
    calidad_futuro: object          # Future con el resultado de la Fase 1 (filtro de calidad del equipo)
    tipo: Optional[str]
    clasificacion: str
    evento: Annotated[list, _acumular]  # progreso (no sale del subgrafo); calidad y OCR escriben a la vez
    documentos: Annotated[list[dict], operator.add]   # salida hacia el grafo principal


def _documento_con_error(a: dict, error: Exception) -> dict:
    """Documento vacío con Estado=error: el expediente sigue y el validador lo reporta como ilegible."""
    from ocr_pipeline.export import build_document
    from ocr_pipeline.matching import canonical_tipo, enriquecer_documento

    meta = {"source_file": a["nombre"], "status": "error", "num_pages": 0, "pages": [],
            "errors": [f"{type(error).__name__}: {error}"]}
    tipo = canonical_tipo(a.get("tipo"))
    return enriquecer_documento(build_document(meta, "", tipo_declarado=tipo), tipo)


def agente_ocr(state: EstadoDocumento, config: RunnableConfig) -> dict:
    a = state["archivo"]
    try:
        doc, info = ocr_documento(a["ruta"], a["nombre"], a.get("tipo"), _aj(config))
    except Exception as e:  # noqa: BLE001 - archivo dañado, protegido o de formato no soportado
        log.warning("OCR falló en %s: %s", a["nombre"], e)
        doc, info = _documento_con_error(a, e), {"ocr_s": 0.0, "cache": False}
    return {"doc_ocr": doc, "info_ocr": info,
            "evento": {"archivo": a["nombre"], "etapa": "ocr", "s": info["ocr_s"], "cache": info["cache"],
                       "paginas": doc["NumPaginas"], "calidad": doc.get("CalidadTexto"), "estado": doc["Estado"]}}


_pool_calidad = ThreadPoolExecutor(max_workers=8, thread_name_prefix="calidad")


def agente_calidad(state: EstadoDocumento, config: RunnableConfig) -> dict:
    """Fase 1 del equipo: ¿es un documento válido del tipo esperado?

    Se lanza en segundo plano y NO bloquea la extracción (el filtro usa un candado del equipo y con
    5 documentos sumaba ~20 s de espera). Su resultado se une al terminar el documento (_salida):
    un documento VOLVER_A_SUBIR queda fuera de la validación cruzada y cuenta como faltante."""
    a = state["archivo"]
    futuro = _pool_calidad.submit(calidad_mod.evaluar, a["ruta"], a["nombre"], canonical_tipo(a.get("tipo")))
    return {"calidad_futuro": futuro}


def agente_clasificador(state: EstadoDocumento, config: RunnableConfig) -> dict:
    t0 = time.perf_counter()
    tipo, metodo = agentes.clasificar(state["doc_ocr"], _aj(config))
    return {"tipo": tipo, "clasificacion": metodo,
            "evento": {"archivo": state["archivo"]["nombre"], "etapa": "clasificacion", "tipo": tipo,
                       "metodo": metodo, "s": round(time.perf_counter() - t0, 2)}}


def _ruta_extractor(state: EstadoDocumento) -> str:
    return EXTRACTORES.get(state.get("tipo") or "", "sin_tipo")


def _salida(state: EstadoDocumento, analizado: DocumentoAnalizado) -> dict:
    analizado.tiempos["ocr_s"] = state["info_ocr"]["ocr_s"]
    analizado.tiempos["ocr_cache"] = float(state["info_ocr"]["cache"])
    futuro = state.get("calidad_futuro")
    try:
        analizado.calidad = futuro.result(timeout=120) if futuro else None
    except Exception as e:  # noqa: BLE001 - sin filtro el análisis sigue
        log.warning("Filtro de calidad sin resultado: %s", e)
    return {"documentos": [{"analizado": analizado.model_dump(), "ocr": state["doc_ocr"],
                            "clasificacion": state.get("clasificacion")}],
            "evento": {"archivo": state["archivo"]["nombre"], "etapa": "extraccion", "tipo": analizado.tipo,
                       "s": analizado.tiempos.get("llm_s", 0.0), "campos": len(analizado.campos),
                       "error": analizado.error_llm}}


def _extractor(tipo: str) -> Callable:
    def nodo(state: EstadoDocumento, config: RunnableConfig) -> dict:
        return _salida(state, agentes.extraer(state["doc_ocr"], tipo, _aj(config)))
    nodo.__name__ = EXTRACTORES[tipo]
    return nodo


def sin_tipo(state: EstadoDocumento) -> dict:
    return _salida(state, agentes.documento_sin_tipo(state["doc_ocr"], state.get("clasificacion", "")))


FINALES = [*EXTRACTORES.values(), "sin_tipo"]


def construir_subgrafo():
    g = StateGraph(EstadoDocumento)
    g.add_node("agente_calidad", agente_calidad)
    g.add_node("agente_ocr", agente_ocr)
    g.add_node("agente_clasificador", agente_clasificador)
    for tipo, nombre in EXTRACTORES.items():
        g.add_node(nombre, _extractor(tipo))
    g.add_node("sin_tipo", sin_tipo)
    g.add_edge(START, "agente_calidad")          # lanza la Fase 1 en segundo plano
    g.add_edge("agente_calidad", "agente_ocr")
    g.add_edge("agente_ocr", "agente_clasificador")
    g.add_conditional_edges("agente_clasificador", _ruta_extractor, FINALES)
    for nombre in FINALES:
        g.add_edge(nombre, END)
    return g.compile()


# ---------------------------------------------------------------------------------------
# Grafo principal
# ---------------------------------------------------------------------------------------
class EstadoGrafo(TypedDict, total=False):
    archivos: list[dict]
    documentos: Annotated[list[dict], operator.add]
    hallazgos: list[dict]
    resultado: dict


def despachar(state: EstadoGrafo) -> list[Send]:
    return [Send("analizar_documento", {"archivo": a}) for a in state["archivos"]]


def _expediente_id(docs: list[DocumentoAnalizado], ocr: list[dict]) -> str:
    for t in ("Escritura", "Predial", "Alineamiento", "UsoDeSuelo"):
        for d in docs:
            c = d.campos.get("clave_catastral")
            if d.tipo == t and c and len(digits_only(str(c.valor))) >= 8:
                return f"EXP-{digits_only(str(c.valor))}"
    h = hashlib.sha1("|".join(sorted(o.get("Hash") or o.get("RutaArchivo", "") for o in ocr)).encode()).hexdigest()
    return f"EXP-{h[:10]}"


def validador_cruzado(state: EstadoGrafo, config: RunnableConfig) -> dict:
    t0 = time.perf_counter()
    docs = [DocumentoAnalizado.model_validate(x["analizado"]) for x in state["documentos"]]
    ocr = {x["ocr"]["RutaArchivo"]: x["ocr"] for x in state["documentos"]}
    hallazgos = reglas.validar(docs, ocr, _aj(config))
    return {"hallazgos": [h.model_dump() for h in hallazgos],
            "resultado": {"validacion_s": round(time.perf_counter() - t0, 3)}}


def dictaminador(state: EstadoGrafo, config: RunnableConfig) -> dict:
    aj = _aj(config)
    t_inicio = config["configurable"].get("t_inicio", time.perf_counter())
    docs = [DocumentoAnalizado.model_validate(x["analizado"]) for x in state["documentos"]]
    orden = {n: i for i, n in enumerate(a["nombre"] for a in state["archivos"])}
    docs.sort(key=lambda d: orden.get(d.ruta_archivo, 99))
    hallazgos = [Hallazgo.model_validate(h) for h in state["hallazgos"]]
    estado_reglas = reglas.decidir_estado(hallazgos)
    recibidos = [t for t in TIPOS if any(d.tipo == t and not reglas.rechazado(d) for d in docs)]
    dic = dictaminar(estado_reglas, hallazgos, recibidos, aj, time.perf_counter() - t_inicio)
    conf, nivel, factores = reglas.calcular_confianza(docs, hallazgos)
    tiempos = {
        "ocr_max_s": max((d.tiempos.get("ocr_s", 0) for d in docs), default=0.0),
        "llm_extraccion_max_s": max((d.tiempos.get("llm_s", 0) for d in docs), default=0.0),
        "llm_extraccion_suma_s": round(sum(d.tiempos.get("llm_s", 0) for d in docs), 2),
        "validacion_s": state.get("resultado", {}).get("validacion_s", 0.0),
        "dictamen_s": dic["dictamen_s"],
        "paginas": float(sum(d.num_paginas for d in docs)),
    }
    color, color_texto = reglas.semaforo(dic["estado"], hallazgos)
    res = ResultadoExpediente(
        expediente_id=_expediente_id(docs, [x["ocr"] for x in state["documentos"]]),
        estado=dic["estado"], semaforo=color, semaforo_texto=color_texto,
        estado_reglas=estado_reglas, estado_llm=dic["estado_llm"],
        confianza=conf, nivel_confianza=nivel, factores_confianza=factores,
        resumen=dic["resumen"], observaciones=dic["observaciones"], dictamen_por=dic["dictamen_por"],
        uso_requerido=aj.uso_requerido, fecha_referencia=aj.fecha_referencia.isoformat(),
        documentos_recibidos=[NOMBRE_TIPO[t] for t in recibidos],
        documentos_faltantes=[NOMBRE_TIPO[t] for t in TIPOS if t not in recibidos],
        requisitos_cumplidos=list(dict.fromkeys(h.regla for h in hallazgos if h.resultado == "cumple")),
        requisitos_no_cumplidos=list(dict.fromkeys(
            f"{h.regla}{' (crítico)' if h.severidad == 'critica' else ''}" for h in hallazgos
            if h.resultado in ("no_cumple", "revisar"))),
        hallazgos=hallazgos, documentos=docs, proveedor_llm=aj.proveedor, modelo_llm=aj.modelo,
        tiempos=tiempos,
    )
    return {"resultado": res.model_dump()}


def construir_grafo():
    g = StateGraph(EstadoGrafo)
    g.add_node("analizar_documento", construir_subgrafo())
    g.add_node("validador_cruzado", validador_cruzado)
    g.add_node("dictaminador", dictaminador)
    g.add_conditional_edges(START, despachar, ["analizar_documento"])
    g.add_edge("analizar_documento", "validador_cruzado")
    g.add_edge("validador_cruzado", "dictaminador")
    g.add_edge("dictaminador", END)
    return g.compile()


_GRAFO = None


def grafo():
    global _GRAFO
    if _GRAFO is None:
        _GRAFO = construir_grafo()
    return _GRAFO


def diagrama_mermaid() -> str:
    return grafo().get_graph(xray=True).draw_mermaid()


# ---------------------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------------------
def _normalizar_archivos(archivos) -> list[dict]:
    out = []
    for a in archivos:
        if isinstance(a, dict):
            ruta = a["ruta"]
            out.append({"ruta": str(ruta), "nombre": a.get("nombre") or Path(ruta).name, "tipo": a.get("tipo")})
        elif isinstance(a, (tuple, list)):
            ruta, tipo = (list(a) + [None])[:2]
            out.append({"ruta": str(ruta), "nombre": Path(ruta).name, "tipo": tipo})
        else:
            out.append({"ruta": str(a), "nombre": Path(a).name, "tipo": None})
    unicos, vistos = [], set()
    for a in out:   # el mismo archivo dos veces (p. ej. alineamiento y número oficial): se analiza una vez
        try:
            h = hashlib.sha256(Path(a["ruta"]).read_bytes()).hexdigest()
        except OSError:
            h = a["ruta"]
        if h not in vistos:
            vistos.add(h)
            unicos.append(a)
    out = unicos
    nombres = [a["nombre"] for a in out]
    for a in out:  # nombres repetidos: se distinguen para la trazabilidad
        if nombres.count(a["nombre"]) > 1:
            a["nombre"] = f"{Path(a['ruta']).parent.name}/{a['nombre']}"
    return out


def analizar_expediente(archivos, aj: Ajustes | None = None,
                        al_progresar: Callable[[dict], None] | None = None) -> dict:
    """Analiza los documentos de UN inmueble y devuelve un dict con el formato ResultadoExpediente.

    archivos: rutas, tuplas (ruta, tipo_declarado) o dicts {"ruta", "nombre", "tipo"}.
              tipo_declarado: "Escritura" | "Predial" | "Alineamiento" | "UsoDeSuelo" | None (detectar).
    al_progresar: callback opcional que recibe eventos {"archivo", "etapa", "s", ...}.
    """
    aj = aj or Ajustes.desde_entorno()
    aj.validar()
    entradas = _normalizar_archivos(archivos)
    if not entradas:
        raise ValueError("Se requiere al menos un documento")
    carga_modelo = 0.0
    if aj.es_local and not estado_ollama(aj)["modelo_cargado"]:
        # costo único al arrancar (keep_alive mantiene el modelo en GPU): se mide aparte
        if al_progresar:
            al_progresar({"archivo": None, "etapa": "carga_modelo", "s": 0.0})
        carga_modelo = precalentar(aj)
    t0 = time.perf_counter()
    config: RunnableConfig = {"configurable": {"ajustes": aj, "t_inicio": t0}, "max_concurrency": 16,
                              "recursion_limit": 50}
    resultado = None
    for _ns, actualizacion in grafo().stream({"archivos": entradas}, config, stream_mode="updates", subgraphs=True):
        for nodo, datos in (actualizacion or {}).items():
            if not isinstance(datos, dict):
                continue
            if al_progresar and "evento" in datos:
                al_progresar(datos["evento"])
            if nodo == "validador_cruzado" and al_progresar:
                al_progresar({"archivo": None, "etapa": "validacion", "s": datos["resultado"]["validacion_s"],
                              "hallazgos": len(datos["hallazgos"])})
            if nodo == "dictaminador":
                resultado = datos["resultado"]
    if resultado is None:
        raise RuntimeError("El grafo terminó sin resultado")
    resultado["tiempos"]["total_s"] = round(time.perf_counter() - t0, 2)
    resultado["tiempos"]["carga_modelo_s"] = carga_modelo
    if al_progresar:
        al_progresar({"archivo": None, "etapa": "dictamen", "s": resultado["tiempos"]["dictamen_s"],
                      "por": resultado["dictamen_por"], "estado": resultado["estado"]})
    return resultado
