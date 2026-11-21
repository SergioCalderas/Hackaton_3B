from conftest import PREDIAL, PREDIAL_ALTERADO, PREDIAL_OTRO, USO_SUELO, hacer_documento

from ocr_pipeline.matching import (MatchConfig, agrupar, canonical_tipo, comparar, enriquecer_documento,
                                   sim_clave, sim_nombre, verificar)


def doc(texto, tipo, ruta):
    return enriquecer_documento(hacer_documento(texto, tipo, ruta))


def test_canonical_tipo():
    assert canonical_tipo("uso de suelo") == canonical_tipo("Uso_de_suelo") == "UsoDeSuelo"
    assert canonical_tipo("Alineamiento_y_Numero_Oficial") == "Alineamiento"
    assert canonical_tipo("recibo de luz") is None


def test_similitudes():
    assert sim_clave("1120314518000000", "1120314518000000") == 1.0
    assert sim_clave("1120314518000000", "1120314519000000") == 0.85  # un dígito
    assert sim_clave("006014070700000", "0060140707000000") >= 0.9   # ceros de relleno
    assert sim_nombre("GARCIA CERVANTES", "GARCIA CERVANTES ALEJANDRO FELIX") >= 0.9
    assert sim_nombre("ROSA MARIA QUINTANAR LEDESMA", "QUINTANAR LEDESMA ROSA MARIA") == 1.0
    assert sim_nombre("JUAN CARLOS BENITEZ ARROYO", "BENITEZ ARROYO JORGE ARMANDO") < 0.8


def test_expediente_coherente(docs_expediente):
    exp = verificar(docs_expediente)
    assert exp["ExpedienteId"] == "EXP-1120314518000000"
    assert exp["DocumentosFaltantes"] == []
    assert exp["NivelMatch"] == "alto"
    assert {"ClaveCatastral", "Propietario", "SuperficieTerreno"} <= set(exp["CamposCoinciden"])
    assert exp["CamposNoCoinciden"] == []


def test_expediente_con_discrepancias(docs_expediente):
    docs = [d for d in docs_expediente if d["TipoDocumento"] != "Predial"]
    docs.append(doc(PREDIAL_ALTERADO, "Predial", "Predial/alterado.pdf"))
    exp = verificar(docs)
    no = {x["Campo"]: x for x in exp["CamposNoCoinciden"]}
    assert {"ClaveCatastral", "Propietario", "NumeroOficial"} <= set(no)
    assert "levemente" in no["ClaveCatastral"]["Detalle"]
    assert any(v["Documento"] == "Predial/alterado.pdf" for v in no["Propietario"]["Valores"])


def test_faltantes_y_prediales_mismo_ejercicio():
    docs = [doc(PREDIAL, "Predial", "Predial/a.pdf"), doc(PREDIAL, "Predial", "Predial/b.pdf")]
    exp = verificar(docs)
    assert set(exp["DocumentosFaltantes"]) == {"Alineamiento", "Escritura", "UsoDeSuelo"}
    assert any(x["Campo"] == "EjercicioFiscal" for x in exp["CamposNoCoinciden"])


def test_tipo_declarado_distinto_al_detectado():
    d = doc(PREDIAL, "Escritura", "Escritura/en_realidad_predial.pdf")
    assert d["TipoDetectado"] == "Predial"
    assert any("no coincide con TipoDetectado" in x for x in d["Discrepancias"])


def test_agrupar_separa_inmuebles_y_no_fuerza_ilegibles(docs_expediente):
    otro = doc(PREDIAL_OTRO, "Predial", "Predial/otro.pdf")
    ilegible = doc("— e E a Ñ |", "UsoDeSuelo", "Uso_de_suelo/ilegible.pdf")
    res = agrupar(docs_expediente + [otro, ilegible], MatchConfig())
    assert len(res["expedientes"]) == 1
    assert len(res["expedientes"][0]["Documentos"]) == 4
    sin = {s["Documento"]: s for s in res["sin_match"]}
    assert set(sin) == {"Predial/otro.pdf", "Uso_de_suelo/ilegible.pdf"}
    assert "sin campos útiles" in sin["Uso_de_suelo/ilegible.pdf"]["Motivo"]


def test_comparar_sin_ancla_no_da_puntaje():
    a = doc("ROSA MARIA texto suelto", "Predial", "a.pdf")
    b = doc(USO_SUELO, "UsoDeSuelo", "b.pdf")
    assert comparar(a, b, MatchConfig())["score"] is None
