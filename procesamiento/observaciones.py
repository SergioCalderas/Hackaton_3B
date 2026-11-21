"""Observaciones estructuradas de un expediente.

Convierte lo que dejan las etapas (hoy: Fase 1, filtro de calidad) en una lista uniforme
que consumen el front y el dictamen con LLM:

  {id, tabla, documento, etapa, codigo, regla, severidad, bloquea, texto}

  severidad: CRITICA | ALTA | MEDIA | BAJA   (como en los requerimientos, RF-04/06)
  bloquea:   True si impide continuar (hay que volver a subir o falta el archivo)
  id:        estable ("escrituras-3") para que el dictamen pueda citarlo

Los hallazgos de la validación cruzada (VC-xx) se agregan en de_operacion() con la misma forma
(ver etapa_verificacion.py). Los de riesgos (RG-xx) se agregarán igual.
"""
from __future__ import annotations

import re

NOMBRE_TABLA = {
    "escrituras": "Escrituras",
    "predial": "Predial",
    "suelo": "Uso de Suelo",
    "aliniamiento": "Alineamiento y Número Oficial",
}
ORDEN_SEVERIDAD = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3}

# (patrón sobre el texto de la observación, código, regla, severidad)
_REGLAS_TEXTO = [
    (r"vigencia vencida", "RIESGO-VIGENCIA", "RG-01", "ALTA"),
    (r"adeudo|pendientes de pago", "RIESGO-ADEUDO", "RG-04", "MEDIA"),
    (r"varios documentos juntos", "CAL-COMBINADO", "RF-02", "MEDIA"),
    (r"formato.*pago|comprobante de pago|certificaci[oó]n bancaria", "CAL-NO-COMPROBANTE", None, "MEDIA"),
    (r"tipo ambiguo|no se pudo confirmar el tipo|se detect[oó]", "CAL-TIPO-DUDOSO", "RF-02", "MEDIA"),
    (r"cancelado|no surte efectos", "CAL-CANCELADO", None, "ALTA"),
    (r"no se pudo leer|calidad de lectura|confianza media", "CAL-LECTURA", None, "BAJA"),
    (r"foto|n[ií]tida|resoluci[oó]n baja|girad|en blanco", "CAL-IMAGEN", None, "BAJA"),
]


def _clasificar(texto: str, tabla: str) -> tuple[str, str | None, str]:
    t = texto.lower()
    for patron, codigo, regla, sev in _REGLAS_TEXTO:
        if re.search(patron, t):
            # Vigencia del predial es adeudo/periodo (RG-04), no RG-01
            if codigo == "RIESGO-VIGENCIA" and tabla == "predial":
                return "RIESGO-PERIODO", "RG-04", "MEDIA"
            return codigo, regla, sev
    return "CAL-OBSERVACION", None, "BAJA"


def de_documento(tabla: str, doc: dict) -> list[dict]:
    """doc = entrada de fuentes.resumen_operaciones()[i]["documentos"][tabla]."""
    nombre = NOMBRE_TABLA.get(tabla, tabla)
    salida: list[dict] = []

    def agregar(codigo, regla, severidad, texto, bloquea=False):
        previa = next((o for o in salida if o["codigo"] == codigo), None)
        if previa:  # misma señal dicha de otra forma: una sola observación
            previa["texto"] += f" · {texto}"
            return
        salida.append({"id": f"{tabla}-{len(salida) + 1}", "tabla": tabla, "documento": nombre,
                       "etapa": "calidad", "codigo": codigo, "regla": regla, "severidad": severidad,
                       "bloquea": bloquea, "texto": texto})

    if not doc.get("tiene_archivo"):
        agregar("FALTA-ARCHIVO", "RF-01", "ALTA", "No hay archivo cargado para este documento.", True)
        return salida
    f = doc.get("filtro")
    if not f:
        agregar("SIN-VERIFICAR", None, "MEDIA", "El documento aún no pasa por el filtro de calidad.")
        return salida

    if f["estado"] == "VOLVER_A_SUBIR":
        agregar("CAL-RECHAZO", "VC-07", "ALTA", f["mensaje"], True)
    elif f["estado"] == "REVISION_MANUAL":
        codigo, regla, sev = _clasificar(f["motivo"] or "", tabla)
        agregar(codigo, regla, sev, f["motivo"])

    vistos = {f.get("motivo")}
    for texto in f.get("observaciones") or []:
        if texto in vistos:
            continue
        vistos.add(texto)
        codigo, regla, sev = _clasificar(texto, tabla)
        agregar(codigo, regla, sev, texto)
    return salida


def de_operacion(op: dict) -> list[dict]:
    """Todas las observaciones de una operación, de la más grave a la más leve.
    Incluye las de la validación cruzada (etapa_verificacion.py) cuando hay campos extraídos."""
    obs = [o for tabla, doc in op["documentos"].items() for o in de_documento(tabla, doc)]
    try:
        from . import etapa_verificacion
        obs += etapa_verificacion.observaciones(op)
    except Exception as e:  # noqa: BLE001 — la validación cruzada nunca debe romper la Fase 1
        print(f"[procesamiento] Validación cruzada omitida: {e.__class__.__name__}: {e}", flush=True)
    return sorted(obs, key=lambda o: (ORDEN_SEVERIDAD[o["severidad"]], o["tabla"]))
