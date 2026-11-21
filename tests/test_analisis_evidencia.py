"""Trazabilidad: cada valor se localiza en el texto OCR con su página y cita literal."""
from analisis.contexto import limpiar_texto, preparar_contexto
from analisis.evidencia import TextoDocumento, localizar, normalizar_con_mapa

PAG1 = "NOTARÍA No. 18\nEn la ciudad de Zumpango, a 12 de marzo de 2019, ANTE MÍ se hace constar la COMPRAVENTA."
PAG2 = ("inmueble ubicado en Calle\nFresno No. 28, Lote 14, Col. La Loma, con superficie de 245.00 metros cuadrados, "
        "clave catastral 112 03 145 18 00 0000 y COMPRADOR(A) ROSA MARÍA QUINTANAR LEDESMA")
TEXTO = TextoDocumento("Escritura/a.pdf", "Escritura", [(1, PAG1), (2, PAG2)])


def test_mapa_de_normalizacion_conserva_posiciones():
    norm, mapa = normalizar_con_mapa("Jerónimo  Atlaco")
    assert norm == "JERONIMO ATLACO" and len(mapa) == len(norm)
    assert "Jerónimo  Atlaco"[mapa[9]] == "A"


def test_localiza_nombre_sin_acentos_y_con_salto_de_linea():
    ev = localizar(TEXTO, "propietario", "Rosa Maria Quintanar Ledesma")
    assert ev.verificada and ev.pagina == 2
    assert "QUINTANAR LEDESMA" in ev.cita and ev.documento == "Escritura/a.pdf"
    ev = localizar(TEXTO, "calle", "Calle Fresno")      # "Calle\nFresno" en el original
    assert ev.verificada and ev.pagina == 2


def test_localiza_numeros_y_fechas_en_otro_formato():
    assert localizar(TEXTO, "superficie_terreno_m2", 245.0).pagina == 2
    ev = localizar(TEXTO, "fecha", "2019-03-12")         # ISO -> "12 de marzo de 2019"
    assert ev.verificada and ev.pagina == 1
    ev = localizar(TEXTO, "clave_catastral", "1120314518000000")
    assert ev.verificada and ev.pagina == 2


def test_numero_oficial_usa_el_contexto_de_la_calle():
    ev = localizar(TEXTO, "numero", "28", extras={"calle": "Fresno"})
    assert ev.verificada and "Fresno No. 28" in ev.cita


def test_tolera_errores_de_ocr_pero_no_inventa():
    assert localizar(TEXTO, "propietario", "ROSA MARIA QUINTANAR LEDEZMA").verificada  # 1 letra distinta
    ev = localizar(TEXTO, "propietario", "JUAN CARLOS BENITEZ ARROYO")
    assert not ev.verificada and ev.pagina is None
    assert not localizar(TEXTO, "numero", "82", extras={"calle": "Fresno"}).verificada


def test_limpieza_quita_basura_del_ocr_pero_conserva_valores_cortos():
    sucio = "E) »\n—S\n28\nAL NORTE: en 10.00 metros con Calle Fresno. ------------\n=== m=-=------"
    limpio = limpiar_texto(sucio)
    assert "28" in limpio and "AL NORTE: en 10.00 metros con Calle Fresno." in limpio
    assert "»" not in limpio and "---" not in limpio


def test_contexto_respeta_presupuesto_y_prioriza_paginas_relevantes():
    relleno = "texto de relleno sin datos relevantes de ningun tipo para la prueba " * 40
    doc = {"Paginas": [{"Numero": 1, "Texto": "ESCRITURA PUBLICA NUMERO 1 " + relleno},
                       *[{"Numero": n, "Texto": relleno} for n in range(2, 9)],
                       {"Numero": 9, "Texto": "COMPRAVENTA inmueble UBICADO en lote con SUPERFICIE de 200 m2 COMPRADOR "
                                              + relleno}],
           "CamposExtraidos": {}}
    texto, paginas = preparar_contexto(doc, "Escritura", 6000)
    assert paginas[0] == 1 and 9 in paginas            # primera página + la más relevante
    assert len(texto) <= 6000 + 200
    texto, paginas = preparar_contexto(doc, "Escritura", 10 ** 6)
    assert paginas == list(range(1, 10))
