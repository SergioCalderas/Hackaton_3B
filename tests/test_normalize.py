import pytest

from ocr_pipeline.normalize import (compact, digits_only, norm, norm_address, norm_cuenta, norm_estado,
                                    norm_name, parse_date, parse_number)


def test_norm_quita_acentos_y_signos():
    assert norm("San Jerónimo Atlaco, Edo. Méx.") == "SAN JERONIMO ATLACO EDO MEX"
    assert compact("La  Loma") == "LALOMA"


@pytest.mark.parametrize("entrada, esperado", [
    ("Av. Insurgentes No. 104, Col. Centro", "AVENIDA INSURGENTES NUMERO 104 COLONIA CENTRO"),
    ("C. Fresno #28 Mza. 6 Lt. 14", "CALLE FRESNO NUMERO 28 MANZANA 6 LOTE 14"),
    ("Matamoros S/N Bo. San Juan", "MATAMOROS SN BARRIO SAN JUAN"),
])
def test_norm_address_abreviaturas(entrada, esperado):
    assert norm_address(entrada) == esperado


def test_norm_name():
    assert norm_name("C. Ma. Isabel Gicela") == "MARIA ISABEL GICELA"
    assert norm_name("Lic. José Pérez") == "JOSE PEREZ"


@pytest.mark.parametrize("entrada, esperado", [
    ("1,039.71", 1039.71), ("536,82", 536.82), ("245.00", 245.0), ("783:20", 783.2), ("1.234.567,89", 1234567.89),
    ("", None), ("m2", None),
])
def test_parse_number(entrada, esperado):
    assert parse_number(entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("17 de febrero de 2025", "2025-02-17"), ("03 DE MARZO DE 2025", "2025-03-03"),
    ("26/01/2025", "2025-01-26"), ("2024-03-25T11:08:01", "2024-03-25"), ("31 de febrero de 2025", None),
])
def test_parse_date(entrada, esperado):
    assert parse_date(entrada) == esperado


def test_claves_y_cuentas():
    assert digits_only("112 03 145 18 00 0000") == "1120314518000000"
    assert digits_only("O77 04 31O l2") == "0770431012"  # confusiones de OCR O->0, l->1
    assert norm_cuenta("U-03410") == norm_cuenta("U0003410") == "U3410"


def test_norm_estado():
    assert norm_estado("Hgo.") == "HIDALGO"
    assert norm_estado("Estado de México") == "MEXICO"
