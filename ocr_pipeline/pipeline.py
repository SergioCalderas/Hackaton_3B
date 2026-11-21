"""Orquestación: descubrir archivos, procesar cada documento, deduplicar y reanudar."""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from .config import EXCLUDED_DIRS, PIPELINE_VERSION, SUPPORTED_EXTENSIONS, PipelineConfig
from .engines import EngineUnavailableError, OCREngine, create_engine
from .loaders import DocumentSource, sha256_file, useful_chars
from .outputs import build_summary_csv, build_summary_xlsx, iter_result_jsons, output_paths, read_json, write_json, write_txt
from .preprocess import preprocess
from .quality import text_quality

log = logging.getLogger("ocr_pipeline")


# ---------------------------------------------------------------------------
# Descubrimiento de archivos
# ---------------------------------------------------------------------------
def discover_files(cfg: PipelineConfig) -> list[Path]:
    """Lista archivos soportados bajo input_dir (excluyendo salidas y entornos).

    Respeta --folder (sin distinguir mayúsculas), --order, --limit-per-folder y --limit.
    """
    input_dir = cfg.input_dir.resolve()
    output_dir = cfg.output_dir.resolve()
    files = []
    for p in input_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel = p.relative_to(input_dir)
        if any(part in EXCLUDED_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if output_dir in p.parents:
            continue
        if cfg.folder and (len(rel.parts) < 2 or rel.parts[0].lower() != cfg.folder.lower()):
            continue
        files.append(p)

    key = (lambda p: (p.relative_to(input_dir).parts[0], p.stat().st_size)) if cfg.order == "size" \
        else (lambda p: str(p.relative_to(input_dir)).lower())
    files.sort(key=key)

    if cfg.limit_per_folder:
        per: Counter = Counter()
        kept = []
        for p in files:
            top = p.relative_to(input_dir).parts[0]
            if per[top] < cfg.limit_per_folder:
                kept.append(p)
                per[top] += 1
        files = kept
    if cfg.limit:
        files = files[: cfg.limit]
    return files


# ---------------------------------------------------------------------------
# Motores (carga perezosa: solo se instancia si alguna página necesita OCR)
# ---------------------------------------------------------------------------
class EngineProvider:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self._engines: dict[str, OCREngine] = {}

    def get(self, name: str) -> OCREngine:
        if name not in self._engines:
            log.info("Cargando motor OCR '%s'...", name)
            self._engines[name] = create_engine(name, **self.cfg.engine_options())
        return self._engines[name]


# ---------------------------------------------------------------------------
# Procesamiento de un documento
# ---------------------------------------------------------------------------
def page_header(n: int, total: int, method: str, conf) -> str:
    c = f" | confianza: {conf:.3f}" if isinstance(conf, (int, float)) else ""
    return f"===== Página {n} / {total} | método: {method}{c} ====="


def compute_status(meta: dict, cfg: PipelineConfig) -> str:
    pages = meta["pages"]
    if not pages or all(p.get("error") for p in pages):
        return "error"
    if any(p.get("error") for p in pages):
        return "partial"
    n = meta["num_pages"] or 1
    if meta["total_chars"] / n < cfg.low_text_chars_per_page:
        return "low_text"
    quality = meta.get("text_quality")
    if quality is not None and quality < cfg.low_quality_threshold:
        return "low_confidence"
    return "ok"


def process_document(path: Path, rel: Path, sha: str, cfg: PipelineConfig,
                     provider: EngineProvider) -> tuple[dict, str]:
    """Procesa un documento y devuelve (metadatos, texto completo)."""
    t_doc = time.perf_counter()
    meta: dict = {
        "source_file": rel.as_posix(),
        "source_path": str(path),
        "doc_type": rel.parts[0] if len(rel.parts) > 1 else "",
        "file_type": path.suffix.lower().lstrip("."),
        "sha256": sha,
        "size_bytes": path.stat().st_size,
        "num_pages": 0,
        "engine": cfg.engine,
        "dpi": cfg.dpi,
        "preprocess": cfg.preprocess.active_steps(),
        "pages": [],
        "methods_count": {},
        "avg_confidence": None,
        "text_quality": None,
        "total_chars": 0,
        "processing_time_s": None,
        "status": None,
        "duplicate_of": None,
        "errors": [],
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "pipeline_version": PIPELINE_VERSION,
    }
    sections: list[str] = []

    try:
        src = DocumentSource(path)
    except Exception as e:
        meta["errors"].append(f"No se pudo abrir el archivo: {type(e).__name__}: {e}")
        meta["status"] = "error"
        meta["processing_time_s"] = round(time.perf_counter() - t_doc, 2)
        return meta, ""

    with src:
        meta["num_pages"] = src.num_pages
        for i in range(src.num_pages):
            t_page = time.perf_counter()
            page = {"page": i + 1, "method": None, "engine": None, "chars": 0,
                    "confidence": None, "time_s": None, "error": None}
            text = ""
            try:
                native = src.native_text(i) if cfg.use_native_text else ""
                if useful_chars(native) >= cfg.min_native_chars:
                    text = native.strip()
                    page["method"] = "native"
                else:
                    img, eff_dpi = src.render(i, cfg.dpi, cfg.max_render_pixels)
                    if eff_dpi and eff_dpi != cfg.dpi:
                        page["render_dpi"] = eff_dpi
                    img, pinfo = preprocess(img, cfg.preprocess)
                    if pinfo["skew_angle"] is not None:
                        page["skew_angle"] = pinfo["skew_angle"]
                    engine = provider.get(cfg.engine)
                    res = engine.ocr(img)
                    text = res.text.strip()
                    used = res.engine or engine.name
                    page["method"] = f"ocr:{used}"
                    page["engine"] = used
                    page["confidence"] = round(res.confidence, 4) if res.confidence is not None else None
                    page["ocr_lines"] = len(res.lines)
                    if res.extra.get("fallback"):
                        page["hybrid"] = {k: v for k, v in res.extra.items() if k != "quality"}
            except EngineUnavailableError:
                raise  # falla de configuración: detiene el run completo
            except Exception as e:
                page["error"] = f"{type(e).__name__}: {e}"
                meta["errors"].append(f"Página {i + 1}: {page['error']}")
                log.warning("%s pág %d: %s", rel, i + 1, page["error"])
            page["chars"] = len(text)
            q = text_quality(text) if text else None
            page["text_quality"] = round(q, 4) if q is not None else None
            page["time_s"] = round(time.perf_counter() - t_page, 2)
            meta["pages"].append(page)

            body = text if not page["error"] else f"[ERROR EN PÁGINA: {page['error']}]"
            sections.append(page_header(i + 1, src.num_pages, page["method"] or "error",
                                        page["confidence"]) + "\n" + body)

    # Agregados
    meta["methods_count"] = dict(Counter(p["method"] or "error" for p in meta["pages"]))
    meta["total_chars"] = sum(p["chars"] for p in meta["pages"])
    ocr_pages = [p for p in meta["pages"] if p["confidence"] is not None and p["chars"]]
    if ocr_pages:
        tot = sum(p["chars"] for p in ocr_pages)
        meta["avg_confidence"] = round(sum(p["confidence"] * p["chars"] for p in ocr_pages) / tot, 4)
    q_pages = [p for p in meta["pages"] if p.get("text_quality") is not None and p["chars"]]
    if q_pages:
        tot = sum(p["chars"] for p in q_pages)
        meta["text_quality"] = round(sum(p["text_quality"] * p["chars"] for p in q_pages) / tot, 4)
    meta["processing_time_s"] = round(time.perf_counter() - t_doc, 2)
    meta["status"] = compute_status(meta, cfg)

    header = (f"# Fuente: {meta['source_file']}\n# Tipo: {meta['doc_type']}\n"
              f"# Páginas: {meta['num_pages']}\n# SHA-256: {sha}\n")
    return meta, header + "\n" + "\n\n".join(sections) + "\n"


def make_duplicate(primary_meta: dict, primary_txt: Path, path: Path, rel: Path,
                   sha: str) -> tuple[dict, str]:
    """Reutiliza el resultado de un archivo idéntico (mismo SHA-256) sin repetir OCR."""
    meta = dict(primary_meta)
    meta.update({
        "source_file": rel.as_posix(),
        "source_path": str(path),
        "doc_type": rel.parts[0] if len(rel.parts) > 1 else "",
        "file_type": path.suffix.lower().lstrip("."),
        "size_bytes": path.stat().st_size,
        "duplicate_of": primary_meta["source_file"],
        "processing_time_s": 0.0,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    })
    text = primary_txt.read_text(encoding="utf-8")
    text = text.replace(f"# Fuente: {primary_meta['source_file']}\n",
                        f"# Fuente: {meta['source_file']}\n"
                        f"# DUPLICADO de: {primary_meta['source_file']} (mismo SHA-256; texto reutilizado)\n", 1)
    return meta, text


# ---------------------------------------------------------------------------
# Run completo
# ---------------------------------------------------------------------------
def run(cfg: PipelineConfig) -> dict:
    input_dir = cfg.input_dir.resolve()
    output_dir = cfg.output_dir.resolve()
    files = discover_files(cfg)
    log.info("Archivos a considerar: %d (entrada: %s)", len(files), input_dir)

    # Registro de documentos ya procesados por hash (para deduplicar).
    registry: dict[str, tuple[dict, Path]] = {}
    if not cfg.force:
        for jp, m in iter_result_jsons(output_dir):
            if m.get("sha256") and not m.get("duplicate_of") and m.get("status") != "error":
                registry.setdefault(m["sha256"], (m, jp.with_suffix(".txt")))

    provider = EngineProvider(cfg)
    stats = Counter()
    bar = tqdm(files, unit="doc", dynamic_ncols=True)
    for path in bar:
        rel = path.relative_to(input_dir)
        bar.set_postfix_str(rel.name[:40])
        txt_path, json_path = output_paths(output_dir, rel)

        if not cfg.force and json_path.exists() and txt_path.exists():
            prev = read_json(json_path)
            if prev and prev.get("status") != "error":
                stats["saltado"] += 1
                continue

        try:
            sha = sha256_file(path)
            if sha in registry:
                pmeta, ptxt = registry[sha]
                meta, text = make_duplicate(pmeta, ptxt, path, rel, sha)
                stats["duplicado"] += 1
                log.info("DUPLICADO %s == %s", rel.as_posix(), pmeta["source_file"])
            else:
                meta, text = process_document(path, rel, sha, cfg, provider)
                stats[meta["status"]] += 1
                log.info("%-14s %s | págs=%d %s calidad=%s conf=%s chars=%d %.1fs", meta["status"].upper(),
                         rel.as_posix(), meta["num_pages"], meta["methods_count"], meta["text_quality"],
                         meta["avg_confidence"], meta["total_chars"], meta["processing_time_s"])
            write_txt(txt_path, text)
            write_json(json_path, meta)
            if meta["status"] != "error" and not meta["duplicate_of"]:
                registry.setdefault(sha, (meta, txt_path))
        except EngineUnavailableError:
            raise
        except Exception as e:
            stats["error"] += 1
            log.exception("Fallo procesando %s: %s", rel.as_posix(), e)
            write_json(json_path, {
                "source_file": rel.as_posix(), "source_path": str(path),
                "doc_type": rel.parts[0] if len(rel.parts) > 1 else "",
                "file_type": path.suffix.lower().lstrip("."), "num_pages": 0, "pages": [],
                "engine": cfg.engine, "status": "error", "errors": [f"{type(e).__name__}: {e}"],
                "processed_at": datetime.now().isoformat(timespec="seconds"),
            })

    csv_path = build_summary_csv(output_dir)
    try:
        xlsx_path = build_summary_xlsx(output_dir)
    except Exception as e:  # el Excel es un extra: no debe tumbar el run
        xlsx_path = f"no generado ({type(e).__name__}: {e})"
        log.exception("No se pudo generar el Excel")
    try:
        from .export import exportar_todo
        resumen = exportar_todo(output_dir)
        log.info("Exportado: %s", ", ".join(resumen["archivos"]))
    except Exception:
        log.exception("No se pudo generar documentos.json / expedientes.json")
    log.info("Resumen: %s | CSV: %s | Excel: %s", dict(stats), csv_path, xlsx_path)
    return dict(stats)
