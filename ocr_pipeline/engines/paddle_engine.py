"""Motor PaddleOCR 3.x en CPU, idioma español."""
from __future__ import annotations

import logging
import os

import numpy as np

from .base import EngineUnavailableError, OCREngine, OCRLine, OCRResult, lines_to_text, mean_confidence

# Evita que PaddleX consulte servidores remotos al iniciar (los modelos quedan en caché local).
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

INSTALL_HELP = """\
PaddleOCR no está disponible. Dentro del .venv:
  pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
  pip install paddleocr==3.0.3
La primera ejecución descarga los modelos (~100 MB) a %USERPROFILE%\\.paddlex\\official_models.
"""


class PaddleEngine(OCREngine):
    name = "paddle"

    @classmethod
    def check_available(cls, **options) -> tuple[bool, str]:
        try:
            import paddle  # noqa: F401
            import paddleocr  # noqa: F401
        except Exception as e:
            return False, f"{e}\n{INSTALL_HELP}"
        return True, f"PaddleOCR {paddleocr.__version__} / paddle {paddle.__version__}"

    def __init__(self, lang_paddle: str = "es", cpu_threads: int = 8,
                 doc_orientation: bool = True, **_):
        ok, msg = self.check_available()
        if not ok:
            raise EngineUnavailableError(msg)
        from paddleocr import PaddleOCR

        for name in ("paddlex", "paddleocr", "ppocr"):
            logging.getLogger(name).setLevel(logging.WARNING)

        self._ocr = PaddleOCR(
            lang=lang_paddle,
            device="cpu",
            cpu_threads=cpu_threads,
            # Detecta páginas escaneadas giradas 90/180/270°.
            use_doc_orientation_classify=doc_orientation,
            # El "unwarping" deforma documentos planos y es lento: apagado.
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    def ocr(self, image: np.ndarray) -> OCRResult:
        results = self._ocr.predict(image)
        lines: list[OCRLine] = []
        for res in results:
            texts = res["rec_texts"]
            scores = res["rec_scores"]
            boxes = res["rec_boxes"]
            for text, score, box in zip(texts, scores, boxes):
                if not text or not text.strip():
                    continue
                x0, y0, x1, y1 = (float(v) for v in box[:4])
                lines.append(OCRLine(text.strip(), float(score), (x0, y0, x1, y1)))
        return OCRResult(lines_to_text(lines), mean_confidence(lines), lines)
