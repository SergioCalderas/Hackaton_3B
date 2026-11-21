"""Configuración central del pipeline OCR."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PIPELINE_VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS

# Carpetas que nunca se consideran entrada (salidas, entornos, datos de modelos...).
EXCLUDED_DIRS = {".git", ".venv", "venv", ".dist", "output", "comparison", "tessdata",
                 "ocr_pipeline", "__pycache__"}

# Rutas por defecto de Tesseract en Windows.
DEFAULT_TESSERACT_CMDS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
DEFAULT_TESSDATA_DIR = PROJECT_ROOT / "tessdata"


@dataclass
class PreprocessConfig:
    """Pasos de preprocesamiento con OpenCV. `enabled` es el interruptor general."""
    enabled: bool = False
    grayscale: bool = True
    denoise: bool = True
    deskew: bool = True
    binarize: bool = True
    binarize_method: str = "adaptive"   # "adaptive" | "otsu"
    max_skew_deg: float = 5.0           # rango de búsqueda del deskew (±grados)

    def active_steps(self) -> list[str]:
        if not self.enabled:
            return []
        steps = []
        if self.grayscale or self.binarize or self.denoise:
            steps.append("grayscale")
        if self.denoise:
            steps.append("denoise")
        if self.deskew:
            steps.append("deskew")
        if self.binarize:
            steps.append(f"binarize:{self.binarize_method}")
        return steps


@dataclass
class PipelineConfig:
    input_dir: Path = PROJECT_ROOT
    output_dir: Path = PROJECT_ROOT / "output"
    engine: str = "paddle"
    dpi: int = 300
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)

    # Una página usa su capa de texto nativa si tiene al menos estos caracteres alfanuméricos.
    min_native_chars: int = 50
    use_native_text: bool = True

    # Selección de archivos
    folder: str | None = None
    limit: int | None = None
    limit_per_folder: int | None = None
    order: str = "name"                 # "name" | "size" (size = más pequeños primero)
    force: bool = False

    # Umbrales para el estado del documento
    low_conf_threshold: float = 0.80
    low_text_chars_per_page: int = 80

    # Opciones de motores
    lang_paddle: str = "es"
    lang_tesseract: str = "spa"
    tesseract_cmd: str | None = None
    tessdata_dir: Path | None = DEFAULT_TESSDATA_DIR
    tesseract_psm: int = 3
    cpu_threads: int = 8

    # Límite de seguridad para páginas gigantes (planos): se baja el DPI si se excede.
    max_render_pixels: int = 60_000_000

    def engine_options(self) -> dict:
        return {
            "lang_paddle": self.lang_paddle,
            "lang_tesseract": self.lang_tesseract,
            "tesseract_cmd": self.tesseract_cmd,
            "tessdata_dir": self.tessdata_dir,
            "tesseract_psm": self.tesseract_psm,
            "cpu_threads": self.cpu_threads,
        }
