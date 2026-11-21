"""Última etapa: dictamen del expediente (RF-08).

Regla del proyecto: "el LLM lee, el código decide".
  1. semaforo()      -> el color lo decide código determinista a partir de las observaciones.
  2. entrada_llm()   -> paquete con semáforo + observaciones (con id) que se manda al LLM.
  3. redactar()      -> el LLM SOLO redacta la justificación; debe citar ids de observaciones.
                        No puede cambiar el semáforo (no forma parte de su salida).
                        Sin LLM configurado, se redacta con una plantilla determinista.

Configuración (variables de entorno del servidor):
  DICTAMEN_LLM=1           activa la llamada al LLM (por omisión: plantilla, costo cero)
  DICTAMEN_MODELO          modelo (por omisión claude-opus-5-5)
  DICTAMEN_EFFORT          low | medium | high (por omisión low: es redacción corta)
  ANTHROPIC_API_KEY        credencial (o perfil de `ant auth login`)
"""
from __future__ import annotations

import json
import os

from .observaciones import ORDEN_SEVERIDAD

VERSION_DICTAMEN = "dictamen v0.2"
ETAPAS_COMPLETADAS = ["calidad"]
ETAPAS_PENDIENTES = ["extraccion", "normalizacion", "validacion_cruzada", "riesgos"]
# Con validación cruzada (Fase 2 + etapa_verificacion.py):
ETAPAS_COMPLETADAS_VC = ["calidad", "extraccion", "validacion_cruzada"]
ETAPAS_PENDIENTES_VC = ["riesgos"]

SEMAFORO_TEXTO = {
    "GRIS": "No validado",
    "ROJO": "No cumple",
    "AMARILLO": "Requiere revisión",
    "VERDE": "Cumple",
}


def _vc(op: dict) -> dict:
    """Resumen de la validación cruzada ({"realizada": False} si no hay campos extraídos)."""
    try:
        from . import etapa_verificacion
        return etapa_verificacion.resumen(op)
    except Exception:  # noqa: BLE001
        return {"realizada": False}


# --------------------------------------------------------------------------
# 1. Semáforo determinista
# --------------------------------------------------------------------------
def semaforo(op: dict, obs: list[dict]) -> tuple[str, str]:
    """(color, razón). Tabla de agregación de los requerimientos (3.3), aplicada a lo disponible."""
    bloqueantes = [o for o in obs if o["bloquea"]]
    if bloqueantes:
        docs = sorted({o["documento"] for o in bloqueantes})
        return "GRIS", f"Expediente incompleto: hay que cargar o volver a subir {', '.join(docs)}."
    if any(o["codigo"] == "SIN-VERIFICAR" for o in obs):
        return "GRIS", "Hay documentos que aún no pasan por el filtro de calidad."
    if any(o["severidad"] == "CRITICA" for o in obs):
        return "ROJO", "Hay al menos una observación crítica."
    relevantes = [o for o in obs if o["severidad"] in ("ALTA", "MEDIA")]
    if relevantes:
        return "AMARILLO", f"{len(relevantes)} observación(es) de severidad media o alta por revisar."
    vc = _vc(op)
    if vc["realizada"]:
        return "VERDE", (f"Los documentos pasaron el filtro de calidad y sus datos coinciden entre sí "
                         f"(validación cruzada, puntaje {vc['puntaje']:.2f}: {', '.join(vc['coinciden'])}). "
                         "Falta la evaluación de riesgos (RG) para un dictamen definitivo.")
    return "VERDE", ("Los 4 documentos pasaron el filtro de calidad. Falta la validación cruzada "
                     "de datos (Fase 2 en adelante) para un dictamen definitivo.")


