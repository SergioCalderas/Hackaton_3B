"""Trazabilidad: localiza un valor extraído dentro del texto OCR y devuelve página + cita literal.

El LLM solo devuelve valores; aquí se verifica que cada valor exista en el documento (tolerando
acentos, mayúsculas, espacios y errores típicos de OCR) y se toma la cita del texto ORIGINAL.
Una evidencia con verificada=False significa que el valor no se encontró en el texto: el front
debe mostrarla como "no verificada".
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from rapidfuzz import fuzz

from ocr_pipeline.normalize import MESES

from .esquemas import Evidencia

_MES_NOMBRE = {v: k for k, v in MESES.items() if k != "SETIEMBRE"}


def _base(ch: str) -> str:
    d = unicodedata.normalize("NFD", ch)
    c = d[0].upper() if d else ""
    return c if c.isalnum() else " "


def normalizar_con_mapa(texto: str) -> tuple[str, list[int]]:
    """Texto en mayúsculas, sin acentos ni signos y con espacios simples, más un mapa
    posición-normalizada -> posición-original para recuperar la cita literal."""
    out: list[str] = []
    mapa: list[int] = []
    espacio = True
    for i, ch in enumerate(texto):
        c = _base(ch)
        if c == " ":
            if espacio:
                continue
            espacio = True
        else:
            espacio = False
        out.append(c)
        mapa.append(i)
    if out and out[-1] == " ":
        out.pop()
        mapa.pop()
    return "".join(out), mapa


def normalizar(s: str) -> str:
    return normalizar_con_mapa(s)[0]


class TextoDocumento:
    """Páginas de un documento con su versión normalizada (se calcula una vez)."""

    def __init__(self, ruta: str, tipo: str | None, paginas: list[tuple[int, str]]):
        self.ruta = ruta
        self.tipo = tipo
        self.paginas = [(n, t or "") for n, t in paginas]
        self._norm = {n: normalizar_con_mapa(t or "") for n, t in self.paginas}

    @classmethod
    def desde_documento(cls, doc: dict) -> "TextoDocumento":
        return cls(doc.get("RutaArchivo") or doc.get("NombreArchivo") or "", doc.get("TipoDocumento"),
                   [(p["Numero"], p.get("Texto") or "") for p in doc.get("Paginas", [])])

    def cita(self, pagina: int, ini: int, fin: int, contexto: int = 70) -> str:
        texto = dict(self.paginas)[pagina]
        a, b = max(0, ini - contexto), min(len(texto), fin + contexto)
        frag = re.sub(r"\s+", " ", texto[a:b]).strip()
        return ("…" if a > 0 else "") + frag + ("…" if b < len(texto) else "")

    def buscar(self, candidatos: list[str], umbral: float = 85.0,
               paginas_preferidas: list[int] | None = None) -> tuple[int, int, int, float] | None:
        """Primera coincidencia según el ORDEN de los candidatos (el primero es el más específico):
        (página, ini, fin, puntaje). Valores cortos: coincidencia exacta por palabra; largos: exacta
        y, si no, difusa (tolera errores de OCR) con puntaje >= umbral."""
        orden = list(dict.fromkeys((paginas_preferidas or []) + [n for n, _ in self.paginas]))
        for cand in candidatos:
            c = normalizar(cand)
            if not c:
                continue
            exacto = re.compile(rf"(?<![A-Z0-9]){re.escape(c)}(?![A-Z0-9])")
            mejor = None
            for n in orden:                       # 1) exacta, en el orden de páginas preferido
                nt, mapa = self._norm.get(n, ("", []))
                if nt and (m := exacto.search(nt)):
                    mejor = (n, mapa[m.start()], mapa[m.end() - 1] + 1, 100.0)
                    break
            if mejor is None and len(c) > 5:      # 2) difusa
                for n in orden:
                    nt, mapa = self._norm.get(n, ("", []))
                    if not nt:
                        continue
                    al = fuzz.partial_ratio_alignment(c, nt, score_cutoff=umbral)
                    if al and al.dest_end > al.dest_start and (mejor is None or al.score > mejor[3] + 0.5):
                        mejor = (n, mapa[al.dest_start], mapa[al.dest_end - 1] + 1, al.score)
            if mejor:
                return mejor
        return None

    def buscar_digitos(self, digitos: str, paginas_preferidas: list[int] | None = None):
        """Claves numéricas con separadores arbitrarios: '1120314518000000' ~ '112 03 145 18 00 0000'."""
        if len(digitos) < 6:
            return None
        patron = re.compile(r"(?<!\d)" + r" ?".join(digitos) + r"(?!\d)")
        for n in list(dict.fromkeys((paginas_preferidas or []) + [n for n, _ in self.paginas])):
            nt, mapa = self._norm.get(n, ("", []))
            if nt and (m := patron.search(nt)):
                return n, mapa[m.start()], mapa[m.end() - 1] + 1, 100.0
        return None


# ---------------------------------------------------------------------------------------
# Candidatos de búsqueda por tipo de valor
# ---------------------------------------------------------------------------------------
def candidatos_numero(x: float) -> list[str]:
    ent = int(round(x))
    out = [f"{x:,.2f}", f"{x:.2f}", f"{x:.2f}".replace(".", ","), f"{x:,.1f}"]
    if abs(x - ent) < 1e-9:
        out += [f"{ent:,}", str(ent)]
    return list(dict.fromkeys(out))


def candidatos_fecha(iso: str) -> list[str]:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return [iso]
    mes = _MES_NOMBRE[d.month]
    return [f"{d.day:02d} de {mes} de {d.year}", f"{d.day} de {mes} de {d.year}", f"{d.day:02d} de {mes} del {d.year}",
            f"{d.day:02d}/{d.month:02d}/{d.year}", f"{d.day}/{d.month}/{d.year}", d.isoformat()]


def candidatos(campo: str, valor, extras: dict | None = None) -> list[str]:
    extras = extras or {}
    if valor is None or valor == "" or valor == []:
        return []
    if isinstance(valor, bool):
        return []
    if isinstance(valor, (int, float)) and campo != "ejercicio_fiscal":
        return candidatos_numero(float(valor))
    v = str(valor).strip()
    if campo.startswith("fecha") and re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return candidatos_fecha(v)
    if campo == "numero":
        calle = extras.get("calle")
        sn = re.sub(r"[^A-Z0-9]", "", v.upper()) in ("SN", "SINNUMERO")
        base = ["S/N", "SN", "SIN NUMERO"] if sn else [v]
        pre = [f"{calle} No. {b}" for b in base] + [f"{calle} {b}" for b in base] if calle else []
        return pre + [f"NÚMERO OFICIAL: {b}" for b in base] + [f"No. {b}" for b in base] + base
    if campo == "clave_catastral":
        digitos = re.sub(r"\D", "", v)
        return [v, digitos] if digitos and digitos != v else [v]
    return [v]


UMBRAL_CAMPO = {"numero": 93.0, "clave_catastral": 90.0, "cuenta_predial": 90.0, "ejercicio_fiscal": 100.0}


def localizar(texto: TextoDocumento, campo: str, valor, extras: dict | None = None,
              paginas_preferidas: list[int] | None = None, umbral: float | None = None) -> Evidencia:
    """Evidencia para `valor` (verificada si se encontró en el texto)."""
    umbral = umbral if umbral is not None else UMBRAL_CAMPO.get(campo, 85.0)
    cands = candidatos(campo, valor, extras)
    valor_txt = None if valor is None else (", ".join(valor) if isinstance(valor, list) else str(valor))
    if cands:
        r = texto.buscar(cands, umbral=umbral, paginas_preferidas=paginas_preferidas)
        if r is None and campo in ("clave_catastral", "cuenta_predial", "folio_real", "numero_escritura"):
            r = texto.buscar_digitos(re.sub(r"\D", "", str(valor)), paginas_preferidas)
        if r is None and isinstance(valor, str) and re.search(r",|;| - ", valor):
            # valor compuesto por el LLM a partir de varias líneas: se localiza su parte más larga
            partes = sorted((p.strip() for p in re.split(r",|;| - ", valor)), key=len, reverse=True)
            r = texto.buscar([p for p in partes if len(p) >= 8][:2], umbral=umbral,
                             paginas_preferidas=paginas_preferidas)
        if r:
            n, ini, fin, _ = r
            return Evidencia(documento=texto.ruta, tipo_documento=texto.tipo, pagina=n,
                             cita=texto.cita(n, ini, fin), valor=valor_txt, verificada=True)
    return Evidencia(documento=texto.ruta, tipo_documento=texto.tipo, pagina=None, cita="",
                     valor=valor_txt, verificada=False)


def evidencia_de_campo_reglas(doc: dict, campo_equipo: str) -> Evidencia | None:
    """Evidencia que ya trae el extractor por reglas del equipo (CamposExtraidos)."""
    c = (doc.get("CamposExtraidos") or {}).get(campo_equipo)
    if not c:
        return None
    return Evidencia(documento=doc.get("RutaArchivo", ""), tipo_documento=doc.get("TipoDocumento"),
                     pagina=c.get("Pagina"), cita="…" + c.get("Evidencia", "") + "…", valor=str(c.get("Valor")),
                     verificada=c.get("Pagina") is not None)
