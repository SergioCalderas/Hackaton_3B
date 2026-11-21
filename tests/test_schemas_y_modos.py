import json

import pytest
from conftest import RAIZ

from ocr_pipeline.matching import aplicar_modo, verificar
from ocr_pipeline.schemas import VERSION_ESQUEMA, Documento, Expediente

EJEMPLOS = RAIZ / "examples"


def test_expediente_valida_en_ambos_modos(docs_expediente):
    exp = {"VersionEsquema": VERSION_ESQUEMA, **verificar(docs_expediente)}
    completo = aplicar_modo(exp, "completo", es_expediente=True)
    compacto = aplicar_modo(exp, "compacto", es_expediente=True)
    Expediente.model_validate(completo)
    Expediente.model_validate(compacto)

    assert compacto["Modo"] == "compacto"
    for d in compacto["Documentos"]:
        assert d["TextoExtraido"] is None
        assert all(p["Texto"] is None for p in d["Paginas"])
        assert d["CamposExtraidos"]  # campos y evidencia se conservan
        usadas = {c["Pagina"] for c in d["CamposExtraidos"].values()}
        assert {p["Numero"] for p in d["Paginas"]} <= usadas
    # La verificación no cambia con el modo
    assert compacto["CamposNoCoinciden"] == completo["CamposNoCoinciden"]
    assert compacto["PuntajeMatch"] == completo["PuntajeMatch"]


def test_modo_invalido(docs_expediente):
    with pytest.raises(ValueError):
        aplicar_modo(docs_expediente[0], "resumido", es_expediente=False)


@pytest.mark.parametrize("nombre, modelo", [
    ("documentos.json", Documento), ("expedientes.json", Expediente), ("expedientes_compacto.json", Expediente),
])
def test_ejemplos_cumplen_el_contrato(nombre, modelo):
    data = json.loads((EJEMPLOS / nombre).read_text(encoding="utf-8"))
    assert data, f"{nombre} vacío"
    for obj in data:
        modelo.model_validate(obj)


def test_schemas_exportados_al_dia(tmp_path):
    from ocr_pipeline.schemas import exportar_schemas
    for p in exportar_schemas(tmp_path):
        assert p.read_text(encoding="utf-8") == (RAIZ / "schemas" / p.name).read_text(encoding="utf-8"), \
            f"schemas/{p.name} desactualizado: corre python -m ocr_pipeline.schemas"
