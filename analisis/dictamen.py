"""Agente dictaminador: redacta el dictamen y puede escalar el estado (nunca relajarlo).

El estado lo deciden las reglas (reproducible y auditable). El LLM:
  * redacta el resumen y las acciones a seguir a partir de los hallazgos verificados;
  * sugiere un estado; si las reglas dicen "Cumple" y el LLM ve un problema, el expediente pasa a
    "Requiere revisión". Nunca convierte un "No cumple" en otra cosa ni aprueba lo que las reglas
    marcaron para revisión (evita que una alucinación apruebe un expediente).
Si no queda tiempo dentro del objetivo (DICTAMEN_LLM=auto), la redacción es determinista.
"""
from __future__ import annotations

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from . import prompts
from .config import Ajustes
from .esquemas import NOMBRE_TIPO, Hallazgo, RedaccionDictamen
from .llm import llm_estructurado

log = logging.getLogger("analisis")

SEGUNDOS_RESERVA_DICTAMEN = 12.0

ACCION = {
    "completitud": "Solicitar el documento faltante o corregir el tipo de documento entregado.",
    "calidad": "Volver a subir el documento que no pasó el filtro de calidad.",
    "legibilidad": "Solicitar una copia legible del documento.",
    "identificacion": "Confirmar que todos los documentos correspondan al mismo inmueble.",
    "consistencia": "Aclarar con el propietario las diferencias de datos entre documentos.",
    "vigencia": "Solicitar la renovación o una constancia vigente.",
    "predial": "Solicitar el comprobante de pago del predial del ejercicio vigente.",
    "uso_suelo": "Verificar con el municipio la compatibilidad del uso de suelo con el giro comercial.",
    "alineamiento": "Evaluar el impacto de la afectación del alineamiento en el proyecto del local.",
}


def combinar_estados(estado_reglas: str, estado_llm: str | None) -> str:
    if estado_reglas == "Cumple" and estado_llm in ("Requiere revisión", "No cumple"):
        return "Requiere revisión"
    return estado_reglas


def _problemas(hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    orden = {"critica": 0, "revision": 1, "info": 2}
    return sorted([h for h in hallazgos if h.resultado in ("no_cumple", "revisar")], key=lambda h: orden[h.severidad])


def redaccion_determinista(estado: str, hallazgos: list[Hallazgo]) -> tuple[str, list[str]]:
    problemas = _problemas(hallazgos)
    if estado == "Cumple" or not problemas:
        return ("El expediente cumple: se recibieron los 4 documentos, los datos del inmueble coinciden entre ellos, "
                "las vigencias están en orden y el uso de suelo permite el giro requerido."), []
    motivos = "; ".join(h.descripcion.rstrip(".") for h in problemas[:3])
    extra = f" (y {len(problemas) - 3} hallazgo(s) más)" if len(problemas) > 3 else ""
    acciones = list(dict.fromkeys(ACCION[h.categoria] for h in problemas if h.categoria in ACCION))[:3]
    return f"{estado}. Motivos principales: {motivos}{extra}.", acciones


def _entrada_llm(estado_reglas: str, hallazgos: list[Hallazgo], tipos_recibidos: list[str]) -> str:
    lineas = [f"Documentos recibidos: {', '.join(NOMBRE_TIPO[t] for t in tipos_recibidos) or 'ninguno'}",
              f"Estado según reglas: {estado_reglas}", "Hallazgos:"]
    relevantes = _problemas(hallazgos) + [h for h in hallazgos if h.resultado == "cumple"
                                         and h.categoria in ("uso_suelo", "predial", "vigencia", "identificacion")]
    relevantes += [h for h in hallazgos if h.resultado == "informativo" and h.categoria in ("uso_suelo", "consistencia")]
    for h in relevantes[:14]:
        lineas.append(f"- [{h.resultado.upper()}] {h.descripcion}")
    return "\n".join(lineas)[:3500]


def dictaminar(estado_reglas: str, hallazgos: list[Hallazgo], tipos_recibidos: list[str], aj: Ajustes,
               segundos_transcurridos: float) -> dict:
    resumen, obs = redaccion_determinista(estado_reglas, hallazgos)
    base = {"estado": estado_reglas, "estado_llm": None, "resumen": resumen, "observaciones": obs,
            "dictamen_por": "reglas", "dictamen_s": 0.0}
    usar = aj.dictamen_llm == "si" or (
        aj.dictamen_llm == "auto" and segundos_transcurridos < aj.tiempo_objetivo_s - SEGUNDOS_RESERVA_DICTAMEN)
    if not usar:
        return base
    t0 = time.perf_counter()
    try:
        r: RedaccionDictamen = llm_estructurado(aj, RedaccionDictamen, "dictamen").invoke([
            SystemMessage(prompts.DICTAMINADOR.format(uso_requerido=aj.uso_requerido)),
            HumanMessage(_entrada_llm(estado_reglas, hallazgos, tipos_recibidos)),
        ])
    except Exception as e:  # noqa: BLE001
        log.warning("Dictaminador LLM falló, se usa redacción determinista: %s", e)
        return {**base, "dictamen_s": round(time.perf_counter() - t0, 2)}
    return {
        "estado": combinar_estados(estado_reglas, r.estado_sugerido),
        "estado_llm": r.estado_sugerido,
        "resumen": r.resumen.strip() or resumen,
        "observaciones": [o.strip() for o in r.observaciones if o.strip()][:3] or obs,
        "dictamen_por": "llm",
        "dictamen_s": round(time.perf_counter() - t0, 2),
    }
