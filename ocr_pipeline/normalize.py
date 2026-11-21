"""Normalización de texto y valores para comparar campos entre documentos."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
         "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}

# Abreviaturas frecuentes en direcciones (se aplican sobre texto ya en mayúsculas sin acentos).
ABREVIATURAS = [
    (r"\bAV(DA)?\b\.?", "AVENIDA"), (r"\bC\.(?=\s)", "CALLE"), (r"\bCALZ\b\.?", "CALZADA"),
    (r"\bCOL\b\.?", "COLONIA"), (r"\bFRACC?\b\.?", "FRACCIONAMIENTO"), (r"\bBO\b\.?", "BARRIO"),
    (r"\bCARR?\b\.?", "CARRETERA"), (r"\bCDA\b\.?", "CERRADA"), (r"\bPRIV\b\.?", "PRIVADA"),
    (r"\bBLVD?\b\.?", "BOULEVARD"), (r"\bNO\b\.?", "NUMERO"), (r"\bNUM\b\.?", "NUMERO"),
    (r"\bN[°º]", "NUMERO"), (r"#", " NUMERO "), (r"\bMZA?\b\.?", "MANZANA"), (r"\bLT\b\.?", "LOTE"),
    (r"\bEDO\b\.?", "ESTADO"), (r"\bMPIO\b\.?", "MUNICIPIO"), (r"\bSTA\b\.?", "SANTA"),
    (r"\bSN\b|\bS/N\b|\bSIN NUMERO\b", "SN"), (r"\bMA\b\.", "MARIA"), (r"\bMA\b(?=\s)", "MARIA"),
]

ESTADOS = {
    "HGO": "HIDALGO", "HIDALGO": "HIDALGO",
    "MEX": "MEXICO", "MEXICO": "MEXICO", "ESTADO DE MEXICO": "MEXICO", "EDOMEX": "MEXICO",
    "CDMX": "CIUDAD DE MEXICO", "CIUDAD DE MEXICO": "CIUDAD DE MEXICO",
    "QRO": "QUERETARO", "QUERETARO": "QUERETARO", "PUE": "PUEBLA", "PUEBLA": "PUEBLA",
    "TLAX": "TLAXCALA", "TLAXCALA": "TLAXCALA", "MOR": "MORELOS", "MORELOS": "MORELOS",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str | None) -> str:
    """Mayúsculas, sin acentos, sin signos (salvo / en S/N), espacios simples."""
    if not s:
        return ""
    s = strip_accents(s.upper()).replace("Ñ", "N")
    s = re.sub(r"[^\w/ ]", " ", s.replace("_", " "))
    return re.sub(r"\s+", " ", s).strip()


def compact(s: str | None) -> str:
    """Versión sin espacios para comparar."""
    return norm(s).replace(" ", "")


def norm_address(s: str | None) -> str:
    if not s:
        return ""
    t = strip_accents(s.upper())
    for pat, rep in ABREVIATURAS:
        t = re.sub(pat, rep, t)
    return norm(t)


def norm_name(s: str | None) -> str:
    """Nombre de persona: sin títulos (C., LIC., SR.), MA.->MARIA, sin signos."""
    if not s:
        return ""
    t = strip_accents(s.upper())
    t = re.sub(r"\bMA\b\.?", "MARIA", t)
    t = re.sub(r"\bJ\.?\s*JESUS\b", "JOSE DE JESUS", t)
    t = norm(t)
    t = re.sub(r"^(C|LIC|ING|ARQ|SR|SRA|SRITA|DR|DRA|PROF|C P)\s+", "", t)
    return t


_OCR_DIGITS = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1",
                             "i": "1", "S": "5", "B": "8", "Z": "2"})


def digits_only(s: str | None, ocr_fix: bool = True) -> str:
    if not s:
        return ""
    if ocr_fix:
        s = s.translate(_OCR_DIGITS)
    return re.sub(r"\D", "", s)


def norm_cuenta(s: str | None) -> str:
    """Cuenta predial tipo 'U-03410' / 'U0003410' -> 'U3410'."""
    m = re.match(r"\s*([A-Z]{1,2})\s*-?\s*0*(\d+)", (s or "").upper())
    return f"{m.group(1)}{m.group(2)}" if m else compact(s)


def parse_number(s: str | None) -> float | None:
    """'1,039.71' -> 1039.71 ; '536,82' -> 536.82 ; '783:20' -> 783.2."""
    if not s or not re.match(r"^\s*\$?\s*[\d.,]*\d", s):  # debe empezar con un número ("m2" no lo es)
        return None
    t = s.strip().replace(" ", "").replace(":", ".")
    t = re.sub(r"[^\d.,]", "", t)
    if not t or not any(c.isdigit() for c in t):
        return None
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else t.replace(",", "")
    elif t.count(".") > 1:
        head, _, tail = t.rpartition(".")
        t = f"{head.replace('.', '')}.{tail}"
    try:
        return float(t)
    except ValueError:
        return None


def parse_date(s: str | None) -> str | None:
    """'17 de febrero de 2025' | '26/01/2025' | '2024-03-25' -> '2025-02-17' (ISO)."""
    if not s:
        return None
    t = norm(s)
    m = re.search(r"\b(\d{1,2})\s+(?:DE\s+)?([A-Z]+)\s+(?:DE(?:L)?\s+)?(\d{4})\b", t)
    if m and m.group(2) in MESES:
        d, mo, y = int(m.group(1)), MESES[m.group(2)], int(m.group(3))
    else:
        m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", s) or None
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})", s)
            if not m:
                return None
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def norm_estado(s: str | None) -> str:
    t = norm(s)
    t = re.sub(r"^ESTADO DE ", "", t) if t not in ESTADOS else t
    return ESTADOS.get(t, ESTADOS.get(t.replace(" ", ""), t))
