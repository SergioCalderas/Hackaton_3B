"""Normalización y similitud de valores entre documentos (reutiliza ocr_pipeline.normalize/matching)."""
from __future__ import annotations

import re

from ocr_pipeline.matching import sim_calle, sim_clave, sim_nombre, sim_texto
from ocr_pipeline.normalize import compact, digits_only, norm, norm_address, norm_cuenta, norm_estado, norm_name, parse_date

# campo del LLM -> (campo del extractor por reglas del equipo, tipo de comparación)
MAPA_REGLAS: dict[str, tuple[str, str]] = {
    "propietario": ("Propietario", "nombre"), "vendedor": ("Vendedor", "nombre"),
    "calle": ("Calle", "calle"), "numero": ("NumeroOficial", "numero"), "colonia": ("Colonia", "texto"),
    "municipio": ("Municipio", "texto"), "entidad": ("Estado", "estado"), "lote": ("Lote", "exacto"),
    "manzana": ("Manzana", "exacto"), "clave_catastral": ("ClaveCatastral", "clave"),
    "cuenta_predial": ("CuentaPredial", "cuenta"), "superficie_terreno_m2": ("SuperficieTerreno", "superficie"),
    "superficie_construccion_m2": ("SuperficieConstruccion", "superficie"),
    "numero_escritura": ("NumeroEscritura", "digitos"), "ejercicio_fiscal": ("EjercicioFiscal", "anio"),
    "fecha": ("FechaDocumento", "fecha"), "fecha_expedicion": ("FechaDocumento", "fecha"),
    "fecha_pago": ("FechaDocumento", "fecha"),
}
UMBRAL_COINCIDE = {"nombre": 0.90, "calle": 0.85, "texto": 0.85, "clave": 0.95}


def norm_numero(v) -> str:
    """'No. 28' -> '28' ; 'S/N (KM 71)' -> 'SN' ; '15-A' -> '15A'."""
    t = norm(str(v or "")).replace("/", "")
    t = re.sub(r"\b(NO|NUM|NUMERO|OFICIAL|EXT|EXTERIOR)\b", " ", t)
    if re.search(r"\bSN\b|\bSIN NUMERO\b", t) or compact(t) in ("SN", ""):
        return "SN" if t.strip() else ""
    m = re.search(r"\d+(?:\s*-?\s*[A-Z]\b)?", t)
    return compact(m.group(0)) if m else compact(t)


def a_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        from ocr_pipeline.normalize import parse_number

        return parse_number(str(v))


def diferencia_relativa(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b)) if max(abs(a), abs(b)) else 0.0


_ESTADOS_SUFIJO = re.compile(r"\b(ESTADO DE MEXICO|EDO MEX|ESTADO DE HIDALGO|HIDALGO|HGO|MEXICO|MEX)\b.*$")
_ESQUINA = re.compile(r"\bESQ(?:UINA)?\b(?:\s+CON)?|\bENTRE\b|\bY\b")


def norm_lugar(v) -> str:
    """Municipio/colonia sin el estado pegado: 'TEPEJI DEL RIO, HIDALGO' -> 'TEPEJI DEL RIO'."""
    t = norm_address(str(v))
    t = re.sub(r"^(MUNICIPIO|LOCALIDAD|COLONIA)\s+(DE\s+)?", "", t)
    return _ESTADOS_SUFIJO.sub("", t).strip() or t


def _sim_lugar(a, b) -> float:
    ta, tb = norm_lugar(a), norm_lugar(b)
    sa, sb = set(ta.split()) - {"DE", "DEL", "LA", "LOS", "LAS", "EL"}, set(tb.split()) - {"DE", "DEL", "LA", "LOS", "LAS", "EL"}
    if sa and sb and (sa <= sb or sb <= sa):
        return 1.0     # 'TEPEJI DEL RIO' ⊂ 'TEPEJI DEL RIO DE OCAMPO'
    return sim_texto(ta, tb)


def _sim_calle_esquina(a, b) -> float:
    """Predios en esquina: 'AV. INSURGENTES ESQUINA CON CALLE GLADIOLAS' coincide con cualquiera de las dos."""
    pa = [p for p in _ESQUINA.split(norm_address(str(a))) if p.strip()] or [norm_address(str(a))]
    pb = [p for p in _ESQUINA.split(norm_address(str(b))) if p.strip()] or [norm_address(str(b))]
    return max(sim_calle(x.strip(), y.strip()) for x in pa for y in pb)


def similitud(tipo: str, a, b) -> float | None:
    """0..1 (1 = mismo valor). None si falta alguno."""
    if a in (None, "", []) or b in (None, "", []):
        return None
    if tipo == "nombre":
        return sim_nombre(norm_name(str(a)), norm_name(str(b)))
    if tipo == "calle":
        return _sim_calle_esquina(a, b)
    if tipo == "texto":
        return _sim_lugar(a, b)
    if tipo == "estado":
        return 1.0 if norm_estado(str(a)) == norm_estado(str(b)) else 0.0
    if tipo == "exacto":
        return 1.0 if compact(str(a)) == compact(str(b)) else 0.0
    if tipo == "numero":
        na, nb = norm_numero(a), norm_numero(b)
        return 1.0 if na and na == nb else 0.0
    if tipo == "clave":
        da, db = digits_only(str(a)), digits_only(str(b))
        return sim_clave(da, db) if da and db else None
    if tipo == "cuenta":
        return 1.0 if norm_cuenta(str(a)) == norm_cuenta(str(b)) else 0.0
    if tipo == "digitos":
        return 1.0 if digits_only(str(a)) == digits_only(str(b)) else 0.0
    if tipo == "superficie":
        fa, fb = a_float(a), a_float(b)
        if not fa or not fb:
            return None
        rel = diferencia_relativa(fa, fb)
        return 1.0 if rel <= 0.005 else max(0.0, 1.0 - rel * 5)
    if tipo == "anio":
        bs = b if isinstance(b, list) else [b]
        try:
            return 1.0 if int(a) == max(int(x) for x in bs) else 0.0
        except (TypeError, ValueError):
            return None
    if tipo == "fecha":
        fa = parse_date(str(a)) or str(a)[:10]
        fb = parse_date(str(b)) or str(b)[:10]
        return 1.0 if fa == fb else 0.0
    return 1.0 if str(a) == str(b) else 0.0


def coincide(tipo: str, a, b) -> bool | None:
    s = similitud(tipo, a, b)
    if s is None:
        return None
    return s >= UMBRAL_COINCIDE.get(tipo, 0.99)
