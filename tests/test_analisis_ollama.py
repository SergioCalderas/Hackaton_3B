"""Extracción con el LLM real (Ollama). Se saltan si Ollama o el modelo no están disponibles.

    .venv\\Scripts\\python -m pytest -m "llm and not slow"
"""
import pytest
from conftest import PREDIAL, USO_SUELO, hacer_documento

from analisis import agentes
from analisis.config import Ajustes
from analisis.llm import estado_ollama, precalentar
from ocr_pipeline.matching import enriquecer_documento
from ocr_pipeline.normalize import norm_name

pytestmark = pytest.mark.llm


@pytest.fixture(scope="module")
def aj():
    aj = Ajustes.desde_entorno(proveedor="local")
    est = estado_ollama(aj)
    if not (est["servidor"] and est["modelo_instalado"]):
        pytest.skip(f"Ollama o {aj.ollama_modelo} no disponible")
    precalentar(aj)
    return aj


def _doc(texto, tipo):
    return enriquecer_documento(hacer_documento(texto, tipo, f"{tipo}/prueba.pdf"), tipo)


def test_extractor_predial_real(aj):
    r = agentes.extraer(_doc(PREDIAL, "Predial"), "Predial", aj)
    c = r.campos
    assert r.error_llm is None
    assert set(norm_name(c["propietario"].valor).split()) == {"QUINTANAR", "LEDESMA", "ROSA", "MARIA"}
    assert c["superficie_terreno_m2"].valor == 245.0 and c["ejercicio_fiscal"].valor == 2025
    assert c["clave_catastral"].coincide_reglas and c["propietario"].evidencia.verificada
    assert r.tiempos["llm_s"] < 20, "la extracción de un predial debe tardar segundos"


def test_extractor_uso_de_suelo_real_detecta_uso_habitacional(aj):
    r = agentes.extraer(_doc(USO_SUELO, "UsoDeSuelo"), "UsoDeSuelo", aj)
    assert r.campos["compatible_comercial"].valor == "no"
    assert "HABITACIONAL" in r.campos["uso_autorizado"].valor.upper().replace(" ", "")
    assert r.campos["fecha_expedicion"].valor == "2025-03-03"
