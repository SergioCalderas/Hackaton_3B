"""El visor de Streamlit carga sin errores (no ejecuta OCR ni LLM)."""
import os

import pytest

pytest.importorskip("streamlit")


def test_app_carga(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("LLM_PROVIDER", "local")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    at = AppTest.from_file(os.path.join(raiz, "app_streamlit.py"), default_timeout=60).run()
    assert not at.exception
    assert [b.label for b in at.button][:2] == ["Analizar expediente", "Ejecutar pruebas"]
    assert any("Sintético A" in o for o in at.selectbox[0].options)


def test_frase_de_evidencia_con_enlace_discreto(tmp_path, monkeypatch):
    from analisis import visor

    monkeypatch.setattr(visor, "EXPEDIENTES_STATIC", tmp_path)
    enl = visor.Enlaces("abc", {"Predial/a.pdf": "01_a.pdf"})
    ev = [{"documento": "Predial/a.pdf", "tipo_documento": "Predial", "pagina": 2, "cita": "CLAVE <123> $5",
           "verificada": True},
          {"documento": "Predial/a.pdf", "tipo_documento": "Predial", "pagina": 2, "cita": "x", "verificada": True}]
    html = visor.frase_evidencias(ev, enl)
    assert html.startswith("Como se visualiza en la <span class=\"ev\">")
    assert 'href="app/static/expedientes/abc/01_a.pdf#page=2"' in html and "Abrir página 2" in html
    assert html.count('class="ev"') == 1                       # sin duplicados
    assert "&lt;123&gt;" in html and "&#36;5" in html           # escapa HTML y $
    assert "no localizada" in visor.frase_evidencias([{**ev[0], "verificada": False}], enl)
