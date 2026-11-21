"""Punta a punta con los PDFs del reto: OCR real (sin caché) + LLM real + validación + dictamen.

Verifica el estado esperado y que cada expediente se analice en menos de TIEMPO_OBJETIVO_S (60 s).
La carga inicial del modelo en la GPU (~15 s, una sola vez) no cuenta: se precarga antes.

    .venv\\Scripts\\python -m pytest -m "slow and llm" -s
"""
import pytest

from analisis import ejemplos
from analisis.config import Ajustes
from analisis.grafo import analizar_expediente
from analisis.llm import estado_ollama, precalentar
from analisis.ocr_rapido import resolver_idioma

pytestmark = [pytest.mark.slow, pytest.mark.llm]


@pytest.fixture(scope="module")
def aj():
    aj = Ajustes.desde_entorno(ocr_cache=False)
    try:
        resolver_idioma(aj.ocr_idioma)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Tesseract no disponible: {e}")
    if aj.es_local:
        est = estado_ollama(aj)
        if not (est["servidor"] and est["modelo_instalado"]):
            pytest.skip(f"Ollama o {aj.ollama_modelo} no disponible")
        precalentar(aj)
    return aj


@pytest.mark.parametrize("nombre", [n for n in ejemplos.EXPEDIENTES if n in ejemplos.disponibles()])
def test_expediente_en_menos_de_un_minuto(nombre, aj):
    res = analizar_expediente(ejemplos.rutas(nombre), aj)
    t = res["tiempos"]
    print(f"\n{nombre}: {res['estado']} en {t['total_s']:.1f} s (OCR máx {t['ocr_max_s']:.1f} s, "
          f"LLM máx {t['llm_extraccion_max_s']:.1f} s, dictamen {t['dictamen_s']:.1f} s, {int(t['paginas'])} págs.)")
    assert t["total_s"] < aj.tiempo_objetivo_s
    esperado = ejemplos.EXPEDIENTES[nombre]["esperado"]
    if esperado:
        assert res["estado"] == esperado
    verificadas = [e["verificada"] for h in res["hallazgos"] for e in h["evidencias"]]
    assert sum(verificadas) / max(1, len(verificadas)) > 0.6, "la mayoría de la evidencia debe ubicarse en el texto"
