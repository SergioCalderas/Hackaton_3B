"""Switch local/online por variables de entorno y fábrica de modelos (sin red)."""
import pytest

from analisis.config import Ajustes, ConfiguracionError
from analisis.esquemas import ExtraccionUsoSuelo
from analisis.llm import crear_llm, esquema_json_obligatorio, llm_estructurado


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    for v in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "OLLAMA_MODEL", "CLAUDE_MODEL", "OCR_DPI", "FECHA_REFERENCIA",
              "DICTAMEN_LLM"):
        monkeypatch.delenv(v, raising=False)
    crear_llm.cache_clear()
    llm_estructurado.cache_clear()


def test_por_defecto_es_local_con_qwen(monkeypatch):
    aj = Ajustes.desde_entorno()
    assert aj.proveedor == "local" and aj.modelo == "qwen3.5:9b"
    llm = crear_llm(aj)
    assert type(llm).__name__ == "ChatOllama"
    assert llm.reasoning is False            # thinking apagado: indispensable para el tiempo
    assert llm.num_gpu == 99 and llm.num_ctx == 8192 and llm.temperature == 0


@pytest.mark.parametrize("valor", ["online", "claude", "ANTHROPIC"])
def test_online_usa_claude_haiku(monkeypatch, valor):
    monkeypatch.setenv("LLM_PROVIDER", valor)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    aj = Ajustes.desde_entorno()
    assert aj.proveedor == "online" and aj.modelo == "claude-haiku-5-5"
    llm = crear_llm(aj)
    assert type(llm).__name__ == "ChatAnthropic" and llm.model == "claude-haiku-5-5"
    assert aj.max_chars_doc > Ajustes().max_chars_local


def test_online_sin_api_key_explica_el_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "online")
    aj = Ajustes.desde_entorno()
    with pytest.raises(ConfiguracionError, match="ANTHROPIC_API_KEY"):
        aj.validar()


def test_valores_invalidos(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gpt")
    with pytest.raises(ConfiguracionError, match="local"):
        Ajustes.desde_entorno()
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("FECHA_REFERENCIA", "21/11/2026")
    with pytest.raises(ConfiguracionError, match="AAAA-MM-DD"):
        Ajustes.desde_entorno()


def test_fecha_referencia_y_overrides(monkeypatch):
    monkeypatch.setenv("FECHA_REFERENCIA", "2025-06-30")
    aj = Ajustes.desde_entorno(ocr_dpi=300)
    assert aj.fecha_referencia.isoformat() == "2025-06-30" and aj.ocr_dpi == 300


def test_esquema_ollama_obliga_todas_las_propiedades():
    s = esquema_json_obligatorio(ExtraccionUsoSuelo)
    assert set(s["required"]) == set(s["properties"])
    assert {"uso_autorizado", "giro", "compatible_comercial"} <= set(s["required"])
