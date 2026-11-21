"""Integración con OCR real sobre documentos SINTÉTICOS del reto (lento: pytest -m slow).

Requiere Tesseract + tessdata/ y las carpetas de documentos del reto (están en main).
"""
import pytest
from conftest import RAIZ

pytestmark = pytest.mark.slow

PREDIAL = RAIZ / "Predial" / "02 Predial.pdf"
ESCRITURA = RAIZ / "Escritura" / "01 Escritura.pdf"


@pytest.fixture(scope="module", autouse=True)
def requisitos():
    from ocr_pipeline.engines import get_engine_class
    from ocr_pipeline.config import PipelineConfig
    ok, msg = get_engine_class("tesseract").check_available(**PipelineConfig().engine_options())
    if not ok:
        pytest.skip(f"Tesseract no disponible: {msg.splitlines()[0]}")
    if not (PREDIAL.exists() and ESCRITURA.exists()):
        pytest.skip("Faltan los PDFs sintéticos del reto")


def test_procesar_documento_real():
    from ocr_pipeline import procesar_documento
    d = procesar_documento(PREDIAL, "Predial")
    assert d["Estado"] == "ok" and d["TipoDetectado"] == "Predial"
    assert d["CamposExtraidos"]["ClaveCatastral"]["Normalizado"] == "1120314518000000"


def test_verificar_expediente_real_compacto():
    from ocr_pipeline import verificar_expediente
    exp = verificar_expediente([(ESCRITURA, "Escritura"), (PREDIAL, "Predial")], modo="compacto")
    assert exp["Modo"] == "compacto" and exp["NivelMatch"] == "alto"
    assert "ClaveCatastral" in exp["CamposCoinciden"]
    assert set(exp["DocumentosFaltantes"]) == {"Alineamiento", "UsoDeSuelo"}
