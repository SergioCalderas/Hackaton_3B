"""Texto extraído para la vista del caso (procesamiento/texto.py + rutas Flask). Sin OCR real."""
import sys
import threading
import types

import pytest
from conftest import PREDIAL, RAIZ, hacer_documento

from ocr_pipeline.matching import enriquecer_documento
from procesamiento import texto


@pytest.fixture
def cache_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(texto, "DIR_CACHE", tmp_path / ".cache_texto")
    return tmp_path


@pytest.fixture
def ocr_falso(monkeypatch):
    """procesar_documento simulado (devuelve un Documento completo con el texto sintético del predial)."""
    import ocr_pipeline.servicio as servicio
    llamadas = []

    def falso(ruta, tipo=None, nombre_original=None, modo="completo"):
        llamadas.append((tipo, modo))
        return enriquecer_documento(hacer_documento(PREDIAL, tipo, nombre_original or "x.pdf"))

    monkeypatch.setattr(servicio, "procesar_documento", falso)
    if "procesamiento.pipeline" not in sys.modules:  # sin rapidocr: candado simulado
        try:
            import procesamiento.pipeline  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "procesamiento.pipeline",
                                types.SimpleNamespace(CANDADO_OCR=threading.Lock()))
    return llamadas


def test_genera_una_vez_y_luego_usa_cache(cache_tmp, ocr_falso):
    r1 = texto.de_bytes(b"%PDF-falso", "02 Predial.pdf", tipo="predial")
    assert r1["estado"] == "OK" and r1["origen"] == "ocr" and r1["num_paginas"] == 1
    assert r1["motores"] == ["tesseract"] and r1["calidad_texto"] == 0.9
    assert "CLAVE CATASTRAL 112 03 145 18 00 0000" in r1["paginas"][0]["texto"]
    assert r1["campos"]["ClaveCatastral"]["valor"] == "112 03 145 18 00 0000"
    assert r1["campos"]["Propietario"]["pagina"] == 1
    r2 = texto.de_bytes(b"%PDF-falso", "otro-nombre.pdf", tipo="predial")
    assert r2["origen"] == "cache" and len(ocr_falso) == 1          # no repite OCR (misma huella)
    assert (cache_tmp / ".cache_texto" / f"{r1['sha256']}.json").is_file()


def test_solo_cache_no_corre_ocr(cache_tmp, ocr_falso):
    r = texto.de_bytes(b"%PDF-nuevo", "nuevo.pdf", tipo="predial", generar=False)
    assert r["estado"] == "SIN_EXTRAER" and ocr_falso == []


def test_campos_se_recalculan_segun_el_tipo(cache_tmp, ocr_falso):
    texto.de_bytes(b"%PDF-falso", "a.pdf", tipo="predial")
    r = texto.de_bytes(b"%PDF-falso", "a.pdf", tipo=None)
    assert r["origen"] == "cache" and "ClaveCatastral" in r["campos"]


@pytest.mark.parametrize("ruta", ["../README.md", "/docs/../../server/app.py", "https://evil.example/x.pdf",
                                  "//evil.example/x.pdf", "docs/predial/no-existe.pdf", "favicon.png.txt", ""])
def test_rutas_invalidas(ruta):
    with pytest.raises(texto.TextoError):
        texto.ruta_publica(ruta)


def test_ruta_valida_del_front():
    p = texto.ruta_publica("/docs/predial/caso-001.pdf")
    assert p.is_file() and p.parent.name == "predial" and (RAIZ / "public") in p.parents


# ---------------------------------------------------------------------------
# Rutas Flask (solo en el entorno del servidor: requiere flask + rapidocr del filtro)
# ---------------------------------------------------------------------------
@pytest.fixture
def cliente(cache_tmp, ocr_falso):
    pytest.importorskip("flask")
    pytest.importorskip("rapidocr")
    from flask import Flask

    from procesamiento.api import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client()


def test_api_texto(cliente):
    r = cliente.get("/api/texto?ruta=/docs/predial/caso-001.pdf&tipo=predial&solo_cache=1")
    assert r.status_code == 200 and r.get_json()["estado"] == "SIN_EXTRAER"
    r = cliente.get("/api/texto?ruta=/docs/predial/caso-001.pdf&tipo=predial")
    j = r.get_json()
    assert r.status_code == 200 and j["estado"] == "OK" and j["origen"] == "ocr"
    r = cliente.get("/api/texto?ruta=/docs/predial/caso-001.pdf&tipo=predial&solo_cache=1")
    assert r.get_json()["origen"] == "cache"


def test_api_texto_errores(cliente):
    assert cliente.get("/api/texto?ruta=../server/app.py").status_code == 400
    assert cliente.get("/api/texto?ruta=/docs/predial/no-existe.pdf").status_code == 404
    assert "error" in cliente.get("/api/texto").get_json()
