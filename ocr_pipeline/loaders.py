"""Carga de documentos: PDFs (texto nativo o render a imagen) e imágenes sueltas."""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

try:  # PyMuPDF >= 1.24.3 expone `pymupdf`; `fitz` está obsoleto desde la 2.x
    import pymupdf as fitz
except ImportError:  # pragma: no cover - versiones antiguas
    import fitz
from PIL import Image, ImageOps

from .config import IMAGE_EXTENSIONS, PDF_EXTENSIONS


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def useful_chars(text: str) -> int:
    """Cuenta caracteres alfanuméricos (ignora espacios, puntuación y basura)."""
    return sum(1 for c in text if c.isalnum())


def load_image_file(path: Path) -> np.ndarray:
    """Carga una imagen como BGR respetando la orientación EXIF.

    Se usa PIL en lugar de cv2.imread porque cv2.imread falla con rutas
    Unicode (acentos) en Windows.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        rgb = np.array(im)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class DocumentSource:
    """Abstracción de un documento con N páginas.

    - PDF: cada página puede tener texto nativo y/o renderizarse a imagen.
    - Imagen: una sola página, sin texto nativo.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        ext = self.path.suffix.lower()
        self._doc = None
        self._image = None
        if ext in PDF_EXTENSIONS:
            self.kind = "pdf"
            self._doc = fitz.open(self.path)
            if self._doc.needs_pass and not self._doc.authenticate(""):
                raise RuntimeError("PDF protegido con contraseña")
            self.num_pages = self._doc.page_count
        elif ext in IMAGE_EXTENSIONS:
            self.kind = "image"
            self.num_pages = 1
        else:
            raise ValueError(f"Extensión no soportada: {ext}")

    # -- contexto -------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    # -- acceso a páginas ----------------------------------------------
    def native_text(self, index: int) -> str:
        if self.kind != "pdf":
            return ""
        return self._doc[index].get_text("text") or ""

    def render(self, index: int, dpi: int = 300, max_pixels: int = 60_000_000) -> tuple[np.ndarray, int]:
        """Devuelve (imagen BGR, dpi efectivo)."""
        if self.kind == "image":
            if self._image is None:
                self._image = load_image_file(self.path)
            return self._image, 0

        page = self._doc[index]
        rect = page.rect
        zoom = dpi / 72.0
        pixels = rect.width * zoom * rect.height * zoom
        if pixels > max_pixels:  # páginas enormes (planos): reducir resolución
            zoom *= (max_pixels / pixels) ** 0.5
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return bgr, round(zoom * 72)
