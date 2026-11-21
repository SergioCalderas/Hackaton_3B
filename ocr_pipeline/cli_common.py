"""Utilidades compartidas por los scripts de línea de comandos."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

from .config import PreprocessConfig


class TqdmLoggingHandler(logging.Handler):
    """Escribe logs sin romper la barra de progreso."""

    def emit(self, record):
        try:
            tqdm.write(self.format(record), file=sys.stderr)
        except Exception:
            self.handleError(record)


def setup_logging(log_file: Path, verbose: bool = False) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ocr_pipeline")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    ch = TqdmLoggingHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


def add_preprocess_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("preprocesamiento (OpenCV)")
    g.add_argument("--preprocess", action=argparse.BooleanOptionalAction, default=False,
                   help="Activa/desactiva el preprocesamiento (default: desactivado)")
    g.add_argument("--pre-steps", default="grayscale,denoise,deskew,binarize",
                   help="Pasos a aplicar si --preprocess está activo (lista separada por comas)")
    g.add_argument("--binarize-method", choices=["adaptive", "otsu"], default="adaptive")


def build_preprocess_config(args, enabled: bool | None = None) -> PreprocessConfig:
    steps = {s.strip() for s in args.pre_steps.split(",") if s.strip()}
    return PreprocessConfig(
        enabled=args.preprocess if enabled is None else enabled,
        grayscale="grayscale" in steps,
        denoise="denoise" in steps,
        deskew="deskew" in steps,
        binarize="binarize" in steps,
        binarize_method=args.binarize_method,
    )


def add_tesseract_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("tesseract")
    g.add_argument("--tesseract-cmd", default=None, help="Ruta a tesseract.exe si no está en el PATH")
    g.add_argument("--tessdata-dir", type=Path, default=None,
                   help="Carpeta con *.traineddata (default: ./tessdata del proyecto)")
    g.add_argument("--psm", type=int, default=3, help="Page segmentation mode de Tesseract")
