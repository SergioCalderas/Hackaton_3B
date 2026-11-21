"""Capa HTTP (FastAPI) con el OCR simulado: no requiere Tesseract ni Paddle."""
import json

import pytest
from conftest import RAIZ

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

EJEMPLO_DOC = json.loads((RAIZ / "examples" / "documentos.json").read_text(encoding="utf-8"))[0]
EJEMPLO_EXP = json.loads((RAIZ / "examples" / "expedientes.json").read_text(encoding="utf-8"))[0]


@pytest.fixture
def cliente(monkeypatch):
    import api
    llamadas = {}

    def fake_procesar(ruta, tipo=None, nombre_original=None, modo="completo"):
        llamadas.setdefault("procesar", []).append((nombre_original, tipo, modo))
        return {**EJEMPLO_DOC, "NombreArchivo": nombre_original, "Modo": modo}

    def fake_verificar(docs, modo="completo"):
        llamadas["verificar"] = (len(docs), modo)
        return {**EJEMPLO_EXP, "Modo": modo}

    monkeypatch.setattr(api, "precargar", lambda: "simulado")
    monkeypatch.setattr(api, "procesar_documento", fake_procesar)
    monkeypatch.setattr(api, "verificar_expediente", fake_verificar)
    with TestClient(api.app) as c:
        c.llamadas = llamadas
        yield c


def test_salud(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200 and r.json()["motor"] == "simulado"


def test_documento_y_modo(cliente):
    r = cliente.post("/documento?modo=compacto", files={"archivo": ("boleta.pdf", b"%PDF-1.4", "application/pdf")},
                     data={"tipo_declarado": "Predial"})
    assert r.status_code == 200, r.text
    assert r.json()["NombreArchivo"] == "boleta.pdf"
    assert cliente.llamadas["procesar"] == [("boleta.pdf", "Predial", "compacto")]


def test_expediente(cliente):
    files = [("archivos", ("a.pdf", b"%PDF", "application/pdf")), ("archivos", ("b.jpg", b"jpg", "image/jpeg"))]
    r = cliente.post("/expediente", files=files, data={"tipos": ["Escritura", "Predial"]})
    assert r.status_code == 200, r.text
    assert cliente.llamadas["verificar"] == (2, "completo")


def test_errores(cliente):
    r = cliente.post("/documento", files={"archivo": ("x.docx", b"hola", "application/octet-stream")})
    assert r.status_code == 415
    r = cliente.post("/expediente", files=[("archivos", ("a.pdf", b"%PDF", "application/pdf"))],
                     data={"tipos": ["Predial", "Escritura"]})
    assert r.status_code == 400
    r = cliente.post("/documento?modo=resumido", files={"archivo": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 422
