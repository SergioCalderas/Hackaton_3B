"""Interfaz común de motores OCR.

Para agregar un motor nuevo (p. ej. EasyOCR):
  1. Crear una subclase de OCREngine en este paquete con `name`,
     `check_available()` y `ocr()`.
  2. Registrarla en `engines/__init__.py` (diccionario ENGINES).
El pipeline no necesita cambios.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


class EngineUnavailableError(RuntimeError):
    """El motor no está instalado o configurado. El mensaje incluye cómo arreglarlo."""


@dataclass
class OCRLine:
    text: str
    confidence: float | None          # 0..1
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class OCRResult:
    text: str
    confidence: float | None          # promedio 0..1 (None si no hay texto)
    lines: list[OCRLine] = field(default_factory=list)
    engine: str | None = None         # motor que produjo el texto (útil en motores compuestos)
    extra: dict = field(default_factory=dict)  # info adicional para los metadatos


class OCREngine(ABC):
    name: str = "base"

    @classmethod
    def check_available(cls, **options) -> tuple[bool, str]:
        """Devuelve (disponible, mensaje). No debe lanzar excepciones."""
        return True, ""

    @abstractmethod
    def ocr(self, image: np.ndarray) -> OCRResult:
        """Recibe una imagen BGR (numpy) y devuelve el texto en orden de lectura."""


def lines_to_text(lines: list[OCRLine]) -> str:
    """Ordena cajas sueltas en orden de lectura: renglones de arriba a abajo,
    y dentro de cada renglón de izquierda a derecha."""
    if not lines:
        return ""
    heights = sorted(max(1.0, l.bbox[3] - l.bbox[1]) for l in lines)
    tol = heights[len(heights) // 2] * 0.5  # mitad de la altura mediana

    items = sorted(lines, key=lambda l: (l.bbox[1] + l.bbox[3]) / 2)
    rows: list[list[OCRLine]] = []
    row_centers: list[float] = []
    for line in items:
        yc = (line.bbox[1] + line.bbox[3]) / 2
        if rows and abs(yc - row_centers[-1]) <= tol:
            rows[-1].append(line)
            n = len(rows[-1])
            row_centers[-1] = row_centers[-1] + (yc - row_centers[-1]) / n
        else:
            rows.append([line])
            row_centers.append(yc)
    return "\n".join(" ".join(l.text for l in sorted(r, key=lambda l: l.bbox[0])) for r in rows)


def mean_confidence(lines: list[OCRLine]) -> float | None:
    """Promedio de confianza ponderado por longitud del texto de cada caja."""
    pairs = [(l.confidence, len(l.text)) for l in lines if l.confidence is not None and l.text.strip()]
    total = sum(w for _, w in pairs)
    if not total:
        return None
    return sum(c * w for c, w in pairs) / total
