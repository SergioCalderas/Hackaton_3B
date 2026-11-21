"""Endpoints del análisis con IA en el servidor Flask (procesamiento/api_analisis.py), sin OCR ni LLM."""
import pytest

flask = pytest.importorskip("flask")

import procesamiento.api_analisis as api  # noqa: E402
from procesamiento import texto  # noqa: E402


@pytest.fixture
def cliente(monkeypatch):
    llamadas = []

    def falso(entradas, aj=None):
        llamadas.append(entradas)
        return {"estado": "Requiere revisión", "semaforo": "AMARILLO", "hallazgos": [], "tiempos": {"total_s": 1.0}}

    monkeypatch.setattr("analisis.analizar_expediente", falso)
    api._resultados.clear()
    app = flask.Flask(__name__)
    app.register_blueprint(api.bp)
    return app.test_client(), llamadas


def _pdf_publico():
    return next(p for p in (texto.DIR_PUBLICO / "docs").rglob("*.pdf"))


def test_caso_usa_rutas_publicas_y_guarda_resultado(cliente):
    c, llamadas = cliente
    p = _pdf_publico()
    ruta = "/" + p.relative_to(texto.DIR_PUBLICO).as_posix()
    cuerpo = {"documentos": [{"ruta": ruta, "tipo": "numero_oficial"}]}
    r = c.post("/api/analisis/caso", json=cuerpo)
    assert r.status_code == 200 and r.get_json()["desde_cache"] is False
    assert llamadas[0][0]["nombre"] == ruta and llamadas[0][0]["tipo"] == "Alineamiento"
    assert c.post("/api/analisis/caso", json=cuerpo).get_json()["desde_cache"] is True
    assert c.post("/api/analisis/caso", json={**cuerpo, "forzar": True}).get_json()["desde_cache"] is False
    assert len(llamadas) == 2


def test_caso_rechaza_rutas_fuera_de_public(cliente):
    c, _ = cliente
    assert c.post("/api/analisis/caso", json={"documentos": []}).status_code == 400
    r = c.post("/api/analisis/caso", json={"documentos": [{"ruta": "../.env", "tipo": "predial"}]})
    assert r.status_code == 400
    r = c.post("/api/analisis/caso", json={"documentos": [{"ruta": "https://x.com/a.pdf", "tipo": "predial"}]})
    assert r.status_code == 400


def test_miniatura(cliente):
    c, _ = cliente
    ruta = "/" + _pdf_publico().relative_to(texto.DIR_PUBLICO).as_posix()
    r = c.get(f"/api/analisis/miniatura?ruta={ruta}&pagina=1")
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data[:2] == b"\xff\xd8"
