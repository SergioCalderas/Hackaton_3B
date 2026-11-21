"""Registro de motores OCR. Para agregar uno nuevo, impórtalo y añádelo a ENGINES."""
from __future__ import annotations

from .base import EngineUnavailableError, OCREngine, OCRLine, OCRResult
from .paddle_engine import PaddleEngine
from .tesseract_engine import TesseractEngine

ENGINES: dict[str, type[OCREngine]] = {
    PaddleEngine.name: PaddleEngine,
    TesseractEngine.name: TesseractEngine,
    # "easyocr": EasyOCREngine,
}


def get_engine_class(name: str) -> type[OCREngine]:
    try:
        return ENGINES[name]
    except KeyError:
        raise ValueError(f"Motor desconocido '{name}'. Opciones: {sorted(ENGINES)}")


def create_engine(name: str, **options) -> OCREngine:
    return get_engine_class(name)(**options)


__all__ = ["ENGINES", "EngineUnavailableError", "OCREngine", "OCRLine", "OCRResult",
           "create_engine", "get_engine_class"]
