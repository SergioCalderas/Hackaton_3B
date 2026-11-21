"""Motor híbrido: Tesseract (sin preprocesar) por defecto y PaddleOCR (con
preprocesamiento) como respaldo por página.

Regla (decidida con compare_engines.py):
  1. Tesseract raw -> calidad = % de palabras válidas en español.
  2. Si conf_tesseract < conf_threshold o calidad < quality_threshold:
       Paddle + preprocesamiento -> calidad_paddle
       se queda el resultado con MÁS palabras válidas (nunca se decide por confianza,
       porque la confianza de Paddle está mal calibrada).
"""
from __future__ import annotations

import numpy as np

from ..config import PreprocessConfig
from ..preprocess import preprocess
from ..quality import load_lexicon, text_quality, valid_word_count
from .base import EngineUnavailableError, OCREngine, OCRResult
from .paddle_engine import PaddleEngine
from .tesseract_engine import TesseractEngine


class HybridEngine(OCREngine):
    name = "hybrid"

    @classmethod
    def check_available(cls, **options) -> tuple[bool, str]:
        ok_t, msg_t = TesseractEngine.check_available(**options)
        if not ok_t:
            return False, msg_t
        ok_p, msg_p = PaddleEngine.check_available(**options)
        if not load_lexicon():
            return False, "No hay léxico de español para medir la calidad (tessdata/spa_words.txt)."
        note = "" if ok_p else " (Paddle NO disponible: sin respaldo)"
        return True, f"Híbrido: {msg_t} + {msg_p.splitlines()[0]}{note}"

    def __init__(self, conf_threshold: float = 0.75, quality_threshold: float = 0.70, **options):
        self.options = options
        self.conf_threshold = conf_threshold
        self.quality_threshold = quality_threshold
        self.tesseract = TesseractEngine(**options)
        self._paddle: PaddleEngine | None = None
        self._paddle_failed = False
        self.paddle_pre = PreprocessConfig(enabled=True)  # gris + mediana + deskew + binarización
        self.lexicon = load_lexicon()

    def _get_paddle(self) -> PaddleEngine | None:
        if self._paddle is None and not self._paddle_failed:
            try:
                self._paddle = PaddleEngine(**self.options)
            except EngineUnavailableError:
                self._paddle_failed = True
        return self._paddle

    def ocr(self, image: np.ndarray) -> OCRResult:
        tess = self.tesseract.ocr(image)
        t_quality = text_quality(tess.text, self.lexicon)
        info = {"tesseract_conf": _r(tess.confidence), "tesseract_quality": _r(t_quality), "fallback": False}

        needs_fallback = (tess.confidence is None or tess.confidence < self.conf_threshold
                          or t_quality is None or t_quality < self.quality_threshold)
        paddle = self._get_paddle() if needs_fallback else None
        if paddle is None:
            tess.engine, tess.extra = "tesseract", {**info, "quality": _r(t_quality)}
            return tess

        pimg, _ = preprocess(image, self.paddle_pre)
        pad = paddle.ocr(pimg)
        p_quality = text_quality(pad.text, self.lexicon)
        t_valid = valid_word_count(tess.text, self.lexicon)
        p_valid = valid_word_count(pad.text, self.lexicon)
        info.update({"fallback": True, "paddle_conf": _r(pad.confidence), "paddle_quality": _r(p_quality),
                     "tesseract_valid_words": t_valid, "paddle_valid_words": p_valid})

        best, best_q = (pad, p_quality) if p_valid > t_valid else (tess, t_quality)
        best.engine = "paddle" if best is pad else "tesseract"
        best.extra = {**info, "quality": _r(best_q)}
        return best


def _r(v):
    return round(v, 4) if isinstance(v, (int, float)) else None
