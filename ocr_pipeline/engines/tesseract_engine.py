"""Motor Tesseract (pytesseract) usando la carpeta tessdata/ del proyecto."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import cv2
import numpy as np

from ..config import DEFAULT_TESSERACT_CMDS
from .base import EngineUnavailableError, OCREngine, OCRLine, OCRResult, mean_confidence

INSTALL_HELP = """\
Tesseract no está disponible. Para instalarlo en Windows:
  1. winget install UB-Mannheim.TesseractOCR
     (o el instalador de https://github.com/UB-Mannheim/tesseract/wiki)
  2. Idioma español: descarga spa.traineddata de
     https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
     a la carpeta tessdata/ del proyecto y copia ahí también eng.traineddata y
     osd.traineddata desde C:\\Program Files\\Tesseract-OCR\\tessdata\\
  3. Si lo instalaste en otra ruta, usa --tesseract-cmd "RUTA\\tesseract.exe".
"""


def _find_tesseract(cmd: str | None) -> str | None:
    if cmd and Path(cmd).is_file():
        return cmd
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in DEFAULT_TESSERACT_CMDS:
        if Path(candidate).is_file():
            return candidate
    return None


class TesseractEngine(OCREngine):
    name = "tesseract"

    @classmethod
    def _setup(cls, tesseract_cmd=None, tessdata_dir=None, **_):
        try:
            import pytesseract
        except ImportError:
            raise EngineUnavailableError("Falta el paquete pytesseract: pip install pytesseract\n" + INSTALL_HELP)
        cmd = _find_tesseract(tesseract_cmd)
        if not cmd:
            raise EngineUnavailableError(INSTALL_HELP)
        pytesseract.pytesseract.tesseract_cmd = cmd
        # TESSDATA_PREFIX evita problemas de comillas con --tessdata-dir en Windows.
        if tessdata_dir and Path(tessdata_dir).is_dir():
            os.environ["TESSDATA_PREFIX"] = str(Path(tessdata_dir).resolve())
        return pytesseract

    @classmethod
    def check_available(cls, lang_tesseract="spa", **options) -> tuple[bool, str]:
        try:
            pytesseract = cls._setup(**options)
            langs = set(pytesseract.get_languages(config=""))
        except EngineUnavailableError as e:
            return False, str(e)
        except Exception as e:  # binario roto, permisos, etc.
            return False, f"Error al ejecutar Tesseract: {e}\n{INSTALL_HELP}"
        missing = [l for l in lang_tesseract.split("+") if l not in langs]
        if missing:
            where = os.environ.get("TESSDATA_PREFIX", "tessdata de la instalación")
            return False, (f"Tesseract no tiene el idioma {missing} en {where}. "
                           f"Idiomas disponibles: {sorted(langs)}\n{INSTALL_HELP}")
        return True, f"Tesseract OK ({pytesseract.get_tesseract_version()}), idiomas: {sorted(langs)}"

    def __init__(self, lang_tesseract: str = "spa", tesseract_psm: int = 3, **options):
        ok, msg = self.check_available(lang_tesseract=lang_tesseract, **options)
        if not ok:
            raise EngineUnavailableError(msg)
        self._pt = self._setup(**options)
        self.lang = lang_tesseract
        self.config = f"--oem 1 --psm {tesseract_psm}"

    def ocr(self, image: np.ndarray) -> OCRResult:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 else image
        data = self._pt.image_to_data(rgb, lang=self.lang, config=self.config,
                                      output_type=self._pt.Output.DICT)
        # Agrupar palabras por (bloque, párrafo, línea): Tesseract ya da orden de lectura.
        groups: dict[tuple, list[int]] = {}
        for i, word in enumerate(data["text"]):
            if word and word.strip():
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                groups.setdefault(key, []).append(i)

        lines: list[OCRLine] = []
        text_parts: list[str] = []
        prev_block_par = None
        for key, idxs in groups.items():
            words = [data["text"][i] for i in idxs]
            confs = [float(data["conf"][i]) for i in idxs if float(data["conf"][i]) >= 0]
            x0 = min(data["left"][i] for i in idxs)
            y0 = min(data["top"][i] for i in idxs)
            x1 = max(data["left"][i] + data["width"][i] for i in idxs)
            y1 = max(data["top"][i] + data["height"][i] for i in idxs)
            line_text = " ".join(words)
            conf = (sum(confs) / len(confs) / 100.0) if confs else None
            lines.append(OCRLine(line_text, conf, (x0, y0, x1, y1)))
            if prev_block_par is not None and key[:2] != prev_block_par:
                text_parts.append("")  # línea en blanco entre párrafos
            text_parts.append(line_text)
            prev_block_par = key[:2]

        # Confianza por palabra (más fiel que por línea)
        word_confs = [(float(c), len(t)) for t, c in zip(data["text"], data["conf"])
                      if t and t.strip() and float(c) >= 0]
        total = sum(w for _, w in word_confs)
        confidence = (sum(c * w for c, w in word_confs) / total / 100.0) if total else mean_confidence(lines)
        return OCRResult("\n".join(text_parts), confidence, lines)
