"""Utilidades compartidas por las pruebas.

Los textos de prueba son SINTÉTICOS (nombres y claves inventados), en el formato de los
documentos de ejemplo del reto.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PREDIAL = """MUNICIPIO DE SAN JERÓNIMO ATLACO, ESTADO DE MÉXICO
TESORERÍA MUNICIPAL - CATASTRO E IMPUESTO PREDIAL
RECIBO OFICIAL DE PAGO
FOLIO: TM-2025-435320
FECHA DE PAGO: 26/01/2025 12:21
DATOS DEL PREDIO
CLAVE CATASTRAL 112 03 145 18 00 0000
PROPIETARIO / POSEEDOR QUINTANAR LEDESMA ROSA MARIA
UBICACIÓN FRESNO 28, COL. LA LOMA
SUPERFICIE TERRENO (M2) 245.00
SUPERFICIE CONSTRUCCIÓN (M2) 96.40
AÑO BIM, INI BIM. FIN IMPUESTO ADICIONAL RECARGOS MULTAS BONIFICACIÓN SUBTOTAL
2025 1 6 1,989.36 147.36 0.00 0.00 -294,72 1,842.00
TOTAL PAGADO: $ 1,842.00
LÍNEA DE CAPTURA: 939786689216168389"""

ALINEAMIENTO = """H. AYUNTAMIENTO CONSTITUCIONAL DE SAN JERÓNIMO ATLACO
Estado de México - Administración 2025-2027
CONSTANCIA DE ALINEAMIENTO
FOLIO: DDU/ALI/0418/2025
San Jerónimo Atlaco, Estado de México, a 17 de febrero de 2025.
C. ROSA MARÍA QUINTANAR LEDESMA: Esta Dirección, en contestación a su solicitud, ha señalado el
alineamiento que se indica en el siguiente croquis con ubicación en Calle Fresno No. 28, Lote 14, Manzana 6,
Col. La Loma, Municipio de San Jerónimo Atlaco, Estado de México. CLAVE CATASTRAL: 112 03 145 18 00
0000.
PREDIO SUP. 245.00 m?
NÚMERO OFICIAL 28"""

ESCRITURA = """LIC. ARMANDO VILLASEÑOR CRUZ
NOTARÍA NOTARIO PÚBLICO No. 18 - ZUMPANGO
VOLUMEN 612 ---------- INSTRUMENTO NÚMERO 21,487 --------
En la ciudad de Zumpango, a 12 de marzo de 2019, ANTE MÍ, se hace constar el CONTRATO DE COMPRAVENTA
que celebran, de una parte como VENDEDOR FRANCISCO JAVIER MORALES PIÑA, y de la otra como COMPRADOR(A)
ROSA MARÍA QUINTANAR LEDESMA, al tenor de los siguientes antecedentes y cláusulas:
ANTECEDENTES
I.- Declara la parte vendedora ser legítima propietaria del inmueble ubicado en Calle
Fresno No. 28, Lote 14, Manzana 6, Col. La Loma, Municipio de San Jerónimo Atlaco,
Estado de México, con superficie de 245.00 metros cuadrados, identificado con clave
catastral 112 03 145 18 00 0000, según consta en el folio real electrónico.
CLÁUSULAS
PRIMERA.- FRANCISCO JAVIER MORALES PIÑA vende. DOY FE."""

USO_SUELO = """LICENCIA DE USO DEL SUELO FOLIO: DDU/LUS/0233/2025
H. AYUNTAMIENTO CONSTITUCIONAL DE SAN JERÓNIMO ATLACO
NOMBRE ROSA MARÍA QUINTANAR LEDESMA
DOMICILIO Calle Fresno No. 28, Lote 14, Manzana 6, Col. La Loma
CLAVE CATASTRAL 112 03 145 18 00 0000
SUPERFICIE DEL PREDIO 245.00 m?
USO DE SUELO QUE SE AUTORIZA: HABITACIONAL
COEFICIENTE DE OCUPACIÓN 70% DENSIDAD MEDIA
FECHA DE EXPEDICIÓN: 03 DE MARZO DE 2025"""

# Variante con discrepancias plantadas (otro propietario, un dígito distinto en la clave, otro número).
PREDIAL_ALTERADO = (PREDIAL.replace("112 03 145 18 00 0000", "112 03 145 19 00 0000")
                    .replace("QUINTANAR LEDESMA ROSA MARIA", "QUINTANAR LEDESMA JORGE ARMANDO")
                    .replace("FRESNO 28", "FRESNO 82"))

# Otro inmueble distinto.
PREDIAL_OTRO = (PREDIAL.replace("112 03 145 18 00 0000", "077 04 310 12 00 0000")
                .replace("QUINTANAR LEDESMA ROSA MARIA", "PEÑALOZA RUIZ SILVIA ADRIANA")
                .replace("FRESNO 28, COL. LA LOMA", "AVENIDA DE LAS TORRES 5, COL. EL MIRADOR")
                .replace("SAN JERÓNIMO ATLACO", "OCOTLÁN DE LAS TORRES")
                .replace("245.00", "410.00"))


def hacer_documento(texto: str, tipo: str | None, ruta: str, estado: str = "ok") -> dict:
    """Documento base (formato Documento) con una sola página, como lo produce export.build_document."""
    return {
        "VersionEsquema": "1.1.0", "Modo": "completo",
        "NombreArchivo": Path(ruta).name, "RutaArchivo": ruta,
        "TipoDocumento": tipo, "TipoDeclarado": tipo, "TipoDetectado": None,
        "TextoExtraido": texto,
        "Paginas": [{"Numero": 1, "Texto": texto, "Metodo": "ocr", "Motor": "tesseract", "CalidadTexto": 0.9}],
        "Estado": estado, "CalidadTexto": 0.9, "NumPaginas": 1, "Hash": None, "DuplicadoDe": None,
        "CamposExtraidos": {}, "Discrepancias": [], "ExpedienteId": None,
    }


@pytest.fixture
def docs_expediente():
    from ocr_pipeline.matching import enriquecer_documento
    return [enriquecer_documento(hacer_documento(t, tipo, ruta)) for t, tipo, ruta in (
        (PREDIAL, "Predial", "Predial/a.pdf"),
        (ALINEAMIENTO, "Alineamiento", "Alineamiento_y_Numero_Oficial/a.pdf"),
        (ESCRITURA, "Escritura", "Escritura/a.pdf"),
        (USO_SUELO, "UsoDeSuelo", "Uso_de_suelo/a.pdf"),
    )]
