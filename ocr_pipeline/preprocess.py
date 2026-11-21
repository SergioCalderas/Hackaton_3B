"""Preprocesamiento de imágenes con OpenCV antes del OCR.

Cada paso se puede activar/desactivar desde PreprocessConfig.
Devuelve siempre una imagen BGR de 3 canales (lo que esperan los motores).
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import PreprocessConfig


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def denoise(gray: np.ndarray) -> np.ndarray:
    # Mediana 3x3: quita "sal y pimienta" del escaneo sin borrar trazos finos y es rápida.
    return cv2.medianBlur(gray, 3)


def estimate_skew(gray: np.ndarray, max_deg: float = 5.0, step: float = 0.25) -> float:
    """Estima la inclinación con perfil de proyección horizontal.

    Se prueba cada ángulo en [-max_deg, max_deg] sobre una versión reducida y
    se elige el que maximiza la varianza de las sumas por renglón (los renglones
    de texto quedan "alineados" con las filas de píxeles).
    """
    h, w = gray.shape[:2]
    scale = 1000.0 / max(h, w)
    small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    sh, sw = bw.shape
    center = (sw / 2, sh / 2)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_deg, max_deg + 1e-9, step):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(bw, m, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1, dtype=np.float64)))
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = 255 if img.ndim == 2 else (255, 255, 255)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def binarize(gray: np.ndarray, method: str = "adaptive") -> np.ndarray:
    if method == "otsu":
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return bw
    # Adaptativo: tolera iluminación desigual, sellos y fondos con marca de agua.
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 15)


def preprocess(img: np.ndarray, cfg: PreprocessConfig) -> tuple[np.ndarray, dict]:
    """Aplica los pasos activos. Devuelve (imagen BGR, info con pasos y ángulo)."""
    info: dict = {"steps": [], "skew_angle": None}
    if not cfg.enabled:
        return img, info

    out = img
    if cfg.grayscale or cfg.denoise or cfg.binarize:
        out = to_gray(out)
        info["steps"].append("grayscale")
    if cfg.denoise:
        out = denoise(to_gray(out))
        info["steps"].append("denoise")
    if cfg.deskew:
        angle = estimate_skew(to_gray(out), cfg.max_skew_deg)
        info["skew_angle"] = round(angle, 2)
        if abs(angle) >= 0.25:
            out = rotate(out, angle)
        info["steps"].append("deskew")
    if cfg.binarize:
        out = binarize(to_gray(out), cfg.binarize_method)
        info["steps"].append(f"binarize:{cfg.binarize_method}")

    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    return out, info
