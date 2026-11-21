"""Genera los ejemplos de examples/ a partir de output/ (requiere haber corrido run_ocr.py).

Usa SOLO el expediente sintético "v" (documentos marcados "DOCUMENTO SINTÉTICO - HACKATHON 3B -
SIN VALIDEZ OFICIAL"): nada de escrituras reales ni datos personales. Los textos se recortan.

    python examples/generar_ejemplos.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ocr_pipeline.matching import aplicar_modo  # noqa: E402
from ocr_pipeline.schemas import Documento, Expediente  # noqa: E402

# Los 4 documentos sintéticos del set "v" (tienen discrepancias plantadas: propietario,
# un dígito de la clave catastral, número oficial y superficie).
SINTETICOS_V = {
    "Alineamiento_y_Numero_Oficial/03 Alineamiento y Numero Oficialv.pdf",
    "Escritura/01 Escriturav.pdf",
    "Predial/02 Predialv.pdf",
    "Uso_de_suelo/04 Licencia de Uso de Suelov.pdf",
}
MAX_TEXTO = 300


def recortar(texto: str | None, n: int = MAX_TEXTO) -> str | None:
    if texto is None or len(texto) <= n:
        return texto
    return texto[:n].rstrip() + " …[recortado]"


def recortar_documento(doc: dict) -> dict:
    return {**doc,
            "TextoExtraido": recortar(doc.get("TextoExtraido")),
            "Paginas": [{**p, "Texto": recortar(p.get("Texto"), 200)} for p in doc.get("Paginas", [])]}


def main() -> int:
    salida = RAIZ / "output" / "expedientes.json"
    if not salida.exists():
        print("No existe output/expedientes.json; corre primero run_ocr.py", file=sys.stderr)
        return 2
    expedientes = json.loads(salida.read_text(encoding="utf-8"))
    exp = next((e for e in expedientes if {d["RutaArchivo"] for d in e["Documentos"]} == SINTETICOS_V), None)
    if exp is None:
        print("No se encontró el expediente sintético 'v' en output/expedientes.json", file=sys.stderr)
        return 1

    exp = {**exp, "Documentos": [recortar_documento(d) for d in exp["Documentos"]]}
    docs = exp["Documentos"]
    compacto = aplicar_modo(exp, "compacto", es_expediente=True)

    for d in docs:
        Documento.model_validate(d)
    Expediente.model_validate(exp)
    Expediente.model_validate(compacto)

    destino = Path(__file__).resolve().parent
    for nombre, data in (("documentos.json", docs), ("expedientes.json", [exp]),
                         ("expedientes_compacto.json", [compacto])):
        (destino / nombre).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("->", destino / nombre)
    return 0


if __name__ == "__main__":
    sys.exit(main())
