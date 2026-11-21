"""Compara motores OCR (con y sin preprocesamiento) sobre una muestra pequeña.

Para cada documento de la muestra renderiza las primeras páginas UNA vez y las
pasa por cada combinación motor × preprocesamiento. Genera:
  comparison/tabla.csv              una fila por documento × combinación
  comparison/resumen_combos.csv     promedios por combinación
  comparison/<carpeta>/<doc>/<motor>_<pre|raw>.txt   textos para revisar a ojo
  comparison/lado_a_lado.html       los textos en columnas + miniatura de la pág. 1

Ejemplos:
  python compare_engines.py                         # 2 docs por carpeta, máx 3 págs c/u
  python compare_engines.py --per-folder 3 --pick shortest
  python compare_engines.py --engines paddle        # si Tesseract no está listo
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2

from ocr_pipeline.cli_common import add_preprocess_args, add_tesseract_args, build_preprocess_config, setup_logging
from ocr_pipeline.config import DEFAULT_TESSDATA_DIR, PROJECT_ROOT, PipelineConfig
from ocr_pipeline.engines import ENGINES, create_engine, get_engine_class
from ocr_pipeline.loaders import DocumentSource
from ocr_pipeline.outputs import safe_output_name
from ocr_pipeline.pipeline import discover_files
from ocr_pipeline.preprocess import preprocess


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, default=PROJECT_ROOT)
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "comparison")
    p.add_argument("--engines", default="paddle,tesseract", help=f"Separados por coma. Opciones: {sorted(ENGINES)}")
    p.add_argument("--per-folder", type=int, default=2, help="Documentos por carpeta")
    p.add_argument("--max-pages", type=int, default=3, help="Máximo de páginas por documento")
    p.add_argument("--pick", choices=["random", "shortest"], default="random")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--folder", default=None)
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--threads", type=int, default=8)
    add_preprocess_args(p)
    add_tesseract_args(p)
    return p.parse_args(argv)


def pick_sample(args) -> list[Path]:
    cfg = PipelineConfig(input_dir=args.input, output_dir=args.output, folder=args.folder,
                         order="size" if args.pick == "shortest" else "name")
    by_folder: dict[str, list[Path]] = defaultdict(list)
    for p in discover_files(cfg):
        by_folder[p.relative_to(args.input.resolve()).parts[0]].append(p)
    rng = random.Random(args.seed)
    sample = []
    for folder in sorted(by_folder):
        files = by_folder[folder]
        sample += files[: args.per_folder] if args.pick == "shortest" else \
            rng.sample(files, min(args.per_folder, len(files)))
    return sample


def thumbnail_b64(img, width=700) -> str:
    h, w = img.shape[:2]
    small = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(buf.tobytes()).decode() if ok else ""


def fmt(v, nd=3):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "-"


def main(argv=None) -> int:
    args = parse_args(argv)
    out = args.output.resolve()
    log = setup_logging(out / "comparison.log")
    pre_cfg = build_preprocess_config(args, enabled=True)
    raw_cfg = build_preprocess_config(args, enabled=False)
    opts = PipelineConfig(tesseract_cmd=args.tesseract_cmd,
                          tessdata_dir=args.tessdata_dir or DEFAULT_TESSDATA_DIR,
                          tesseract_psm=args.psm, cpu_threads=args.threads).engine_options()

    engines = {}
    for name in [e.strip() for e in args.engines.split(",") if e.strip()]:
        ok, msg = get_engine_class(name).check_available(**opts)
        if not ok:
            log.warning("Se omite el motor '%s':\n%s", name, msg)
            continue
        log.info("Cargando %s: %s", name, msg)
        engines[name] = create_engine(name, **opts)
    if not engines:
        log.error("No hay motores disponibles.")
        return 2

    combos = [(e, pre) for e in engines for pre in (False, True)]
    sample = pick_sample(args)
    log.info("Muestra: %d documentos, combinaciones: %s", len(sample),
             [f"{e}_{'pre' if p else 'raw'}" for e, p in combos])

    rows, html_docs = [], []
    for path in sample:
        rel = path.relative_to(args.input.resolve())
        doc_dir = out / rel.parent / safe_output_name(rel.name)
        doc_dir.mkdir(parents=True, exist_ok=True)
        log.info("== %s", rel.as_posix())
        try:
            with DocumentSource(path) as src:
                n = min(src.num_pages, args.max_pages)
                t0 = time.perf_counter()
                images = [src.render(i, args.dpi)[0] for i in range(n)]
                render_s = time.perf_counter() - t0
                total_pages = src.num_pages
        except Exception as e:
            log.error("No se pudo abrir %s: %s", rel, e)
            continue

        texts = {}
        for engine_name, use_pre in combos:
            key = f"{engine_name}_{'pre' if use_pre else 'raw'}"
            engine = engines[engine_name]
            page_texts, confs, t_total = [], [], 0.0
            for i, img in enumerate(images):
                t = time.perf_counter()
                try:
                    pimg, _ = preprocess(img, pre_cfg if use_pre else raw_cfg)
                    res = engine.ocr(pimg)
                    txt, conf = res.text.strip(), res.confidence
                except Exception as e:
                    txt, conf = f"[ERROR: {type(e).__name__}: {e}]", None
                t_total += time.perf_counter() - t
                page_texts.append(f"===== Página {i + 1} / {n} =====\n{txt}")
                if conf is not None and txt:
                    confs.append((conf, len(txt)))
            full = "\n\n".join(page_texts)
            texts[key] = full
            (doc_dir / f"{key}.txt").write_text(full, encoding="utf-8")
            wsum = sum(w for _, w in confs)
            avg_conf = sum(c * w for c, w in confs) / wsum if wsum else None
            chars = sum(len(t.split("\n", 1)[1]) if "\n" in t else 0 for t in page_texts)
            rows.append({
                "carpeta": rel.parts[0], "archivo": rel.name, "paginas_evaluadas": n,
                "paginas_totales": total_pages, "motor": engine_name,
                "preproc": "si" if use_pre else "no", "combo": key,
                "tiempo_s": round(t_total, 2), "s_por_pagina": round(t_total / n, 2) if n else None,
                "confianza": round(avg_conf, 4) if avg_conf is not None else None,
                "caracteres": chars, "palabras": len(full.split()),
            })
            log.info("   %-15s %6.1fs  conf=%s  chars=%d", key, t_total, fmt(avg_conf), chars)
        html_docs.append((rel.as_posix(), n, total_pages, round(render_s, 2),
                          thumbnail_b64(images[0]) if images else "", texts))

    if not rows:
        log.error("No se procesó ningún documento.")
        return 1

    # --- tabla detallada
    with open(out / "tabla.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # --- resumen por combinación
    agg = defaultdict(lambda: {"docs": 0, "paginas": 0, "tiempo": 0.0, "chars": 0, "conf": []})
    for r in rows:
        a = agg[r["combo"]]
        a["docs"] += 1
        a["paginas"] += r["paginas_evaluadas"]
        a["tiempo"] += r["tiempo_s"]
        a["chars"] += r["caracteres"]
        if r["confianza"] is not None:
            a["conf"].append(r["confianza"])
    summary = []
    for combo, a in agg.items():
        summary.append({
            "combo": combo, "docs": a["docs"], "paginas": a["paginas"],
            "s_por_pagina": round(a["tiempo"] / a["paginas"], 2) if a["paginas"] else None,
            "confianza_media": round(sum(a["conf"]) / len(a["conf"]), 4) if a["conf"] else None,
            "chars_por_pagina": round(a["chars"] / a["paginas"]) if a["paginas"] else 0,
        })
    with open(out / "resumen_combos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    # --- tabla en consola
    print("\nDetalle por documento:")
    print(f"{'carpeta':<16} {'archivo':<38} {'combo':<15} {'s/pág':>6} {'conf':>6} {'chars':>7}")
    for r in rows:
        print(f"{r['carpeta'][:16]:<16} {r['archivo'][:38]:<38} {r['combo']:<15} "
              f"{fmt(r['s_por_pagina'], 1):>6} {fmt(r['confianza']):>6} {r['caracteres']:>7}")
    print("\nResumen por combinación (nota: la confianza de Paddle y Tesseract no es directamente comparable):")
    print(f"{'combo':<15} {'docs':>4} {'págs':>5} {'s/pág':>6} {'conf':>6} {'chars/pág':>9}")
    for s in summary:
        print(f"{s['combo']:<15} {s['docs']:>4} {s['paginas']:>5} {fmt(s['s_por_pagina'], 1):>6} "
              f"{fmt(s['confianza_media']):>6} {s['chars_por_pagina']:>9}")

    write_html(out / "lado_a_lado.html", html_docs, rows)
    print(f"\nArchivos en: {out}")
    return 0


def write_html(path: Path, docs, rows) -> None:
    stats = {(r["carpeta"] + "/" + r["archivo"], r["combo"]): r for r in rows}
    parts = ["""<!doctype html><meta charset="utf-8"><title>Comparación OCR</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}
h2{margin-top:40px;border-bottom:2px solid #ccc}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px}
.col{background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px}
.col h3{margin:0 0 6px;font-size:14px}.meta{font-size:12px;color:#666}
pre{white-space:pre-wrap;font-size:12px;max-height:600px;overflow:auto;margin:0}
img{max-width:100%;border:1px solid #ccc}
</style><h1>Comparación de motores OCR</h1>"""]
    for name, n, total, render_s, thumb, texts in docs:
        parts.append(f"<h2>{html.escape(name)}</h2><p class=meta>Páginas evaluadas: {n} de {total} · "
                     f"render: {render_s}s</p><div class=grid>")
        if thumb:
            parts.append(f"<div class=col><h3>Página 1 (imagen)</h3><img src='data:image/jpeg;base64,{thumb}'></div>")
        for combo, txt in texts.items():
            r = stats.get((name, combo), {})
            parts.append(f"<div class=col><h3>{combo}</h3><div class=meta>{r.get('tiempo_s')}s · "
                         f"conf {fmt(r.get('confianza'))} · {r.get('caracteres')} chars</div>"
                         f"<pre>{html.escape(txt)}</pre></div>")
        parts.append("</div>")
    path.write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
