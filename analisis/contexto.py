"""Selección y limpieza del texto que se envía al LLM.

Una escritura puede tener 50 páginas (>100 mil caracteres). Al LLM local solo se le envían las
páginas más relevantes para su tipo de documento, dentro de un presupuesto de caracteres:
  * siempre la primera página (proemio: partes, número de escritura, notario);
  * después las páginas con más palabras clave del tipo y con campos ya detectados por reglas;
  * se quitan líneas basura del OCR (sellos, escudos, rayas de relleno).
Las páginas se entregan en su orden original, marcadas como [PÁGINA n].
"""
from __future__ import annotations

import re

from .evidencia import normalizar

PALABRAS_CLAVE = {
    "Escritura": ["COMPRAVENTA", "COMPRADOR", "ADQUIERE", "ADQUIRENTE", "DONATARI", "VENDEDOR", "VENDE", "UBICADO",
                  "SUPERFICIE", "MEDIDAS Y COLINDANCIAS", "LOTE", "MANZANA", "CLAVE CATASTRAL", "FOLIO REAL",
                  "ESCRITURA", "INSTRUMENTO", "NOTARIO", "VOLUMEN", "INSCRI", "REGISTRO PUBLICO", "CLAUSULA",
                  "PRIMERA", "INMUEBLE", "PROPIETARI", "TITULO", "ANTECEDENTE", "PREDIO"],
    "Predial": ["PREDIAL", "CLAVE CATASTRAL", "CUENTA", "PROPIETARIO", "CONTRIBUYENTE", "UBICACION", "SUPERFICIE",
                "TERRENO", "EJERCICIO", "PERIODO", "TOTAL", "PAGO", "VALOR CATASTRAL"],
    "Alineamiento": ["ALINEAMIENTO", "NUMERO OFICIAL", "RESTRICCION", "AFECTACION", "VIGENCIA", "EXPEDICION",
                     "UBICACION", "CLAVE CATASTRAL", "DESARROLLO URBANO", "FRENTE", "SUPERFICIE", "PREDIO"],
    "UsoDeSuelo": ["USO DE SUELO", "USO DEL SUELO", "COMERCIAL", "GIRO", "AUTORIZA", "CONDICION", "RESTRICCION",
                   "VIGENCIA", "SUPERFICIE", "COMPATIBLE", "HABITACIONAL", "LICENCIA", "EXPEDICION", "ZONA",
                   "CLAVE CATASTRAL", "DOMICILIO"],
}
_RELLENO = re.compile(r"[-=_~.·•*'\"`]{3,}")
MIN_CHARS_PAGINA = 1200   # al recortar, cada página incluida conserva al menos esto


def limpiar_texto(texto: str) -> str:
    """Quita líneas basura del OCR y el relleno de escrituras (-----, =====)."""
    lineas = []
    for linea in (texto or "").splitlines():
        linea = _RELLENO.sub(" ", linea)
        linea = re.sub(r"[ \t]{2,}", " ", linea).strip()
        if len(linea) < 2 or (len(linea) < 4 and not any(c.isdigit() for c in linea)):
            continue
        alnum = sum(c.isalnum() for c in linea)
        palabras = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}|\d{2,}", linea)]
        if alnum / len(linea) < 0.55 or not palabras:
            continue
        lineas.append(linea)
    return "\n".join(lineas)


def puntuar_pagina(texto_norm: str, tipo: str | None) -> float:
    return sum(min(texto_norm.count(k), 3) for k in PALABRAS_CLAVE.get(tipo or "", []))


def preparar_contexto(doc: dict, tipo: str | None, max_chars: int) -> tuple[str, list[int]]:
    """Devuelve (texto para el LLM, páginas incluidas)."""
    paginas = [(p["Numero"], limpiar_texto(p.get("Texto") or "")) for p in doc.get("Paginas", [])]
    paginas = [(n, t) for n, t in paginas if t]
    if not paginas:
        return "", []
    total = sum(len(t) for _, t in paginas)
    if total <= max_chars:
        elegidas = dict(paginas)
    else:
        con_campos = {c.get("Pagina") for c in (doc.get("CamposExtraidos") or {}).values()}
        puntaje = {n: puntuar_pagina(normalizar(t), tipo) + (4 if n in con_campos else 0) for n, t in paginas}
        primera = paginas[0][0]
        orden = [primera] + sorted((n for n, _ in paginas if n != primera), key=lambda n: (-puntaje[n], n))
        textos = dict(paginas)
        elegidas, restante = {}, max_chars
        for n in orden:
            if restante < MIN_CHARS_PAGINA and elegidas:
                break
            t = textos[n]
            elegidas[n] = t if len(t) <= restante else t[:restante] + " […]"
            restante -= len(elegidas[n])
    incluidas = sorted(elegidas)
    return "\n\n".join(f"[PÁGINA {n}]\n{elegidas[n]}" for n in incluidas), incluidas
