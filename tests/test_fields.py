from conftest import ALINEAMIENTO, ESCRITURA, PREDIAL, USO_SUELO

from ocr_pipeline.fields import DocText, campos_utiles, detectar_tipo, extraer_campos


def campos(texto, tipo):
    return extraer_campos([(1, texto)], tipo)


def test_predial():
    c = campos(PREDIAL, "Predial")
    assert c["ClaveCatastral"]["Normalizado"] == "1120314518000000"
    assert c["Propietario"]["Normalizado"] == "QUINTANAR LEDESMA ROSA MARIA"
    assert c["Calle"]["Normalizado"] == "FRESNO"
    assert c["NumeroOficial"]["Normalizado"] == "28"
    assert c["SuperficieTerreno"]["Normalizado"] == 245.0
    assert c["EjercicioFiscal"]["Normalizado"] == ["2025"]
    assert c["FechaDocumento"]["Normalizado"] == "2025-01-26"


def test_alineamiento_clave_partida_en_dos_renglones():
    c = campos(ALINEAMIENTO, "Alineamiento")
    assert c["ClaveCatastral"]["Normalizado"] == "1120314518000000"
    assert c["Propietario"]["Normalizado"] == "ROSA MARIA QUINTANAR LEDESMA"
    assert c["Lote"]["Normalizado"] == "14" and c["Manzana"]["Normalizado"] == "6"
    assert c["Municipio"]["Normalizado"] == "SAN JERONIMO ATLACO"
    assert c["Estado"]["Normalizado"] == "MEXICO"


def test_escritura_prefiere_comprador_y_saca_vendedor():
    c = campos(ESCRITURA, "Escritura")
    assert c["Propietario"]["Normalizado"] == "ROSA MARIA QUINTANAR LEDESMA"
    assert c["Vendedor"]["Normalizado"] == "FRANCISCO JAVIER MORALES PINA"
    assert c["NumeroEscritura"]["Normalizado"] == "21487"
    assert c["Volumen"]["Normalizado"] == "612"


def test_evidencia_y_pagina():
    c = extraer_campos([(1, "texto sin datos"), (2, PREDIAL)], "Predial")
    clave = c["ClaveCatastral"]
    assert clave["Pagina"] == 2
    assert "112 03 145 18 00 0000" in clave["Evidencia"]
    assert clave["Regla"]


def test_detectar_tipo():
    for texto, tipo in ((PREDIAL, "Predial"), (ALINEAMIENTO, "Alineamiento"),
                        (ESCRITURA, "Escritura"), (USO_SUELO, "UsoDeSuelo")):
        assert detectar_tipo(DocText.from_pages([(1, texto)]))[0] == tipo
    assert detectar_tipo(DocText.from_pages([(1, "— e E . a Ñ |")]))[0] is None


def test_texto_ilegible_no_tiene_campos_utiles():
    assert not campos_utiles(campos("“ AVENA NO COMETE — e E a Ñ", "UsoDeSuelo"))
