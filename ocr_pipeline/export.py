"""Exportación para el LLM: documentos.json, expedientes.json y expedientes.xlsx.

Se construye solo a partir de los .json/.txt ya generados por el OCR (no repite OCR).
Todo se valida contra los modelos Pydantic de schemas.py antes de escribirse.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .matching import MODOS, MatchConfig, agrupar, aplicar_modo, canonical_tipo, enriquecer_documento
from .outputs import STATUS_FILLS, _atomic_write, _clean_cell, iter_result_jsons, split_pages
from .schemas import VERSION_ESQUEMA, Documento, Expediente

log = logging.getLogger("ocr_pipeline")

DOCUMENTS_JSON = "documentos.json"
EXPEDIENTES_JSON = "expedientes.json"
EXPEDIENTES_XLSX = "expedientes.xlsx"


def tipo_documento(folder: str) -> str | None:
    return canonical_tipo(folder)


def _r(v, nd=3):
    return round(v, nd) if isinstance(v, (int, float)) else None


def build_document(meta: dict, txt: str, tipo_declarado: str | None = None) -> dict:
    """Documento base (sin campos) a partir de los metadatos del OCR y su .txt."""
    page_texts = split_pages(txt)
    paginas = []
    for p in meta.get("pages", []):
        method = p.get("method") or "error"
        paginas.append({
            "Numero": p["page"],
            "Texto": page_texts.get(p["page"], "") if not p.get("error") else "",
            "Metodo": "native" if method == "native" else ("ocr" if method.startswith("ocr") else "error"),
            "Motor": p.get("engine"),
            "CalidadTexto": _r(p.get("text_quality")),
        })
    source = meta.get("source_file", "")
    declarado = canonical_tipo(tipo_declarado) if tipo_declarado else tipo_documento(meta.get("doc_type", ""))
    return {
        "VersionEsquema": VERSION_ESQUEMA,
        "Modo": "completo",
        "NombreArchivo": Path(source).name,
        "RutaArchivo": source,
        "TipoDocumento": declarado,
        "TipoDeclarado": declarado,
        "TipoDetectado": None,
        "TextoExtraido": "\n\n".join(pg["Texto"] for pg in paginas if pg["Texto"]),
        "Paginas": paginas,
        "Estado": meta.get("status") or "error",
        "CalidadTexto": _r(meta.get("text_quality")),
        "NumPaginas": meta.get("num_pages", 0),
        "Hash": (meta.get("sha256") or "")[:16] or None,
        "DuplicadoDe": meta.get("duplicate_of"),
        "CamposExtraidos": {},
        "Discrepancias": [],
        "ExpedienteId": None,
    }


def load_documents(output_dir: Path, enrich: bool = True) -> list[dict]:
    docs = []
    for json_path, meta in iter_result_jsons(Path(output_dir)):
        txt_path = json_path.with_suffix(".txt")
        txt = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""
        doc = build_document(meta, txt)
        docs.append(enriquecer_documento(doc) if enrich else doc)
    docs.sort(key=lambda d: (d["TipoDeclarado"] or "", d["RutaArchivo"].lower()))
    return docs


def write_json_file(path: Path, data) -> None:
    _atomic_write(Path(path), json.dumps(data, ensure_ascii=False, indent=2))


def validar(docs: list[dict], expedientes: list[dict]) -> None:
    for d in docs:
        Documento.model_validate(d)
    for e in expedientes:
        Expediente.model_validate({"VersionEsquema": VERSION_ESQUEMA, **e})


def export_documents_json(output_dir: Path, docs: list[dict] | None = None) -> tuple[Path, int]:
    """Solo documentos.json (sin matching: ExpedienteId = null)."""
    docs = load_documents(output_dir) if docs is None else docs
    validar(docs, [])
    path = Path(output_dir) / DOCUMENTS_JSON
    write_json_file(path, docs)
    return path, len(docs)


def _nombre_modo(nombre: str, modo: str) -> str:
    """documentos.json (completo) / documentos_compacto.json (compacto)."""
    return nombre if modo == "completo" else nombre.replace(".json", f"_{modo}.json")


def exportar_todo(output_dir: Path, cfg: MatchConfig | None = None,
                  modos: tuple[str, ...] = ("completo", "compacto")) -> dict:
    """documentos[_compacto].json + expedientes[_compacto].json + expedientes.xlsx.

    modos: "completo" escribe documentos.json / expedientes.json (con texto);
           "compacto" escribe documentos_compacto.json / expedientes_compacto.json (sin texto).
    """
    output_dir = Path(output_dir)
    cfg = cfg or MatchConfig()
    for m in modos:
        if m not in MODOS:
            raise ValueError(f"modo debe ser uno de {MODOS}, no {m!r}")
    docs = load_documents(output_dir)
    res = agrupar(docs, cfg)

    exp_de = {d["RutaArchivo"]: e["ExpedienteId"] for e in res["expedientes"] for d in e["Documentos"]}
    for d in docs:
        d["ExpedienteId"] = exp_de.get(d["RutaArchivo"])
    expedientes = [{"VersionEsquema": VERSION_ESQUEMA, **e} for e in res["expedientes"]]

    archivos = []
    for modo in modos:
        docs_m = [aplicar_modo(d, modo, es_expediente=False) for d in docs]
        exps_m = [aplicar_modo(e, modo, es_expediente=True) for e in expedientes]
        validar(docs_m, exps_m)
        for nombre, data in ((DOCUMENTS_JSON, docs_m), (EXPEDIENTES_JSON, exps_m)):
            path = output_dir / _nombre_modo(nombre, modo)
            write_json_file(path, data)
            archivos.append(str(path))
    xlsx = build_expedientes_xlsx(output_dir, expedientes, res["revisar"], res["sin_match"], docs)
    archivos.append(str(xlsx))
    resumen = {
        "documentos": len(docs),
        "expedientes": len(expedientes),
        "completos": sum(1 for e in expedientes if not e["DocumentosFaltantes"]),
        "revisar": len(res["revisar"]),
        "sin_match": len(res["sin_match"]),
        "archivos": archivos,
    }
    log.info("Matching: %s", {k: v for k, v in resumen.items() if k != "archivos"})
    return resumen


# ---------------------------------------------------------------------------
# Excel de expedientes
# ---------------------------------------------------------------------------
def _pista(ruta: str) -> str:
    """Nombre del archivo: solo como pista visual para revisar, nunca entra al puntaje."""
    return Path(ruta).stem


def build_expedientes_xlsx(output_dir: Path, expedientes, revisar, sin_match, docs) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    by_ruta = {d["RutaArchivo"]: d for d in docs}
    wb = Workbook()
    sheets = {
        "expedientes": [("ExpedienteId", 26), ("Documentos", 8), ("Tipos", 38), ("Faltantes", 26),
                        ("PuntajeMatch", 11), ("Nivel", 9), ("ClaveCatastral", 20), ("Propietario", 32),
                        ("Direccion", 40), ("Municipio", 22), ("Coinciden", 40), ("NoCoinciden", 50),
                        ("Alertas", 60), ("Archivos", 70)],
        "campos": [("ExpedienteId", 26), ("Documento", 55), ("TipoDocumento", 13), ("Campo", 20),
                   ("Valor", 40), ("Normalizado", 30), ("Pagina", 7), ("Evidencia", 80), ("Regla", 30)],
        "sin_match": [("Documento", 60), ("TipoDocumento", 13), ("Estado", 15), ("Motivo", 45),
                      ("MejorCandidato", 55), ("PuntajeMejorCandidato", 12), ("ExpedienteMejorCandidato", 26),
                      ("PistaNombreArchivo", 45)],
        "revisar": [("Puntaje", 9), ("DocumentoA", 55), ("ExpedienteA", 24), ("DocumentoB", 55),
                    ("ExpedienteB", 24), ("Motivo", 40), ("Coinciden", 35), ("NoCoinciden", 35),
                    ("PistaNombreArchivo", 60)],
    }
    ws_map = {}
    for i, (name, cols) in enumerate(sheets.items()):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = name
        ws.append([c for c, _ in cols])
        for j, (_, w) in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9E1F2")
        ws.freeze_panes = "A2"
        ws_map[name] = ws

    def val(e, campo):
        c = e["CamposConsolidados"].get(campo)
        return c["Valor"] if c else ""

    for e in expedientes:
        calle = " ".join(x for x in (val(e, "Calle"), val(e, "NumeroOficial"), val(e, "Colonia")) if x)
        ws_map["expedientes"].append([
            e["ExpedienteId"], len(e["Documentos"]), ", ".join(e["TiposPresentes"]),
            ", ".join(e["DocumentosFaltantes"]), e["PuntajeMatch"], e["NivelMatch"],
            val(e, "ClaveCatastral"), val(e, "Propietario"), calle, val(e, "Municipio"),
            ", ".join(e["CamposCoinciden"]),
            _clean_cell("\n".join(f"{x['Campo']}: {x['Detalle']} -> " +
                                  " | ".join(f"{v['TipoDocumento']}={v['Valor']}" for v in x["Valores"])
                                  for x in e["CamposNoCoinciden"])),
            _clean_cell("\n".join(e["Alertas"])),
            "\n".join(d["RutaArchivo"] for d in e["Documentos"]),
        ])
    for d in docs:
        for campo, c in d.get("CamposExtraidos", {}).items():
            ws_map["campos"].append([d.get("ExpedienteId") or "", d["RutaArchivo"], d.get("TipoDocumento"),
                                     campo, _clean_cell(c["Valor"]), _clean_cell(str(c["Normalizado"])),
                                     c["Pagina"], _clean_cell(c["Evidencia"]), c["Regla"]])
    for s in sin_match:
        ws_map["sin_match"].append([s["Documento"], s["TipoDocumento"], s["Estado"], s["Motivo"],
                                    s["MejorCandidato"], s["PuntajeMejorCandidato"], s["ExpedienteMejorCandidato"],
                                    _pista(s["Documento"])])
    for r in revisar:
        ws_map["revisar"].append([r["Puntaje"], r["DocumentoA"], r["ExpedienteA"], r["DocumentoB"], r["ExpedienteB"],
                                  r["Motivo"], ", ".join(r["Coinciden"]), ", ".join(r["NoCoinciden"]),
                                  f"{_pista(r['DocumentoA'])}  ↔  {_pista(r['DocumentoB'])}"])

    wrap = Alignment(wrap_text=True, vertical="top")
    nivel_fill = {"alto": STATUS_FILLS["ok"], "medio": STATUS_FILLS["low_confidence"],
                  "bajo": STATUS_FILLS["error"], "sin_datos": STATUS_FILLS["partial"]}
    for name, ws in ws_map.items():
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap
        ws.auto_filter.ref = ws.dimensions
    for row in ws_map["expedientes"].iter_rows(min_row=2):
        if (color := nivel_fill.get(row[5].value)):
            row[5].fill = PatternFill("solid", fgColor=color)
        if row[3].value:
            row[3].fill = PatternFill("solid", fgColor=STATUS_FILLS["low_confidence"])

    path = Path(output_dir) / EXPEDIENTES_XLSX
    try:
        wb.save(path)
    except PermissionError:
        path = Path(output_dir) / f"expedientes_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        wb.save(path)
    return path