# --------------------------------------------------------------------------
# 2. Lo que se manda al LLM
# --------------------------------------------------------------------------
def entrada_llm(op: dict, obs: list[dict]) -> dict:
    color, razon = semaforo(op, obs)
    vc = _vc(op)
    return {
        "operacion_id": op["operacion_id"],
        "semaforo": color,
        "semaforo_texto": SEMAFORO_TEXTO[color],
        "razon_semaforo": razon,
        "etapas_completadas": ETAPAS_COMPLETADAS_VC if vc["realizada"] else ETAPAS_COMPLETADAS,
        "etapas_pendientes": ETAPAS_PENDIENTES_VC if vc["realizada"] else ETAPAS_PENDIENTES,
        "validacion_cruzada": vc,
        "documentos": [
            {"tabla": t, "estado_filtro": (d.get("filtro") or {}).get("estado")
             or ("SIN_ARCHIVO" if not d.get("tiene_archivo") else "SIN_VERIFICAR")}
            for t, d in op["documentos"].items()
        ],
        "observaciones": [{k: o[k] for k in ("id", "documento", "codigo", "regla", "severidad", "bloquea", "texto")}
                          for o in obs],
    }


# --------------------------------------------------------------------------
# 3. Redacción
# --------------------------------------------------------------------------
SISTEMA = (
    "Eres analista de prefactibilidad inmobiliaria para una cadena de tiendas en México. "
    "Recibes el resultado de un sistema que revisó el expediente de un inmueble (Escrituras, Predial, "
    "Alineamiento y Número Oficial, Uso de Suelo). El semáforo ya lo decidió un motor de reglas: "
    "no lo cambies, no lo discutas y no inventes hallazgos. Tu trabajo es explicarlo a un gestor en "
    "español claro y profesional.\n"
    "- Basa cada afirmación en una observación de la entrada y cita su id en `observaciones_citadas`.\n"
    "- Si no hay observaciones, dilo y recuerda qué etapas siguen pendientes.\n"
    "- Las acciones sugeridas deben ser concretas (qué documento, qué hacer).\n"
)
NOTA_SOLO_CALIDAD = ("- Recuerda que solo se ha completado la revisión de calidad documental; no afirmes que "
                     "los datos coinciden entre documentos.")
NOTA_CON_VC = ("- Ya se hizo la validación cruzada de datos (observaciones VC-xx, con los valores de cada "
               "documento y su página). Si no hay observaciones VC, puedes decir que los datos revisados "
               "coinciden; los riesgos (RG) siguen pendientes.")

ESQUEMA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string", "description": "2 a 4 frases para el gestor."},
        "puntos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string"},
                    "observaciones_citadas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["texto", "observaciones_citadas"],
                "additionalProperties": False,
            },
        },
        "acciones_sugeridas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resumen", "puntos", "acciones_sugeridas"],
    "additionalProperties": False,
}


def _plantilla(entrada: dict, nota: str | None = None) -> dict:
    obs = entrada["observaciones"]
    puntos = [{"texto": f"{o['documento']}: {o['texto']}", "observaciones_citadas": [o["id"]]}
              for o in obs if o["severidad"] != "BAJA"]
    leves = [o for o in obs if o["severidad"] == "BAJA"]
    if leves:
        puntos.append({"texto": f"{len(leves)} observación(es) menores de calidad de imagen o lectura.",
                       "observaciones_citadas": [o["id"] for o in leves]})
    acciones = []
    for o in obs:
        if o["bloquea"]:
            acciones.append(f"Cargar o volver a subir {o['documento']}.")
        elif o["codigo"] == "CAL-COMBINADO":
            acciones.append(f"Separar el archivo de {o['documento']}: trae varios documentos juntos.")
        elif o["codigo"] == "CAL-NO-COMPROBANTE":
            acciones.append(f"Solicitar el comprobante de pago certificado de {o['documento']}.")
        elif o["regla"] == "RG-01":
            acciones.append(f"Confirmar la vigencia de {o['documento']} o solicitar uno actualizado.")
        elif o["codigo"] == "SIN-EXTRAER":
            acciones.append("Volver a verificar los documentos aprobados para extraer sus campos.")
        elif o["codigo"].startswith("VC-"):
            acciones.append(f"Aclarar la discrepancia ({o['regla']}): {o['texto'].split(' no coincide')[0]}"
                            " difiere entre documentos; confirmar el valor correcto con el original.")
    resumen = f"Semáforo {entrada['semaforo_texto'].lower()}: {entrada['razon_semaforo']}"
    return {"resumen": resumen, "puntos": puntos, "acciones_sugeridas": list(dict.fromkeys(acciones)),
            "origen": "plantilla", "modelo": None, "nota": nota}


