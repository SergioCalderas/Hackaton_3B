"""Escritura de resultados: .txt por documento, .json de metadatos y CSV resumen."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

SUMMARY_NAME = "resumen.csv"
SUMMARY_COLUMNS = [
    "carpeta", "archivo", "tipo_archivo", "paginas", "motor", "metodos",
    "confianza_promedio", "caracteres", "caracteres_por_pagina", "tiempo_s",
    "estado", "duplicado_de", "errores", "sha256", "txt",
]


def safe_output_name(original_name: str, max_len: int = 150) -> str:
    """Nombre base de salida derivado del original (se conserva la extensión
    original para evitar choques como 'X.pdf' vs 'X.jpeg' o 'X...pdf')."""
    name = original_name.strip().rstrip(".")
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    if len(name) > max_len:  # evita pasar MAX_PATH de Windows
        digest = hashlib.sha1(original_name.encode("utf-8")).hexdigest()[:8]
        name = f"{name[:max_len - 9]}_{digest}"
    return name


def output_paths(output_dir: Path, rel_path: Path) -> tuple[Path, Path]:
    base = output_dir / rel_path.parent / safe_output_name(rel_path.name)
    return base.with_name(base.name + ".txt"), base.with_name(base.name + ".json")


def _atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)


def write_json(path: Path, meta: dict) -> None:
    _atomic_write(path, json.dumps(meta, ensure_ascii=False, indent=2))


def write_txt(path: Path, text: str) -> None:
    _atomic_write(path, text)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def iter_result_jsons(output_dir: Path):
    for p in sorted(output_dir.rglob("*.json")):
        meta = read_json(p)
        if meta and "source_file" in meta and "pages" in meta:
            yield p, meta


def build_summary_csv(output_dir: Path) -> Path:
    """Regenera el CSV resumen a partir de todos los .json existentes."""
    rows = []
    for json_path, m in iter_result_jsons(output_dir):
        pages = m.get("num_pages") or 0
        chars = m.get("total_chars") or 0
        conf = m.get("avg_confidence")
        rows.append({
            "carpeta": m.get("doc_type", ""),
            "archivo": m.get("source_file", ""),
            "tipo_archivo": m.get("file_type", ""),
            "paginas": pages,
            "motor": m.get("engine", ""),
            "metodos": " ".join(f"{k}:{v}" for k, v in (m.get("methods_count") or {}).items()),
            "confianza_promedio": f"{conf:.3f}" if isinstance(conf, (int, float)) else "",
            "caracteres": chars,
            "caracteres_por_pagina": round(chars / pages) if pages else 0,
            "tiempo_s": m.get("processing_time_s", ""),
            "estado": m.get("status", ""),
            "duplicado_de": m.get("duplicate_of") or "",
            "errores": len(m.get("errors") or []),
            "sha256": (m.get("sha256") or "")[:16],
            "txt": str(json_path.with_suffix(".txt").relative_to(output_dir)),
        })
    path = output_dir / SUMMARY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig para que Excel muestre bien acentos y ñ.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
PAGE_HEADER_RE = re.compile(r"^===== Página (\d+) / \d+ \|.*=====$", re.MULTILINE)
EXCEL_CELL_MAX = 32000  # límite de Excel: 32767 caracteres por celda


def split_pages(txt: str) -> dict[int, str]:
    """Separa el .txt de un documento en {número de página: texto}."""
    matches = list(PAGE_HEADER_RE.finditer(txt))
    pages = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
        pages[int(m.group(1))] = txt[m.end():end].strip()
    return pages


def _clean_cell(s: str) -> str:
    # openpyxl rechaza caracteres de control (salvo \t \n \r).
    s = ILLEGAL_CHARACTERS_RE.sub("", s)
    return s if len(s) <= EXCEL_CELL_MAX else s[:EXCEL_CELL_MAX] + " …[truncado]"


STATUS_FILLS = {
    "ok": "C6EFCE",              # verde
    "low_confidence": "FFEB9C",  # amarillo
    "low_text": "FFEB9C",
    "partial": "F8CBAD",         # naranja
    "error": "FFC7CE",           # rojo
}


def build_summary_xlsx(output_dir: Path, preview_chars: int = 300) -> Path:
    """Genera resumen.xlsx con hojas 'documentos' y 'paginas'."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws_docs = wb.active
    ws_docs.title = "documentos"
    ws_pages = wb.create_sheet("paginas")

    doc_cols = [("carpeta", 22), ("archivo", 45), ("paginas", 8), ("metodo_por_pagina", 30),
                ("motor", 10), ("confianza_promedio", 12), ("caracteres", 11), ("estado", 15),
                ("duplicado_de", 35), ("errores", 30), ("vista_previa", 80)]
    page_cols = [("carpeta", 22), ("archivo", 45), ("pagina", 7), ("metodo", 13),
                 ("confianza", 10), ("caracteres", 11), ("error", 25), ("texto", 100)]

    for ws, cols in ((ws_docs, doc_cols), (ws_pages, page_cols)):
        ws.append([c for c, _ in cols])
        for i, (_, width) in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(i)].width = width
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="D9E1F2")
        ws.freeze_panes = "A2"

    for json_path, m in iter_result_jsons(output_dir):
        txt_path = json_path.with_suffix(".txt")
        txt = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""
        page_texts = split_pages(txt)
        body = "\n".join(page_texts[k] for k in sorted(page_texts))
        conf = m.get("avg_confidence")
        method_by_page = " | ".join(f"{p['page']}:{p.get('method') or 'error'}" for p in m.get("pages", []))
        ws_docs.append([
            m.get("doc_type", ""), m.get("source_file", ""), m.get("num_pages", 0), method_by_page,
            m.get("engine", ""), round(conf, 3) if isinstance(conf, (int, float)) else None,
            m.get("total_chars", 0), m.get("status", ""), m.get("duplicate_of") or "",
            _clean_cell("; ".join(m.get("errors") or [])),
            _clean_cell(" ".join(body.split())[:preview_chars]),
        ])
        for p in m.get("pages", []):
            ws_pages.append([
                m.get("doc_type", ""), m.get("source_file", ""), p["page"],
                p.get("method") or "error", p.get("confidence"), p.get("chars", 0),
                p.get("error") or "", _clean_cell(page_texts.get(p["page"], "")),
            ])

    wrap = Alignment(wrap_text=True, vertical="top")
    top = Alignment(vertical="top")
    status_col = [c for c, _ in doc_cols].index("estado") + 1
    for ws, wrap_cols in ((ws_docs, {"archivo", "metodo_por_pagina", "duplicado_de", "errores", "vista_previa"}),
                          (ws_pages, {"archivo", "error", "texto"})):
        headers = [c.value for c in ws[1]]
        for row in ws.iter_rows(min_row=2):
            for cell, h in zip(row, headers):
                cell.alignment = wrap if h in wrap_cols else top
        ws.auto_filter.ref = ws.dimensions
    for row in ws_docs.iter_rows(min_row=2, min_col=status_col, max_col=status_col):
        color = STATUS_FILLS.get(row[0].value)
        if color:
            row[0].fill = PatternFill("solid", fgColor=color)
    # Altura de fila acotada en la hoja de páginas para que sea navegable.
    for r in range(2, ws_pages.max_row + 1):
        ws_pages.row_dimensions[r].height = 120

    path = output_dir / "resumen.xlsx"
    try:
        wb.save(path)
    except PermissionError:  # el archivo está abierto en Excel
        path = output_dir / f"resumen_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        wb.save(path)
    return path
