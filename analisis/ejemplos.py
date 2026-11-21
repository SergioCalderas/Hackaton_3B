"""Expedientes de ejemplo armados con los documentos del reto (para el visor y las pruebas).

Los cuatro "Sintético" son los juegos 01-04 del reto (documentos marcados SIN VALIDEZ OFICIAL),
cada uno con su problema plantado. Los demás se armaron por el nombre de archivo.
"""
from __future__ import annotations

from pathlib import Path

from .config import RAIZ

E, P, A, U = "Escritura", "Predial", "Alineamiento_y_Numero_Oficial", "Uso_de_suelo"


def _sintetico(sufijo: str) -> list[tuple[str, str]]:
    return [(f"{E}/01 Escritura{sufijo}.pdf", "Escritura"), (f"{P}/02 Predial{sufijo}.pdf", "Predial"),
            (f"{A}/03 Alineamiento y Numero Oficial{sufijo}.pdf", "Alineamiento"),
            (f"{U}/04 Licencia de Uso de Suelo{sufijo}.pdf", "UsoDeSuelo")]


EXPEDIENTES: dict[str, dict] = {
    "Sintético A · datos coherentes, uso habitacional": {
        "archivos": _sintetico(""),
        "esperado": "No cumple", "nota": "Los 4 documentos coinciden, pero la licencia solo permite uso habitacional."},
    "Sintético B · discrepancias entre documentos": {
        "archivos": _sintetico("v"),
        "esperado": "Requiere revisión",
        "nota": "Predial con otro propietario, clave con un dígito distinto, número y superficie distintos."},
    "Sintético C · documentos vencidos y afectación": {
        "archivos": _sintetico("!!"),
        "esperado": "Requiere revisión", "nota": "Predial 2023, licencia vencida en 2023 y afectación de 4 m al frente."},
    "Sintético D · documentos ilegibles": {
        "archivos": _sintetico(".."),
        "esperado": "Requiere revisión", "nota": "Escritura, predial y licencia ilegibles."},
    "Tepeji del Río 5 (escritura de 25 págs.)": {
        "archivos": [(f"{E}/Escrituras_Tepeji del Río 5.pdf", "Escritura"), (f"{P}/1. Predial 2025 Tepeji 5.pdf", "Predial"),
                     (f"{A}/3. Alineamiento y numero oficial  Tepeji 5.pdf", "Alineamiento"),
                     (f"{U}/USO DE SUELO TEPEJI DEL RIO 5.pdf", "UsoDeSuelo")],
        "esperado": None, "nota": "Expediente real del reto."},
    "Tultepec Insurgentes": {
        "archivos": [(f"{E}/ESCRITURA-TULTEPEC INSURGENTES.pdf", "Escritura"),
                     (f"{P}/PREDIAL 2024-TULTEPEC INSURGENTES.pdf", "Predial"),
                     (f"{A}/ALINEAMIENTO Y NUMERO OFICIAL-TULTEPEC INSURGENTES.pdf", "Alineamiento"),
                     (f"{U}/USO DE SUELO-TULTEPEC INSURGENTES.pdf", "UsoDeSuelo")],
        "esperado": None, "nota": "Expediente real del reto."},
    "Melchor Ocampo III": {
        "archivos": [(f"{E}/02. Escritura (1).pdf", "Escritura"),
                     (f"{P}/01 Boleta Predial  2025 Melchor Ocampo III.pdf", "Predial"),
                     (f"{A}/03 Alineamiento y numero oficial  Melcho Ocampo III..pdf", "Alineamiento"),
                     (f"{U}/05 Licencia de uso de suelo actualizado al año en curso (uso comercial – minisúper) "
                      "Melchor Ocampo III.pdf", "UsoDeSuelo")],
        "esperado": None, "nota": "Expediente real del reto."},
    "Sor Juana (alineamiento y número oficial en dos constancias)": {
        "archivos": [(f"{E}/02. Escritura.pdf", "Escritura"), (f"{P}/1. Pago de Predial 2025 Sor Juana.pdf", "Predial"),
                     (f"{A}/03. Constancia de Alineamiento Sor Juana.pdf", "Alineamiento"),
                     (f"{A}/03. Número Oficial Sor Juana.pdf", "Alineamiento"),
                     (f"{U}/05. Licencia de Uso de Suelo Sor Juana.pdf", "UsoDeSuelo")],
        "esperado": None, "nota": "Expediente real del reto con 5 archivos."},
    "Escritura de otro inmueble (Tlahuelilpan) + Melchor Ocampo": {
        "archivos": [(f"{E}/02 ESCRITURA.pdf", "Escritura"),
                     (f"{P}/01 Boleta Predial  2025 Melchor Ocampo III.pdf", "Predial"),
                     (f"{A}/03 Alineamiento y numero oficial  Melcho Ocampo III..pdf", "Alineamiento"),
                     (f"{U}/05 Licencia de uso de suelo actualizado al año en curso (uso comercial – minisúper) "
                      "Melchor Ocampo III.pdf", "UsoDeSuelo")],
        "esperado": "No cumple", "nota": "Expediente armado a propósito con la escritura de otro inmueble."},
    "Paseos de la Pradera (escritura de 50 págs., prueba de estrés)": {
        "archivos": [(f"{E}/ESCRITURA 30,025 RELOTIFICACION DE MZAS 88-A A 93-A, 31-B A 71-B Y 1-C A...-HGO PASEOS DE "
                      "LA PRADERA.pdf", "Escritura"),
                     (f"{U}/USO DE SUELO Y ANTECEDENTE CB-HGO PASESO DE LA PRADERA.pdf", "UsoDeSuelo")],
        "esperado": "No cumple", "nota": "Peor caso de páginas; faltan predial y alineamiento."},
}


def rutas(nombre: str) -> list[dict]:
    """Archivos del expediente de ejemplo como {"ruta" absoluta, "nombre" relativo, "tipo"} (solo los que existen)."""
    return [{"ruta": str(RAIZ / r), "nombre": r, "tipo": t}
            for r, t in EXPEDIENTES[nombre]["archivos"] if (RAIZ / r).is_file()]


def disponibles() -> list[str]:
    return [n for n, e in EXPEDIENTES.items() if all((RAIZ / r).is_file() for r, _ in e["archivos"])]


def ruta_relativa(ruta: str | Path) -> str:
    try:
        return Path(ruta).resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return Path(ruta).name
