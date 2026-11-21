"""Agente validador cruzado (determinista): reglas de negocio sobre los datos extraídos.

Produce `Hallazgo`s con evidencia. El estado del expediente se decide así:
  * "No cumple"          -> algún hallazgo crítico: falta un documento, el uso de suelo no permite el
                            comercio requerido, o un documento corresponde a otro inmueble.
  * "Requiere revisión"  -> inconsistencias, vigencias vencidas, predial atrasado, documentos ilegibles,
                            afectaciones... (el expediente puede continuar tras aclararlas).
  * "Cumple"             -> todo lo anterior en orden.
Las tolerancias se configuran en Ajustes (ver .env.example).
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from itertools import combinations

from ocr_pipeline.normalize import compact, norm, parse_date

from .comparar import a_float, diferencia_relativa, norm_numero, similitud  # noqa: F401
from .config import Ajustes
from .esquemas import NOMBRE_TIPO, TIPOS, DocumentoAnalizado, Evidencia, Hallazgo
from .evidencia import TextoDocumento, localizar

CAMPOS_CLAVE = {
    "Escritura": ["propietario", "calle", "superficie_terreno_m2", "clave_catastral", "numero_escritura", "lote"],
    "Predial": ["propietario", "calle", "clave_catastral", "cuenta_predial", "superficie_terreno_m2", "ejercicio_fiscal"],
    "Alineamiento": ["calle", "numero", "clave_catastral", "fecha_expedicion", "alineamiento"],
    "UsoDeSuelo": ["uso_autorizado", "giro", "calle", "clave_catastral", "fecha_expedicion"],
}

# (campo, tipo de comparación, etiqueta, categoría, tipos de documento que participan, umbral)
CAMPOS_CRUZADOS = [
    ("clave_catastral", "clave", "clave catastral", "identificacion", TIPOS, 0.95),
    ("calle", "calle", "calle", "consistencia", TIPOS, 0.85),
    ("numero", "numero", "número oficial", "consistencia", TIPOS, 1.0),
    ("colonia", "texto", "colonia", "consistencia", TIPOS, 0.80),
    ("municipio", "texto", "municipio", "consistencia", TIPOS, 0.80),
    ("lote", "exacto", "lote", "consistencia", TIPOS, 1.0),
    ("manzana", "exacto", "manzana", "consistencia", TIPOS, 1.0),
    ("propietario", "nombre", "propietario", "consistencia", ("Escritura", "Predial"), 0.90),
    ("superficie_terreno_m2", "superficie", "superficie del terreno", "consistencia", TIPOS, None),
]
ARTICULO = {"número oficial": "El", "municipio": "El", "lote": "El", "propietario": "El"}
# Documento de referencia por campo (el primero presente manda)
REFERENCIA = {"numero": ("Alineamiento", "Escritura", "Predial", "UsoDeSuelo")}
REFERENCIA_DEFECTO = ("Escritura", "Predial", "Alineamiento", "UsoDeSuelo")

_NUM_PALABRA = {"UN": 1, "UNO": 1, "UNA": 1, "DOS": 2, "TRES": 3, "CUATRO": 4, "CINCO": 5, "SEIS": 6, "DOCE": 12,
                "DIECIOCHO": 18, "VEINTICUATRO": 24, "TREINTA": 30, "SESENTA": 60, "NOVENTA": 90}


# ---------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------
def _valor(d: DocumentoAnalizado, campo: str):
    c = d.campos.get(campo)
    return c.valor if c else None


def _ev(d: DocumentoAnalizado, campo: str) -> Evidencia:
    c = d.campos.get(campo)
    if c and c.evidencia:
        return c.evidencia.model_copy(update={"valor": c.evidencia.valor or str(c.valor)})
    return Evidencia(documento=d.ruta_archivo, tipo_documento=d.tipo, pagina=None, cita="",
                     valor=None if not c else str(c.valor), verificada=False)


def _ev_doc(d: DocumentoAnalizado) -> Evidencia:
    return Evidencia(documento=d.ruta_archivo, tipo_documento=d.tipo, pagina=1, cita=d.nombre_archivo,
                     valor=None, verificada=True)


def _nombre(d: DocumentoAnalizado) -> str:
    return NOMBRE_TIPO.get(d.tipo or "", d.nombre_archivo)


def _fmt(campo: str, v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f} m²" if "superficie" in campo else f"{v:g}"
    return str(v)


def _fmt_fecha(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _h(id_: str, regla: str, categoria: str, resultado: str, severidad: str, descripcion: str,
       evidencias: list[Evidencia] | None = None) -> Hallazgo:
    return Hallazgo(id=id_, regla=regla, categoria=categoria, resultado=resultado, severidad=severidad,
                    descripcion=descripcion, evidencias=evidencias or [])


def _fecha_iso(v) -> date | None:
    if not v:
        return None
    s = str(v)
    iso = s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else parse_date(s)
    try:
        return date.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def sumar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def calcular_vencimiento(expedicion, vigencia, vencimiento) -> tuple[date | None, str]:
    """(fecha de vencimiento, cómo se obtuvo). ('indefinida' si el texto lo dice)."""
    fv = _fecha_iso(vencimiento)
    if fv:
        return fv, "fecha de vencimiento indicada"
    t = norm(vigencia or "")
    if t:
        fd = _fecha_iso(vigencia)
        if fd:
            return fd, "fecha de vigencia indicada"
        if re.search(r"INDEFINID|PERMANENTE|SIN VENCIMIENTO|SIN CADUCIDAD", t):
            return None, "indefinida"
        m = re.search(r"\b(\d+|" + "|".join(_NUM_PALABRA) + r")\s*(?:\(\s*\d+\s*\)\s*)?(ANOS?|MES(?:ES)?|DIAS?)\b", t)
        fe = _fecha_iso(expedicion)
        if m and fe:
            n = int(m.group(1)) if m.group(1).isdigit() else _NUM_PALABRA[m.group(1)]
            u = m.group(2)
            if u.startswith("ANO"):
                return sumar_meses(fe, 12 * n), f"{n} año(s) desde la expedición"
            if u.startswith("MES"):
                return sumar_meses(fe, n), f"{n} mes(es) desde la expedición"
            from datetime import timedelta
            return fe + timedelta(days=n), f"{n} día(s) desde la expedición"
    return None, "no indicada"


# ---------------------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------------------
def regla_completitud(docs: list[DocumentoAnalizado]) -> list[Hallazgo]:
    out = []
    for t in TIPOS:
        de_tipo = [d for d in docs if d.tipo == t]
        if de_tipo:
            out.append(_h(f"completitud:{t}", f"Documento presente: {NOMBRE_TIPO[t]}", "completitud", "cumple", "info",
                          f"Se recibió {NOMBRE_TIPO[t]} ({', '.join(d.nombre_archivo for d in de_tipo)}).",
                          [_ev_doc(d) for d in de_tipo]))
            if len(de_tipo) > 1 and t != "Predial":
                out.append(_h(f"completitud:{t}:repetido", f"Documentos repetidos: {NOMBRE_TIPO[t]}", "completitud",
                              "informativo", "info", f"Hay {len(de_tipo)} documentos de tipo {NOMBRE_TIPO[t]}; "
                              "se consideran todos en la validación.", [_ev_doc(d) for d in de_tipo]))
        else:
            out.append(_h(f"completitud:{t}", f"Documento faltante: {NOMBRE_TIPO[t]}", "completitud", "no_cumple",
                          "critica", f"Falta {NOMBRE_TIPO[t]}, uno de los 4 documentos mínimos del expediente."))
    for d in docs:
        if d.tipo is None:
            out.append(_h(f"completitud:sin_tipo:{d.nombre_archivo}", "Documento no identificado", "completitud",
                          "revisar", "revision", f"No se pudo identificar qué tipo de documento es "
                          f"{d.nombre_archivo} ({d.error_llm or 'contenido no reconocido'}).", [_ev_doc(d)]))
        elif d.tipo_declarado and d.tipo_detectado and d.tipo_declarado != d.tipo_detectado:
            out.append(_h(f"completitud:tipo:{d.nombre_archivo}", "Tipo declarado distinto al contenido", "completitud",
                          "revisar", "revision", f"{d.nombre_archivo} se entregó como {NOMBRE_TIPO[d.tipo_declarado]}, "
                          f"pero su contenido corresponde a {NOMBRE_TIPO[d.tipo_detectado]}.", [_ev_doc(d)]))
    return out


def regla_legibilidad(docs: list[DocumentoAnalizado]) -> list[Hallazgo]:
    out = []
    for d in docs:
        if not d.tipo:
            continue
        encontrados = [c for c in CAMPOS_CLAVE[d.tipo] if c in d.campos]
        mala_calidad = d.estado_ocr in ("low_text", "low_confidence", "error", "partial")
        q = f"{d.calidad_texto:.0%}" if d.calidad_texto is not None else "sin texto"
        if mala_calidad or len(encontrados) < 2:
            out.append(_h(f"legibilidad:{d.nombre_archivo}", f"Legibilidad: {_nombre(d)}", "legibilidad", "revisar",
                          "revision", f"{d.nombre_archivo} es ilegible o incompleto (calidad de texto {q}, "
                          f"{len(encontrados)} de {len(CAMPOS_CLAVE[d.tipo])} datos clave). Solicitar una copia legible.",
                          [_ev_doc(d)]))
    return out


def _referencia(campo: str, con_valor: list[DocumentoAnalizado]) -> DocumentoAnalizado:
    for t in REFERENCIA.get(campo, REFERENCIA_DEFECTO):
        for d in con_valor:
            if d.tipo == t:
                return d
    return con_valor[0]


def regla_campos_cruzados(docs: list[DocumentoAnalizado], aj: Ajustes) -> list[Hallazgo]:
    out = []
    for campo, tipo_cmp, etiqueta, categoria, tipos, umbral in CAMPOS_CRUZADOS:
        con_valor = [d for d in docs if d.tipo in tipos and _valor(d, campo) not in (None, "", [])]
        if len(con_valor) < 2:
            continue
        ref = _referencia(campo, con_valor)
        vref = _valor(ref, campo)
        difieren, leves, sin_numero = [], [], []
        for d in con_valor:
            if d is ref:
                continue
            v = _valor(d, campo)
            if tipo_cmp == "numero" and (norm_numero(v) == "SN") != (norm_numero(vref) == "SN"):
                sin_numero.append(d)       # un documento no indica número: falta de dato, no contradicción
                continue
            if tipo_cmp == "superficie":
                fa, fb = a_float(vref), a_float(v)
                rel = diferencia_relativa(fa, fb) if fa and fb else 0.0
                if rel > aj.superficie_tolerancia:
                    difieren.append((d, v, f"{rel:.1%}"))
                continue
            s = similitud(tipo_cmp, vref, v)
            if s is None or s >= umbral:
                continue
            if tipo_cmp == "clave" and s >= 0.8:
                leves.append((d, v, "difiere en un dígito: posible error de OCR o alteración"))
            else:
                difieren.append((d, v, None))
        evidencias = [_ev(d, campo) for d in con_valor]
        nombres = ", ".join(_nombre(d) for d in con_valor)
        art = ARTICULO.get(etiqueta, "La")
        if sin_numero:
            out.append(_h(f"{categoria}:{campo}:sin_numero", "Número oficial no indicado en algún documento", categoria,
                          "informativo", "info", f"{', '.join(_nombre(d) for d in sin_numero)} indica S/N mientras "
                          f"{_nombre(ref)} indica el número {vref}. Es una falta de dato, no una contradicción.",
                          [_ev(ref, campo)] + [_ev(d, campo) for d in sin_numero]))
            con_valor = [d for d in con_valor if d not in sin_numero]
            if len(con_valor) < 2:
                continue
        if not difieren and not leves:
            out.append(_h(f"{categoria}:{campo}", f"Coincidencia de {etiqueta}", categoria, "cumple", "info",
                          f"{art} {etiqueta} coincide en {len(con_valor)} documentos ({nombres}): "
                          f"{_fmt(campo, vref)}.", evidencias))
            continue
        partes = [f"{_nombre(ref)}: {_fmt(campo, vref)}"]
        for d, v, nota in difieren + leves:
            sufijo = ""
            if nota:
                sufijo = f" (diferencia de {nota})" if tipo_cmp == "superficie" else f" ({nota})"
            partes.append(f"{_nombre(d)}: {_fmt(campo, v)}{sufijo}")
        tolerancia = f" Tolerancia: {aj.superficie_tolerancia:.0%}." if tipo_cmp == "superficie" else ""
        out.append(_h(f"{categoria}:{campo}", f"Inconsistencia de {etiqueta}", categoria, "revisar", "revision",
                      f"{art} {etiqueta} no coincide entre documentos — " + "; ".join(partes) + "." + tolerancia,
                      evidencias))
    return out


def regla_titular_tramites(docs: list[DocumentoAnalizado]) -> list[Hallazgo]:
    """Alineamiento y uso de suelo pueden estar a nombre del solicitante: solo informativo."""
    duenos = [d for d in docs if d.tipo in ("Escritura", "Predial") and _valor(d, "propietario")]
    if not duenos:
        return []
    ref = _referencia("propietario", duenos)
    out = []
    for d in docs:
        if d.tipo in ("Alineamiento", "UsoDeSuelo") and _valor(d, "propietario"):
            s = similitud("nombre", _valor(ref, "propietario"), _valor(d, "propietario"))
            if s is not None and s < 0.9:
                out.append(_h(f"consistencia:titular:{d.nombre_archivo}", f"Titular del trámite: {_nombre(d)}",
                              "consistencia", "informativo", "info",
                              f"{_nombre(d)} está a nombre de {_valor(d, 'propietario')}, distinto del propietario "
                              f"según {_nombre(ref)} ({_valor(ref, 'propietario')}). Puede ser el solicitante; "
                              "confirmar que el trámite corresponde al inmueble.",
                              [_ev(ref, "propietario"), _ev(d, "propietario")]))
    return out


def _conflictos_fuertes(a: DocumentoAnalizado, b: DocumentoAnalizado) -> tuple[int, int, list[str]]:
    """(comparables, conflictos fuertes, detalle) entre dos documentos en clave, calle y municipio."""
    comparables, conflictos, detalle = 0, 0, []
    for campo, tipo_cmp, limite in (("clave_catastral", "clave", 0.8), ("calle", "calle", 0.7),
                                    ("municipio", "texto", 0.7)):
        s = similitud(tipo_cmp, _valor(a, campo), _valor(b, campo))
        if s is None:
            continue
        comparables += 1
        if s < limite:
            conflictos += 1
            detalle.append(f"{campo.replace('_', ' ')}: {_valor(a, campo)} vs {_valor(b, campo)}")
    return comparables, conflictos, detalle


def regla_otro_inmueble(docs: list[DocumentoAnalizado]) -> list[Hallazgo]:
    tipados = [d for d in docs if d.tipo]
    if len(tipados) < 2:
        return []
    choques: dict[int, list[tuple[DocumentoAnalizado, list[str]]]] = {id(d): [] for d in tipados}
    comparables: dict[int, int] = {id(d): 0 for d in tipados}
    for a, b in combinations(tipados, 2):
        n, c, det = _conflictos_fuertes(a, b)
        if n >= 2:
            comparables[id(a)] += 1
            comparables[id(b)] += 1
            if c >= 2:
                choques[id(a)].append((b, det))
                choques[id(b)].append((a, det))
    out = []
    marcados = [d for d in tipados if comparables[id(d)] and len(choques[id(d)]) / comparables[id(d)] > 0.5]
    if len(tipados) == 2 and len(marcados) == 2:
        marcados = marcados[1:]          # con dos documentos basta un hallazgo
    for d in marcados:
        otro, det = choques[id(d)][0]
        evs = [_ev(d, "clave_catastral"), _ev(otro, "clave_catastral"), _ev(d, "calle"), _ev(otro, "calle")]
        s_dueno = similitud("nombre", _valor(d, "propietario"), _valor(otro, "propietario"))
        mismo_titular = s_dueno is not None and s_dueno >= 0.9
        clave_distinta = any(x.startswith("clave catastral") for x in det)
        if mismo_titular or not clave_distinta:
            # Sin clave catastral que lo confirme, o con el mismo titular, no se rechaza: puede ser un predio en
            # esquina, colindante, con clave anterior o una escritura antigua con otra nomenclatura.
            motivo = (f"aunque el titular es el mismo ({_valor(d, 'propietario')})" if mismo_titular
                      else "y no hay clave catastral comparable que lo confirme")
            out.append(_h(f"identificacion:otro_inmueble:{d.nombre_archivo}", "Posible documento de otro predio",
                          "identificacion", "revisar", "revision",
                          f"{_nombre(d)} ({d.nombre_archivo}) no coincide con {_nombre(otro)} en " + "; ".join(det)
                          + f", {motivo}. Puede ser un predio en esquina, colindante, con clave anterior o un "
                          "documento con nomenclatura antigua: confirmar que se refiere al mismo inmueble.",
                          evs + [_ev(d, "propietario"), _ev(otro, "propietario")]))
            continue
        out.append(_h(f"identificacion:otro_inmueble:{d.nombre_archivo}", "Documento de otro inmueble",
                      "identificacion", "no_cumple", "critica",
                      f"{_nombre(d)} ({d.nombre_archivo}) parece corresponder a OTRO inmueble: no coincide con "
                      f"{_nombre(otro)} en " + "; ".join(det) + ".", evs))
    return out


def compatibilidad_por_reglas(uso: str | None, giro: str | None, restricciones: list[str] | None) -> str | None:
    """'si' | 'no' | None, por palabras clave (segunda opinión independiente del LLM)."""
    t = compact(norm(" ".join([uso or "", giro or ""])))
    r = compact(norm(" ".join(restricciones or [])))
    comercial = re.search(r"COMERCI|MINISUPER|ABARROTE|AUTOSERVICIO|TIENDA|MIXTO|SERVICIOS|CORREDORURBANO", t)
    habitacional = re.search(r"HABITACION|VIVIENDA|RESIDENCIAL|UNIFAMILIAR", t)
    prohibe = re.search(r"NOSEPERMITE\w*COMERCI|PROHIB\w*COMERCI|NOAUTORIZA\w*COMERCI", r + t)
    if comercial and not prohibe:
        return "si"
    if prohibe or (habitacional and not comercial):
        return "no"
    return None


_LINEA_USO = re.compile(r"(?im)^.*\bUSOS?\s+(?:DE|DEL)\s+SUELO\b[^\n]*\bAUTORI[ZC]\w*[^\n]*$|^.*\bUSO\s+AUTORIZADO\b[^\n]*$")
_LINEA_GIRO = re.compile(r"(?im)^.*\bGIRO\b[^\n]*$")
_LINEA_PROHIBE = re.compile(r"(?is)NO\s+SE\s+PERMITE\w*\s+(?:EL\s+|LOS\s+)?USOS?\s+COMERCIAL\w*[^.\n]*")


def uso_por_texto(doc_ocr: dict) -> tuple[str | None, str | None, list[str]]:
    """Agente de reglas para el uso de suelo: lee del texto OCR (sin LLM) la línea del uso autorizado,
    la del giro y las prohibiciones explícitas de comercio."""
    texto = "\n".join(p.get("Texto") or "" for p in doc_ocr.get("Paginas", []))
    uso = _LINEA_USO.search(texto)
    giro = _LINEA_GIRO.search(texto)
    prohibe = [m.group(0) for m in _LINEA_PROHIBE.finditer(texto)]
    return (uso.group(0).strip() if uso else None), (giro.group(0).strip() if giro else None), prohibe


def regla_uso_suelo(docs: list[DocumentoAnalizado], ocr: dict[str, dict], aj: Ajustes) -> list[Hallazgo]:
    out = []
    for d in [d for d in docs if d.tipo == "UsoDeSuelo"]:
        llm = _valor(d, "compatible_comercial") or "no_determinado"
        uso_txt, giro_txt, prohibe_txt = uso_por_texto(ocr.get(d.ruta_archivo, {}))
        regla = compatibilidad_por_reglas(uso_txt or _valor(d, "uso_autorizado"), giro_txt or _valor(d, "giro"),
                                          prohibe_txt + (_valor(d, "restricciones") or []))
        uso = f"uso autorizado: {_valor(d, 'uso_autorizado') or 'no legible'}" + (
            f"; giro: {_valor(d, 'giro')}" if _valor(d, "giro") else "")
        ev = [e for e in (_ev(d, "compatible_comercial"), _ev(d, "uso_autorizado"), _ev(d, "giro"))
              if e.verificada or e.valor]
        rid, nombre = f"uso_suelo:compatibilidad:{d.nombre_archivo}", "Uso de suelo compatible con el giro requerido"
        if (llm == "si" and regla == "no") or (llm == "no" and regla == "si"):
            out.append(_h(rid, nombre, "uso_suelo", "revisar", "revision",
                          f"Los agentes discrepan sobre la compatibilidad ({uso}): el agente LLM opina "
                          f"'{llm}' y el de reglas '{regla}'. Revisar la licencia.", ev))
        elif llm == "si" or (llm == "no_determinado" and regla == "si"):
            out.append(_h(rid, nombre, "uso_suelo", "cumple", "info",
                          f"La licencia permite el uso requerido ({aj.uso_requerido}) — {uso}.", ev))
        elif llm == "no" or (llm == "no_determinado" and regla == "no"):
            out.append(_h(rid, nombre, "uso_suelo", "no_cumple", "critica",
                          f"La licencia NO autoriza el uso requerido ({aj.uso_requerido}) — {uso}.", ev))
        elif llm == "condicionado":
            out.append(_h(rid, nombre, "uso_suelo", "revisar", "revision",
                          f"El uso comercial está condicionado — {uso}. Revisar que las condiciones sean cumplibles.", ev))
        else:
            out.append(_h(rid, nombre, "uso_suelo", "revisar", "revision",
                          f"No se pudo determinar si la licencia permite el uso requerido ({uso}).", ev or [_ev_doc(d)]))
        restr = _valor(d, "restricciones") or []
        sup = _valor(d, "superficie_autorizada_m2")
        if restr or sup:
            texto = TextoDocumento.desde_documento(ocr.get(d.ruta_archivo, {}))
            evs = [localizar(texto, "restricciones", r, paginas_preferidas=d.paginas_enviadas_llm, umbral=75)
                   for r in restr[:4]]
            if sup:
                evs.append(_ev(d, "superficie_autorizada_m2"))
            detalle = "; ".join(restr[:4]) + (f"; superficie autorizada para el giro: {sup:g} m²" if sup else "")
            out.append(_h(f"uso_suelo:restricciones:{d.nombre_archivo}", "Condiciones y restricciones del uso de suelo",
                          "uso_suelo", "informativo", "info", f"La licencia establece: {detalle.strip('; ')}.", evs))
    return out


def regla_vigencias(docs: list[DocumentoAnalizado], aj: Ajustes) -> list[Hallazgo]:
    out, ref = [], aj.fecha_referencia
    for d in [d for d in docs if d.tipo in ("UsoDeSuelo", "Alineamiento")]:
        venc, como = calcular_vencimiento(_valor(d, "fecha_expedicion"), _valor(d, "vigencia"),
                                          _valor(d, "fecha_vencimiento"))
        exp = _fecha_iso(_valor(d, "fecha_expedicion"))
        ev = [e for e in (_ev(d, "fecha_expedicion"), _ev(d, "vigencia"), _ev(d, "fecha_vencimiento")) if e.valor]
        rid, nombre = f"vigencia:{d.nombre_archivo}", f"Vigencia: {_nombre(d)}"
        if venc:
            if venc < ref:
                out.append(_h(rid, nombre, "vigencia", "revisar", "revision",
                              f"{_nombre(d)} venció el {_fmt_fecha(venc)} ({como}); fecha de referencia "
                              f"{_fmt_fecha(ref)}. Solicitar renovación o constancia vigente.", ev))
            else:
                out.append(_h(rid, nombre, "vigencia", "cumple", "info",
                              f"{_nombre(d)} vigente hasta el {_fmt_fecha(venc)} ({como}).", ev))
        elif como == "indefinida":
            out.append(_h(rid, nombre, "vigencia", "cumple", "info", f"{_nombre(d)} con vigencia indefinida.", ev))
        elif exp:
            anios = (ref - exp).days / 365.25
            if d.tipo == "UsoDeSuelo" and anios > aj.uso_suelo_antiguedad_max_anios:
                out.append(_h(rid, nombre, "vigencia", "revisar", "revision",
                              f"{_nombre(d)} no indica vigencia y fue expedida el {_fmt_fecha(exp)} "
                              f"(hace {anios:.1f} años). Confirmar que sigue vigente.", ev))
            else:
                out.append(_h(rid, nombre, "vigencia", "informativo", "info",
                              f"{_nombre(d)} expedida el {_fmt_fecha(exp)}; no indica vigencia.", ev))
        else:
            res, sev = ("revisar", "revision") if d.tipo == "UsoDeSuelo" else ("informativo", "info")
            out.append(_h(rid, nombre, "vigencia", res, sev,
                          f"No se encontró la fecha de expedición ni la vigencia de {_nombre(d)}.", [_ev_doc(d)]))
    return out


def regla_predial(docs: list[DocumentoAnalizado], aj: Ajustes) -> list[Hallazgo]:
    prediales = [d for d in docs if d.tipo == "Predial"]
    if not prediales:
        return []
    anios = []
    for d in prediales:
        v = _valor(d, "ejercicio_fiscal")
        if v is None and _fecha_iso(_valor(d, "fecha_pago")):
            v = _fecha_iso(_valor(d, "fecha_pago")).year
        try:
            anios.append((int(v), d))
        except (TypeError, ValueError):
            pass
    minimo = aj.fecha_referencia.year - aj.predial_tolerancia_anios
    if not anios:
        return [_h("predial:corriente", "Predial al corriente", "predial", "revisar", "revision",
                   "No se pudo determinar el ejercicio fiscal pagado del predial.", [_ev_doc(d) for d in prediales])]
    anio, d = max(anios, key=lambda x: x[0])
    ev = [_ev(d, "ejercicio_fiscal"), _ev(d, "fecha_pago")]
    ev = [e for e in ev if e.valor] or [_ev_doc(d)]
    if anio >= minimo:
        return [_h("predial:corriente", "Predial al corriente", "predial", "cumple", "info",
                   f"El predial está pagado hasta el ejercicio {anio}.", ev)]
    return [_h("predial:corriente", "Predial al corriente", "predial", "revisar", "revision",
               f"El último ejercicio pagado es {anio}; a la fecha de referencia ({_fmt_fecha(aj.fecha_referencia)}) "
               f"se requiere el ejercicio {minimo} o posterior. Solicitar comprobante de pago actualizado.", ev)]


_SIN_AFECTACION = re.compile(r"\b(SIN|NO PRESENTA|NINGUNA|NO EXISTE|NO TIENE|NO HAY|NO SE REPORTA)\b|^\s*(NO|N A)\s*$")


def hay_afectacion(texto: str | None) -> bool:
    """False para 'sin afectación', 'ninguna' o restricciones de 0.00 m."""
    t = norm(texto or "")
    if not t or _SIN_AFECTACION.search(t):
        return False
    numeros = [float(n.replace(" ", ".")) for n in re.findall(r"\d+(?: \d{1,2}\b)?", t)]
    return not (numeros and all(n == 0 for n in numeros))


def regla_alineamiento(docs: list[DocumentoAnalizado]) -> list[Hallazgo]:
    out = []
    for d in [d for d in docs if d.tipo == "Alineamiento"]:
        afect = _valor(d, "afectaciones")
        rid, nombre = f"alineamiento:{d.nombre_archivo}", "Afectaciones en el alineamiento"
        if hay_afectacion(afect):
            out.append(_h(rid, nombre, "alineamiento", "revisar", "revision",
                          f"El alineamiento reporta una afectación o restricción: {afect}. Evaluar el impacto en el "
                          "proyecto del local.", [_ev(d, "afectaciones"), _ev(d, "alineamiento")]))
        elif _valor(d, "alineamiento") or afect:
            out.append(_h(rid, nombre, "alineamiento", "cumple", "info",
                          f"Sin afectaciones reportadas. Alineamiento: {_valor(d, 'alineamiento') or afect}.",
                          [_ev(d, "alineamiento")]))
    return out


def regla_acuerdo_agentes(docs: list[DocumentoAnalizado]) -> list[Hallazgo]:
    out = []
    for d in docs:
        if d.error_llm and d.tipo:
            out.append(_h(f"extraccion:llm:{d.nombre_archivo}", "Extracción con LLM", "extraccion", "informativo", "info",
                          f"El agente LLM no pudo procesar {d.nombre_archivo} ({d.error_llm}); se usaron solo los datos "
                          "del extractor por reglas.", [_ev_doc(d)]))
        for campo in ("clave_catastral", "superficie_terreno_m2", "numero", "propietario"):
            c = d.campos.get(campo)
            if c and c.coincide_reglas is False:
                out.append(_h(f"extraccion:{campo}:{d.nombre_archivo}", "Doble verificación de extracción",
                              "extraccion", "informativo", "info",
                              f"En {d.nombre_archivo}, el agente LLM leyó {c.etiqueta.lower()} = {_fmt(campo, c.valor)} y "
                              f"el extractor por reglas {_fmt(campo, c.valor_reglas)}. Se usa el valor del LLM.",
                              [_ev(d, campo)]))
    return out


# ---------------------------------------------------------------------------------------
# Orquestación del validador
# ---------------------------------------------------------------------------------------
def validar(docs: list[DocumentoAnalizado], ocr: dict[str, dict], aj: Ajustes) -> list[Hallazgo]:
    hallazgos = (regla_completitud(docs) + regla_legibilidad(docs) + regla_otro_inmueble(docs)
                 + regla_campos_cruzados(docs, aj) + regla_titular_tramites(docs) + regla_uso_suelo(docs, ocr, aj)
                 + regla_vigencias(docs, aj) + regla_predial(docs, aj) + regla_alineamiento(docs)
                 + regla_acuerdo_agentes(docs))
    orden = {"no_cumple": 0, "revisar": 1, "cumple": 2, "informativo": 3}
    return sorted(hallazgos, key=lambda h: orden[h.resultado])


def decidir_estado(hallazgos: list[Hallazgo]) -> str:
    if any(h.resultado == "no_cumple" and h.severidad == "critica" for h in hallazgos):
        return "No cumple"
    if any(h.resultado in ("no_cumple", "revisar") for h in hallazgos):
        return "Requiere revisión"
    return "Cumple"


def calcular_confianza(docs: list[DocumentoAnalizado], hallazgos: list[Hallazgo]) -> tuple[float, str, dict]:
    tipados = [d for d in docs if d.tipo]
    calidad = [d.calidad_texto for d in tipados if d.calidad_texto is not None]
    cobertura = [len([c for c in CAMPOS_CLAVE[d.tipo] if c in d.campos]) / len(CAMPOS_CLAVE[d.tipo]) for d in tipados]
    campos = [c for d in tipados for c in d.campos.values() if c.evidencia is not None]
    verificadas = [c.evidencia.verificada for c in campos]
    acuerdo = [c.coincide_reglas for d in tipados for c in d.campos.values() if c.coincide_reglas is not None]
    f = {
        "calidad_ocr": sum(calidad) / len(calidad) if calidad else 0.0,
        "cobertura_campos": sum(cobertura) / len(cobertura) if cobertura else 0.0,
        "evidencia_verificada": sum(verificadas) / len(verificadas) if verificadas else 0.0,
        "acuerdo_agentes": sum(acuerdo) / len(acuerdo) if acuerdo else 0.5,
        "completitud": len({d.tipo for d in tipados}) / len(TIPOS),
    }
    pesos = {"calidad_ocr": 0.25, "cobertura_campos": 0.25, "evidencia_verificada": 0.2, "acuerdo_agentes": 0.15,
             "completitud": 0.15}
    conf = round(sum(f[k] * w for k, w in pesos.items()), 3)
    nivel = "alta" if conf >= 0.8 else "media" if conf >= 0.6 else "baja"
    return conf, nivel, {k: round(v, 3) for k, v in f.items()}
