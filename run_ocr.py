"""Pipeline OCR local: extrae texto de PDFs escaneados e imágenes.

Ejemplos:
  python run_ocr.py                                  # todo, PaddleOCR, sin preprocesamiento
  python run_ocr.py --folder Predial --limit 3       # prueba rápida
  python run_ocr.py --limit-per-folder 2 --order size
  python run_ocr.py --engine tesseract --preprocess --output output_tess
  python run_ocr.py --force                          # reprocesa aunque ya exista salida
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ocr_pipeline.cli_common import (add_preprocess_args, add_tesseract_args,
                                     build_preprocess_config, setup_logging)
from ocr_pipeline.config import DEFAULT_TESSDATA_DIR, PROJECT_ROOT, PipelineConfig
from ocr_pipeline.engines import ENGINES, EngineUnavailableError, get_engine_class


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, default=PROJECT_ROOT, help="Carpeta raíz con las subcarpetas de documentos")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "output", help="Carpeta de salida")
    p.add_argument("--engine", choices=sorted(ENGINES), default="paddle")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--folder", default=None, help="Procesar solo esta subcarpeta (p. ej. Predial)")
    p.add_argument("--limit", type=int, default=None, help="Máximo de archivos en total")
    p.add_argument("--limit-per-folder", type=int, default=None, help="Máximo de archivos por subcarpeta")
    p.add_argument("--order", choices=["name", "size"], default="name",
                   help="Orden de procesamiento; 'size' = más pequeños primero (útil para pruebas)")
    p.add_argument("--force", action="store_true", help="Reprocesar aunque ya exista la salida")
    p.add_argument("--min-native-chars", type=int, default=50,
                   help="Mínimo de caracteres alfanuméricos para confiar en la capa de texto del PDF")
    p.add_argument("--no-native", action="store_true", help="Ignorar capa de texto y hacer OCR siempre")
    p.add_argument("--threads", type=int, default=8, help="Hilos de CPU para PaddleOCR")
    p.add_argument("-v", "--verbose", action="store_true")
    add_preprocess_args(p)
    add_tesseract_args(p)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = PipelineConfig(
        input_dir=args.input, output_dir=args.output, engine=args.engine, dpi=args.dpi,
        preprocess=build_preprocess_config(args), min_native_chars=args.min_native_chars,
        use_native_text=not args.no_native, folder=args.folder, limit=args.limit,
        limit_per_folder=args.limit_per_folder, order=args.order, force=args.force,
        tesseract_cmd=args.tesseract_cmd, tessdata_dir=args.tessdata_dir or DEFAULT_TESSDATA_DIR,
        tesseract_psm=args.psm, cpu_threads=args.threads,
    )
    log = setup_logging(cfg.output_dir / "pipeline.log", args.verbose)
    log.info("Config: motor=%s dpi=%d preproc=%s folder=%s limit=%s force=%s",
             cfg.engine, cfg.dpi, cfg.preprocess.active_steps() or "off", cfg.folder, cfg.limit, cfg.force)

    ok, msg = get_engine_class(cfg.engine).check_available(**cfg.engine_options())
    if not ok:
        log.error("El motor '%s' no está disponible:\n%s", cfg.engine, msg)
        return 2
    log.info(msg)

    from ocr_pipeline.pipeline import run
    try:
        stats = run(cfg)
    except EngineUnavailableError as e:
        log.error("%s", e)
        return 2
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario. Vuelve a ejecutar para reanudar.")
        return 130
    return 1 if stats.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