def _validar_citas(redaccion: dict, entrada: dict) -> dict:
    """Ninguna afirmación sin evidencia: se quitan citas a ids que no existen
    y se marcan los puntos que quedan sin cita."""
    ids = {o["id"] for o in entrada["observaciones"]}
    for p in redaccion.get("puntos", []):
        p["observaciones_citadas"] = [i for i in p.get("observaciones_citadas", []) if i in ids]
        p["sin_evidencia"] = not p["observaciones_citadas"]
    return redaccion


def _llm_activo() -> bool:
    return os.environ.get("DICTAMEN_LLM") == "1"


def redactar(entrada: dict) -> dict:
    if not _llm_activo():
        return _plantilla(entrada, "LLM desactivado (DICTAMEN_LLM no es 1): redacción por plantilla.")
    try:
        import anthropic
    except ImportError:
        return _plantilla(entrada, "Falta el paquete 'anthropic' en el servidor: redacción por plantilla.")

    modelo = os.environ.get("DICTAMEN_MODELO", "claude-opus-5-5")
    effort = os.environ.get("DICTAMEN_EFFORT", "low")
    try:
        client = anthropic.Anthropic()
        r = client.beta.messages.create(
            model=modelo,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # si el modelo declina, el servidor reintenta con el recomendado
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": ESQUEMA}},
            system=SISTEMA + (NOTA_CON_VC if "validacion_cruzada" in entrada["etapas_completadas"]
                              else NOTA_SOLO_CALIDAD),
            messages=[{"role": "user", "content":
                       "Expediente revisado (JSON):\n" + json.dumps(entrada, ensure_ascii=False, indent=2)}],
        )
    except anthropic.AuthenticationError:
        return _plantilla(entrada, "Credencial de Anthropic inválida o ausente: redacción por plantilla.")
    except anthropic.RateLimitError:
        return _plantilla(entrada, "Límite de uso del LLM alcanzado: redacción por plantilla.")
    except anthropic.APIStatusError as e:
        return _plantilla(entrada, f"El LLM respondió error {e.status_code}: redacción por plantilla.")
    except anthropic.APIConnectionError:
        return _plantilla(entrada, "Sin conexión con el LLM: redacción por plantilla.")
    except Exception as e:  # p. ej. sin ninguna credencial configurada
        return _plantilla(entrada, f"No se pudo llamar al LLM ({e.__class__.__name__}): redacción por plantilla.")

    if r.stop_reason == "refusal":
        return _plantilla(entrada, "El LLM declinó la solicitud: redacción por plantilla.")
    if r.stop_reason == "max_tokens":
        return _plantilla(entrada, "La respuesta del LLM se cortó: redacción por plantilla.")
    texto = next((b.text for b in r.content if b.type == "text"), "")
    try:
        redaccion = json.loads(texto)
    except json.JSONDecodeError:
        return _plantilla(entrada, "La respuesta del LLM no fue JSON válido: redacción por plantilla.")
    redaccion.update({"origen": "llm", "modelo": r.model, "nota": None,
                      "uso": {"entrada": r.usage.input_tokens, "salida": r.usage.output_tokens}})
    return _validar_citas(redaccion, entrada)


def dictaminar(op: dict, obs: list[dict]) -> dict:
    entrada = entrada_llm(op, obs)
    redaccion = redactar(entrada)
    return {
        "operacion_id": op["operacion_id"],
        "version": VERSION_DICTAMEN,
        "semaforo": entrada["semaforo"],
        "semaforo_texto": entrada["semaforo_texto"],
        "razon_semaforo": entrada["razon_semaforo"],
        "observaciones": obs,
        "redaccion": redaccion,
        "entrada_llm": entrada,
    }
