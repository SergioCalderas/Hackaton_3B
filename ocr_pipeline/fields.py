"""Extracción de campos con regex + reglas por tipo de documento, y detección de tipo.

Cada campo extraído es un dict con el formato del modelo `Campo`:
  {"Valor", "Normalizado", "Pagina", "Evidencia", "Regla"}
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .normalize import (ESTADOS, compact, digits_only, norm, norm_address, norm_cuenta, norm_estado,
                        norm_name, parse_date, parse_number)

TIPOS = ("Predial", "Alineamiento", "Escritura", "UsoDeSuelo")

# ---------------------------------------------------------------------------
# Texto con páginas
# ---------------------------------------------------------------------------
@dataclass
class DocText:
    text: str
    page_starts: list[tuple[int, int]]  # (offset, número de página)

    @classmethod
    def from_pages(cls, pages: list[tuple[int, str]]) -> "DocText":
        parts, starts, off = [], [], 0
        for num, txt in pages:
            starts.append((off, num))
            parts.append(txt)
            off += len(txt) + 2
        return cls("\n\n".join(parts), starts)

    def page_at(self, offset: int) -> int | None:
        page = None
        for start, num in self.page_starts:
            if start <= offset:
                page = num
        return page

    def first_page_text(self) -> str:
        if len(self.page_starts) > 1:
            return self.text[: self.page_starts[1][0]]
        return self.text

    def evidence(self, start: int, end: int, ctx: int = 60) -> str:
        frag = self.text[max(0, start - ctx): min(len(self.text), end + ctx)]
        return re.sub(r"\s+", " ", frag).strip()


def _campo(doc: DocText, m: re.Match, valor: str, normalizado, regla: str, group: str = "v") -> dict:
    s, e = m.span(group) if group in (m.groupdict() or {}) else m.span()
    return {"Valor": valor.strip(), "Normalizado": normalizado, "Pagina": doc.page_at(s),
            "Evidencia": doc.evidence(s, e), "Regla": regla}


# ---------------------------------------------------------------------------
# Detección de tipo por contenido
# ---------------------------------------------------------------------------
KEYWORDS = {
    "Predial": [("IMPUESTO PREDIAL", 3), ("BOLETA PREDIAL", 3), ("PAGO DE PREDIAL", 3), ("TARJETA PREDIAL", 3),
                ("FORMATO UNIVERSAL DE PAGO", 2),
                ("RECIBO OFICIAL DE PAGO", 2), ("LINEA DE CAPTURA", 2), ("TOTAL PAGADO", 1),
                ("VALOR CATASTRAL", 1), ("TESORERIA", 1), ("CFDI", 1), ("FOLIO FISCAL", 1), ("RECAUDA", 1)],
    "Alineamiento": [("ALINEAMIENTO", 3), ("NUMERO OFICIAL", 3), ("ALINEACION", 2), ("LINEAMIENTO", 2), ("CROQUIS", 1),
                     ("RESTRICCION", 1), ("PARAMENTO", 1)],
    "Escritura": [("NOTARIO", 2), ("NOTARIA", 2), ("ESCRITURA", 2), ("INSTRUMENTO", 1), ("VOLUMEN", 1),
                  ("COMPRAVENTA", 2), ("DOY FE", 2), ("ANTECEDENTES", 1), ("CLAUSULAS", 2), ("PROTOCOLO", 1),
                  ("TESTIMONIO", 1), ("TITULO DE PROPIEDAD", 3), ("REGISTRO AGRARIO", 1), ("DONACION", 1)],
    "UsoDeSuelo": [("USO DE SUELO", 3), ("USO DEL SUELO", 3), ("LICENCIA DE USO", 3), ("USOS DE SUELO", 3),
                   ("COEFICIENTE DE OCUPACION", 1), ("CAJONES DE ESTACIONAMIENTO", 1), ("DENSIDAD", 1),
                   ("PLAN MUNICIPAL DE DESARROLLO URBANO", 1), ("GIRO", 1), ("COS", 1), ("CUS", 1)],
}


def detectar_tipo(doc: DocText, declarado: str | None = None) -> tuple[str | None, dict[str, float]]:
    """Puntaje por palabras clave; la primera página pesa el triple (las escrituras
    citan predial/uso de suelo en sus anexos, y hay PDFs con anexos de otro tipo).

    Si el tipo declarado queda a menos de 20 % del mejor, se respeta el declarado
    (evita falsas discrepancias por anexos)."""
    first, rest = norm(doc.first_page_text()), norm(doc.text[len(doc.first_page_text()):])
    scores = {}
    for tipo, kws in KEYWORDS.items():
        s = 0.0
        for kw, w in kws:
            pat = rf"\b{kw}\b"
            s += w * (3 * min(len(re.findall(pat, first)), 3) + min(len(re.findall(pat, rest)), 3))
        scores[tipo] = s
    best = max(scores, key=scores.get)
    if scores[best] < 4:
        return None, scores
    if declarado in scores and scores[declarado] >= 0.8 * scores[best]:
        return declarado, scores
    return best, scores


# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------
U = "A-ZÁÉÍÓÚÑÜ"
NAME = rf"(?P<v>[{U}][{U}\.]+(?:[ \t]+(?:DE|DEL|LA|LAS|LOS|Y|[{U}][{U}\.]+)){{1,7}})"
NAME_TC = r"(?P<v>[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|los|y|[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)){1,6})"
NAME_STOP = {"R", "RFC", "AL", "EN", "CON", "PRESENTE", "ESTA", "QUE", "POR", "PARA", "FIRMA", "SU",
             "DOMICILIO", "UBICACION", "CLAVE", "MEXICANA", "MAYOR", "COMO", "QUIEN", "QUIENES", "EL", "LE",
             "COLONIA", "CALLE", "CURP", "LOCALIDAD", "ESTADO", "SUPERFICIE", "USO", "GIRO", "FECHA",
             "TELEFONO", "MUNICIPIO", "PROPIETARIO", "POSEEDOR", "APELLIDO", "NOMBRE", "IDENTIFICADO",
             "REPRESENTADA", "REPRESENTADO", "QUIEN", "VENDE", "COMPRA", "NACIONALIDAD"}
NO_PERSONA = re.compile(r"\b(REGISTRADOR|DIRECTOR|PRESIDENTE|TESORER|NOTARIO|SECRETARI|SINDICO|REGIDOR|"
                        r"ENCARGAD|JEFE|COORDINADOR|SUBDIRECTOR|TITULAR|AYUNTAMIENTO|MUNICIPIO|GOBIERNO|"
                        r"QUIEN SE ENCUENTRE|CONTRIBUYENTES CUMPLIDOS|COMUNIDAD|SOLICITANTE|INTERESADO|"
                        r"CONTRIBUYENTE|PROPIETARIO|POSEEDOR|REPRESENTANTE|APODERADO|BENEFICIARIO|RAZON SOCIAL)\b")


def _clean_name(raw: str) -> str | None:
    words = raw.replace("\n", " ").split()
    out = []
    for w in words:
        if norm(w) in NAME_STOP and len(out) >= 2:
            break
        out.append(w)
    while out and norm(out[-1]) in {"DE", "DEL", "LA", "LOS", "LAS", "Y"} | NAME_STOP:
        out.pop()
    while out and norm(out[0]) in {"DE", "DEL", "LA", "LOS", "LAS", "Y"}:
        out.pop(0)
    name = " ".join(out).strip(" .,:;")
    if len(name.split()) < 2 or NO_PERSONA.search(norm(name)):
        return None
    return name


PROPIETARIO_RULES = [
    ("propietario/poseedor", rf"PROPIETARIO\s*/\s*POSEEDOR\s*:?\s*{NAME}"),
    ("nombre del propietario", rf"(?i:NOMBRE\s+DEL\s+PROPIETARIO(?:\s*\(S\))?(?:\s+O\s+POSEEDOR)?)\s*[:.\-]?\s*(?:C\.\s*)?{NAME}"),
    ("poseedor", rf"(?i:POSEEDOR)\s*:\s*(?:C\.\s*)?{NAME}"),
    ("posesionario", rf"(?i:POSESIONARIO(?:\s+LEGAL)?)\s*:\s*(?:C\.\s*)?{NAME}"),
    ("propietario(s)", rf"(?i:PROPIETARIO(?:\s*\(S\))?)\s*:\s*(?:C\.\s*)?{NAME}"),
    ("comprador", rf"(?i:COMPRADOR(?:A|\(A\))?)[”\"’']?\s*,?\s*(?i:(?:el|la)\s+se[ñn]or(?:a)?\s+)?{NAME}"),
    ("adquiere", rf"\by\s+{NAME}\s+(?i:compra\s+y\s+adquiere)"),
    ("donatario", rf"(?i:DONATARI[OA])[”\"’']?\s*,?\s*(?i:(?:el|la)\s+se[ñn]or(?:a)?\s+)?{NAME}"),
    ("nombre", rf"(?m:^\s*NOMBRE\s*[:.]?\s+){NAME}"),
    ("datos del propietario (etiqueta abajo)", rf"(?i:DATOS\s+DEL\s+PROPIETARIO)\s*:?\s*\n\s*{NAME}"),
    ("receptor", rf"RECEPTOR\s*:\s*[:.]?\s*{NAME}"),
    ("contribuyente", rf"CONTRIBUYENTE\s*:?\s*\n?\s*{NAME}"),
    ("a nombre de", rf"(?i:A\s+NOMBRE\s+DE)\s*:?\s*{NAME}"),
    ("destinatario C.", rf"(?m:^\s*C\.\s+){NAME}"),
    ("el C. (minúsculas)", rf"\b(?:el|la|al|del)\s+C\.\s+{NAME_TC}"),
]

VENDEDOR_RULES = [
    ("vendedor", rf"(?i:VENDEDOR(?:A|\(A\))?)[”\"’']?\s*,?\s*(?i:(?:el|la)\s+se[ñn]or(?:a)?\s+)?{NAME}"),
    ("vende", rf"{NAME}\s+(?i:vende)\b"),
    ("donante", rf"(?i:DONANTE)[”\"’']?\s*,?\s*{NAME}"),
]

# Formularios con la etiqueta DEBAJO del valor (Formato Universal de Pago Edomex):
#   0060140707000000 SOR JUANA INES DE LA CRUZ S/N LT 7, COL, RICARDO
#   CLAVE CATASTRAL   UBICACIÓN DEL PREDIO
LABEL_BELOW_CLAVE_RE = re.compile(
    r"(?m)^[ \t]*(?P<v>\d{13,16})[ \t]+(?P<dir>[^\n]{4,160}(?:\n[ \t]*\n?(?![ \t]*CLAVE)[^\n]{1,80})?)"
    r"[ \t]*\n\s*(?i:CLAVE\s+CAT)")
LABEL_BELOW_RULES = [
    ("datos del predio (etiqueta abajo)",
     r"(?i:DATOS\s+DEL\s+PREDIO)\s*:?\s*\n(?P<v>[^\n]{4,160})\n\s*(?i:Calle\s+N[uú]mero)"),
]
CLAVE_RE = re.compile(
    r"(?i:CLAVE\s+(?:UNICA\s+)?CAT\w{3,7}L(?:\s+(?:ACTUAL|N[UÚ]MERO))?|\bClave\s*(?=:\s*\d))"
    r"(?P<ant>\s+ANTERIOR)?[\s:;.|_—\-–“\"]*(?P<v>[\dOoIl|][\dOoIl| \t\-–\.]{4,40}(?:\n[ \t]*[\dOo][\d \t\-–\.]{0,20})?)")
CUENTA_RE = re.compile(
    r"(?i:CUENTA\s+PREDIAL(?:\s+NO\.?)?|N[UÚ]MERO\s+DE\s+CUENTA(?:\s+PREDIAL)?|PREDIAL\s+NO\.?|\bPREDIO)"
    r"\s*[:.]?\s*(?P<v>[A-Z]{1,2}\s*-?\s*\d{3,8})\b")
CUENTA_BELOW_RE = re.compile(r"(?P<v>\b[A-Z]-?\d{4,7})\s*\n\s*(?i:Municipio\s+Cuenta\s+Predial)")

DIRECCION_RULES = [
    ("ubicacion en", r"(?i:con\s+ubicaci[oó]n\s*(?:en)?)\s*[:;]?\s*(?P<v>.{8,220}?)(?=(?i:\.\s+CLAVE|\s*CLAVE\s+CAT)|\.\s*\n|\n\s*\n|$)"),
    ("inmueble ubicado en", r"(?i:(?:inmueble|predio|terreno)\s+ubicado\s+en)\s*[:;]?\s*(?P<v>.{8,220}?)(?=(?i:,?\s+con\s+superficie|,?\s+identificado|\.\s+CLAVE|\s+actualmente)|\.\s*\n|\n\s*\n|$)"),
    ("ubicacion del predio", r"(?i:UBICACI[OÓ]N(?:\s+DETALLADA)?\s+DEL\s+PREDIO)\s*[:.]?\s*(?P<v>[^\n]{6,160})"),
    ("direccion del predio", r"(?i:DIRECCI[OÓ]N\s+DEL\s+PREDIO)\s*:\s*(?P<v>[^\n]{6,200}(?:\n[^\n]{0,80})?)"),
    ("UBICACION", r"(?m:^\s*UBICACI[OÓ]N)\s*:?\s+(?P<v>[^\n]{6,160})"),
    ("DOMICILIO", r"(?m:^\s*DOMICILIO)(?!\s+DEL\s+RECEPTOR)\s*[:.]?\s+(?P<v>[^\n]{6,160})"),
]

SUP_TERRENO_RULES = [
    ("superficie terreno", r"(?i:SUPERFICIE\s+(?:DE(?:L)?\s+)?(?:TERRENO|PREDIO)(?:\s+PROPIO)?(?:\s*\(M2\))?)\s*[:|\-—_ ]*\s*(?P<v>\d[\d,.: ]*\d)"),
    ("sup.", r"(?i:\bSUP\.)\s*(?P<v>\d[\d,.]*\d)\s*(?i:m)"),
    ("con superficie de", r"(?i:(?:con\s+)?superficie(?:\s+total)?\s+de)\s*(?P<v>\d[\d,.]*\d)\s*(?i:m|metros)"),
    ("superficie total", r"(?i:SUPERFICIE\s+TOTAL)\s*[:|]?\s*(?P<v>\d[\d,.]*\d)"),
]
SUP_CONSTR_RE = re.compile(
    r"(?i:SUPERFICIE\s+(?:DE\s+)?CONSTRUCCI[OÓ]N(?:\s+PROPIA)?(?:\s*\(M2\))?)\s*[:|\-—_ ]*\s*(?P<v>\d[\d,.]*\d|\d)")

ESCRITURA_RE = re.compile(
    r"(?i:(?:ESCRITURA(?:\s+P[UÚ]BLICA)?|INSTRUMENTO(?:\s+NOTARIAL)?)\s+(?:N[UÚ]MERO|NO\.?|N[°º]\.?))"
    r"\s*[:.\-]*\s*(?P<v>\d[\d,.]*\d|\d)")
VOLUMEN_RE = re.compile(r"(?i:\bVOLUMEN)\s*(?i:N[UÚ]MERO|NO\.?)?\s*[:.\-]*\s*(?P<v>\d[\d,.]*|[IVXLC]{2,})")
FOLIO_RE = re.compile(
    r"(?i:\bFOLIO(?:\s+REAL(?:\s+ELECTR[OÓ]NICO)?|\s+FISCAL)?|N[°º*?]*\.?\s*DE\s+OFICIO|OFICIO\s+N[OÚ]\.?)"
    r"\s*[:.]?\s*(?P<v>[A-Z0-9][A-Z0-9/\-]{2,40})")

FECHA_RULES = [
    ("fecha de expedicion", r"(?i:FECHA\s+DE\s+(?:EXPEDICI[OÓ]N|EMISI[OÓ]N|PAGO))\s*:?\s*(?P<v>\d{1,2}\s*(?:DE\s+)?[A-Za-z]+\s+(?:DE(?:L)?\s+)?\d{4}|\d{1,2}/\d{1,2}/\d{4})"),
    ("lugar y fecha", r"(?i:,\s*a\s+)(?P<v>\d{1,2}\s+de\s+[A-Za-záéíóú]+\s+(?:de(?:l)?\s+)?\d{4})"),
    ("fecha dd/mm/aaaa", r"(?i:FECHA[^\n:]{0,20}:?)\s*(?P<v>\d{1,2}/\d{1,2}/\d{4})"),
    ("primera fecha", r"(?P<v>\b\d{1,2}\s+de\s+(?i:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de(?:l)?\s+)?\d{4})"),
]

EJERCICIO_RULES = [
    ("ejercicio", r"(?i:EJERCICIO(?:\s+FISCAL)?)\s*:?\s*(?P<v>20\d{2})"),
    ("periodo pagado", r"(?i:PERIODO(?:\s+(?:PAGADO|DE\s+PAGO))?)\s*:?\s*(?:\d{2}-)?(?P<v>20\d{2})"),
    ("predial ene-dic", r"(?i:PREDIAL\s+(?:ENE-DIC\s+)?)(?P<v>20\d{2})"),
    ("tabla año", r"(?m:^\s*(?P<v>20\d{2})\s+(?:\d{1,2}\s+\d{1,2}|ENERO|Enero))"),
]

MUNICIPIO_HEADER_RE = re.compile(
    r"(?i:(?:H\.\s*)?AYUNTAMIENTO(?:\s+CONSTITUCIONAL)?\s+DE|MUNICIPIO\s+DE|PRESIDENCIA\s+MUNICIPAL\s+DE)"
    r"\s+(?P<v>[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ ]{2,40}?)(?=\s*[,.\n]|\s+(?i:ESTADO|EDO|HGO|M[EÉ]X|C\.P))")


# ---------------------------------------------------------------------------
# Extracción de campos individuales
# ---------------------------------------------------------------------------
def _clave(doc: DocText) -> dict | None:
    cands = []
    for m in CLAVE_RE.finditer(doc.text):
        raw = m.group("v")
        first_line, _, rest = raw.partition("\n")
        d1 = digits_only(re.sub(r"[^\dOoIl| \-–.]", "", first_line))
        digits = d1
        if rest and len(d1) not in (10, 16) and len(d1) < 16:
            digits = (d1 + digits_only(rest))[:16]
            raw = first_line + " " + rest.strip()
        else:
            raw = first_line
        if not 8 <= len(digits) <= 20 or set(digits) == {"0"}:
            continue
        cands.append((m, raw.strip(" .-–"), digits, bool(m.group("ant"))))
    for m in LABEL_BELOW_CLAVE_RE.finditer(doc.text):
        if set(m.group("v")) != {"0"}:
            cands.append((m, m.group("v"), m.group("v"), False))
    if not cands:
        return None
    current = [c for c in cands if not c[3]] or cands
    freq = Counter(c[2] for c in current)
    m, raw, digits, _ = max(current, key=lambda c: (freq[c[2]], len(c[2]) == 16, -c[0].start()))
    campo = _campo(doc, m, raw, digits, "clave catastral")
    others = sorted({c[2] for c in current} - {digits})
    if others:
        campo["Regla"] += f" (otras claves en el documento: {', '.join(others)})"
    return campo


def _first_rule(doc: DocText, rules, normalizer, validator=None, flags=0) -> dict | None:
    for regla, pat in rules:
        for m in re.finditer(pat, doc.text, flags):
            val = m.group("v")
            nv = normalizer(val)
            if nv in (None, "") or (validator and not validator(val, nv)):
                continue
            return _campo(doc, m, val, nv, regla)
    return None


def _propietario(doc: DocText, tipo: str | None) -> dict | None:
    rules = PROPIETARIO_RULES
    if tipo == "Escritura":  # en escrituras manda el adquirente (los anexos citan al dueño anterior)
        prio = {"comprador": 0, "adquiere": 1, "donatario": 2}
        rules = sorted(rules, key=lambda r: prio.get(r[0], 9))
    for regla, pat in rules:
        for m in re.finditer(pat, doc.text):
            name = _clean_name(m.group("v"))
            if name:
                return _campo(doc, m, name, norm_name(name), regla)
    return None


def _vendedor(doc: DocText) -> dict | None:
    for regla, pat in VENDEDOR_RULES:
        for m in re.finditer(pat, doc.text):
            name = _clean_name(m.group("v"))
            if name:
                return _campo(doc, m, name, norm_name(name), regla)
    return None


def _parse_address(addr: str) -> dict[str, str]:
    """Separa una dirección (ya normalizada con abreviaturas) en componentes."""
    a = norm_address(addr)
    out: dict[str, str] = {}
    m = re.search(r"\bNUMERO(?:\s+OFICIAL)?\s+(SN|\d+[A-Z]?)\b", a) or re.search(r"\bKM\s+\d+(?:\s+\d+)?\b", a)
    if m:
        out["NumeroOficial"] = m.group(1) if m.lastindex else m.group(0)
    elif re.search(r"\bSN\b", a):
        out["NumeroOficial"] = "SN"
    m = re.search(r"\bLOTE\s+(\d+[A-Z]?)", a)
    if m:
        out["Lote"] = m.group(1)
    m = re.search(r"\bMANZANA\s+(\d+[A-Z\-]*)", a)
    if m:
        out["Manzana"] = m.group(1)
    m = re.search(r"\b(?:COLONIA|BARRIO|FRACCIONAMIENTO)\s*:?\s+(.+?)(?=\s+(?:MUNICIPIO|LOCALIDAD|CP|C P|CODIGO|ESTADO|CALLE|NUMERO|LOTE|MANZANA)\b|$)", a)
    if m:
        out["Colonia"] = re.sub(r"^DE\s+", "", m.group(1).strip())
    m = re.search(r"\bMUNICIPIO\s+(?:DE\s+)?(.+?)(?=\s+(?:ESTADO|CP|C P|CODIGO|COLONIA|HIDALGO|MEXICO|HGO|MEX)\b|$)", a)
    if m and 1 <= len(m.group(1).split()) <= 5:
        out["Municipio"] = m.group(1).strip()
    m = re.search(r"\bESTADO\s*:?\s+(?:DE\s+)?([A-Z]+(?:\s+DE\s+[A-Z]+)?)", a) or \
        re.search(r"\b(HIDALGO|MEXICO|HGO|MEX)\b", a)
    if m and norm_estado(m.group(1)) in ESTADOS.values():
        out["Estado"] = norm_estado(m.group(1))
    m = re.search(r"\b(?:CP|C P|CODIGO POSTAL)\s*:?\s*(\d{5})\b", a)
    if m:
        out["CodigoPostal"] = m.group(1)
    # Calle: lo que hay antes del primer separador (número, lote, colonia...)
    m = re.search(r"\bCALLE\s*:\s*([A-Z0-9 ]+?)(?=\s+NUMERO|\s+NUM|$)", a)  # formato CFDI "CALLE: X"
    calle = m.group(1) if m else re.split(
        r"\s+(?:NUMERO|SN|LOTE|MANZANA|COLONIA|BARRIO|FRACCIONAMIENTO|MUNICIPIO|ESTADO|CP|ESQUINA|ESQ)\b|\s+\d", a, 1)[0]
    calle = re.sub(r"^(?:COMUNIDAD\s+\S+(?:\s+\S+)?\s+)", "", calle).strip()
    if (calle and len(calle) >= 3 and len(calle.split()) <= 8
            and not re.match(r"^(COLONIA|MUNICIPIO|COMUNIDAD|UBICAD|EN\b|EL\b|LA\b|DE\b|DENOMINAD|PREDIO|TERRENO)", calle)):
        out["Calle"] = calle
    # "FRESNO 28 COLONIA LA LOMA": número pegado al nombre de la calle sin "No."
    if "NumeroOficial" not in out:
        m = re.match(r"^(?:CALLE\s+|AVENIDA\s+)?(?:(?!LOTE\b|MANZANA\b|KM\b)[A-Z ]){3,40}?\s+(\d{1,5})\b(?!\s*(?:M2|M|METROS))", a)
        if m:
            out["NumeroOficial"] = m.group(1)
    return out


def _municipio_header(doc: DocText) -> dict | None:
    for m in MUNICIPIO_HEADER_RE.finditer(doc.first_page_text()):
        val = re.sub(r"(?i)\s+(HIDALGO|M[EÉ]XICO|HGO|MEX)\.?$", "", m.group("v").strip())
        if 1 <= len(val.split()) <= 5 and not re.search(r"(?i)\b(QUIEN|ESTE|DICHO|REFERENCIA|SE|LO|QUE)\b", val):
            return _campo(doc, m, val, norm(val), "encabezado del emisor")
    return None


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------
def extraer_campos(pages: list[tuple[int, str]], tipo: str | None) -> dict[str, dict]:
    """pages: [(número de página, texto)]. Devuelve {NombreCampo: Campo}."""
    doc = DocText.from_pages(pages)
    campos: dict[str, dict | None] = {}

    campos["ClaveCatastral"] = _clave(doc)
    campos["CuentaPredial"] = _first_rule(doc, [("cuenta predial", CUENTA_RE.pattern),
                                                ("cuenta predial (etiqueta abajo)", CUENTA_BELOW_RE.pattern)],
                                          norm_cuenta, validator=lambda v, n: any(c.isdigit() for c in n))
    campos["Propietario"] = _propietario(doc, tipo)
    if tipo == "Escritura":
        campos["Vendedor"] = _vendedor(doc)

    label_below = [("ubicacion (etiqueta abajo)", LABEL_BELOW_CLAVE_RE.pattern.replace("(?P<v>", "(?P<c>").replace("(?P<dir>", "(?P<v>"))]
    direccion = _first_rule(doc, label_below + LABEL_BELOW_RULES + DIRECCION_RULES, norm_address,
                            validator=lambda v, n: not re.match(r"^(EL\s+)?MUNICIPIO\b", n) and len(n.split()) >= 2,
                            flags=re.S)
    campos["Direccion"] = direccion
    if direccion:
        for k, v in _parse_address(direccion["Valor"]).items():
            campos[k] = {**direccion, "Valor": v, "Normalizado": v, "Regla": f"componente de dirección ({direccion['Regla']})"}

    # Municipio del emisor: válido para trámites municipales (no para escrituras: la notaría puede estar en otro lado).
    if not campos.get("Municipio") and tipo in ("Predial", "Alineamiento", "UsoDeSuelo"):
        campos["Municipio"] = _municipio_header(doc)
    # Mención genérica "Estado de X" en la 1a página: solo en trámites (las escrituras citan otros estados).
    if not campos.get("Estado") and tipo != "Escritura":
        m = re.search(r"(?i:ESTADO\s+DE)\s+(?P<v>M[EÉ]XICO|HIDALGO)\b", doc.first_page_text())
        if m:
            campos["Estado"] = _campo(doc, m, m.group("v"), norm_estado(m.group("v")), "mención 'Estado de'")

    campos["SuperficieTerreno"] = _first_rule(
        doc, SUP_TERRENO_RULES, parse_number, validator=lambda v, n: n is not None and 10 <= n <= 10_000_000)
    campos["SuperficieConstruccion"] = _first_rule(
        doc, [("superficie construccion", SUP_CONSTR_RE.pattern)], parse_number,
        validator=lambda v, n: n is not None and n < 1_000_000)

    if tipo == "Escritura":
        campos["NumeroEscritura"] = _first_rule(doc, [("escritura/instrumento numero", ESCRITURA_RE.pattern)],
                                                digits_only, validator=lambda v, n: len(n) >= 2)
        campos["Volumen"] = _first_rule(doc, [("volumen", VOLUMEN_RE.pattern)], lambda v: compact(v).strip(".,"),
                                        validator=lambda v, n: n not in ("", "0"))
    campos["Folio"] = _first_rule(doc, [("folio/oficio", FOLIO_RE.pattern)], compact,
                                  validator=lambda v, n: any(c.isdigit() for c in n))
    campos["FechaDocumento"] = _first_rule(doc, FECHA_RULES, parse_date)

    if tipo == "Predial":
        years = []
        first = None
        for regla, pat in EJERCICIO_RULES:
            for m in re.finditer(pat, doc.text):
                y = m.group("v")
                if 2000 <= int(y) <= 2100 and y not in years:
                    years.append(y)
                    first = first or (m, regla)
        if not years and campos.get("FechaDocumento"):
            years = [campos["FechaDocumento"]["Normalizado"][:4]]
            campos["EjercicioFiscal"] = {**campos["FechaDocumento"], "Valor": years[0], "Normalizado": years,
                                         "Regla": "año de la fecha del recibo"}
        elif years:
            m, regla = first
            campos["EjercicioFiscal"] = _campo(doc, m, ", ".join(years), sorted(years), regla)

    return {k: v for k, v in campos.items() if v}


CAMPOS_CLAVE = ("ClaveCatastral", "CuentaPredial", "Calle", "Propietario", "SuperficieTerreno")


def campos_utiles(campos: dict) -> bool:
    """Hay algo con qué hacer matching (sin esto el documento no se fuerza)."""
    return any(k in campos for k in CAMPOS_CLAVE)
