"""Validación cruzada (agente validador) y decisión del estado, sin OCR ni LLM."""
from datetime import date

import pytest

from analisis.config import Ajustes
from analisis.dictamen import combinar_estados, redaccion_determinista
from analisis.esquemas import CampoExtraido, DocumentoAnalizado, Evidencia
from analisis.reglas import (calcular_confianza, calcular_vencimiento, compatibilidad_por_reglas, decidir_estado,
                             hay_afectacion, validar)

AJ = Ajustes(fecha_referencia=date(2025, 11, 1))
CLAVE = "112 03 145 18 00 0000"


def hacer(tipo: str, nombre: str | None = None, estado_ocr: str = "ok", calidad: float = 0.92, **campos):
    nombre = nombre or f"{tipo}/doc.pdf"
    cs = {k: CampoExtraido(campo=k, etiqueta=k, valor=v,
                           evidencia=Evidencia(documento=nombre, tipo_documento=tipo, pagina=1, cita=f"… {v} …",
                                               valor=str(v), verificada=True))
          for k, v in campos.items()}
    return DocumentoAnalizado(nombre_archivo=nombre.split("/")[-1], ruta_archivo=nombre, tipo=tipo, num_paginas=1,
                              calidad_texto=calidad, estado_ocr=estado_ocr, campos=cs)


def expediente(**cambios):
    """Expediente coherente que cumple; `cambios` reemplaza documentos completos por tipo."""
    docs = {
        "Escritura": hacer("Escritura", propietario="ROSA MARÍA QUINTANAR LEDESMA", calle="Calle Fresno", numero="28",
                           colonia="La Loma", municipio="San Jerónimo Atlaco", clave_catastral=CLAVE,
                           superficie_terreno_m2=245.0, numero_escritura="21,487", lote="14"),
        "Predial": hacer("Predial", propietario="QUINTANAR LEDESMA ROSA MARIA", calle="FRESNO", numero="28",
                         clave_catastral="1120314518000000", superficie_terreno_m2=245.0, ejercicio_fiscal=2025),
        "Alineamiento": hacer("Alineamiento", calle="Calle Fresno", numero="No. 28", clave_catastral=CLAVE,
                              superficie_terreno_m2=245.0, fecha_expedicion="2025-02-17",
                              vigencia="un año a partir de su expedición",
                              alineamiento="10.00 m de frente; restricción 0.00 m"),
        "UsoDeSuelo": hacer("UsoDeSuelo", calle="Fresno", numero="28", clave_catastral=CLAVE, superficie_terreno_m2=245.0,
                            uso_autorizado="COMERCIAL", giro="COMERCIO DE PRODUCTOS BÁSICOS (MINISÚPER)",
                            compatible_comercial="si", fecha_expedicion="2025-03-03", vigencia="03 DE MARZO DE 2026"),
    }
    docs.update(cambios)
    return [d for d in docs.values() if d is not None]


def resultados(hallazgos, categoria=None):
    return {h.resultado for h in hallazgos if categoria is None or h.categoria == categoria}


def test_expediente_coherente_cumple():
    hs = validar(expediente(), {}, AJ)
    assert decidir_estado(hs) == "Cumple"
    assert not [h for h in hs if h.resultado in ("revisar", "no_cumple")]
    ids = {h.id for h in hs if h.resultado == "cumple"}
    assert {"identificacion:clave_catastral", "consistencia:propietario", "consistencia:superficie_terreno_m2",
            "predial:corriente"} <= ids
    conf, nivel, f = calcular_confianza(expediente(), hs)
    assert 0.8 <= conf <= 1 and nivel == "alta" and f["completitud"] == 1.0


def test_falta_documento_no_cumple():
    hs = validar(expediente(UsoDeSuelo=None), {}, AJ)
    assert decidir_estado(hs) == "No cumple"
    h = next(h for h in hs if h.id == "completitud:UsoDeSuelo")
    assert h.resultado == "no_cumple" and h.severidad == "critica"


def test_uso_habitacional_no_cumple_con_evidencia():
    uso = hacer("UsoDeSuelo", calle="Fresno", clave_catastral=CLAVE, uso_autorizado="HABITACIONAL",
                giro="VIVIENDA UNIFAMILIAR", compatible_comercial="no", fecha_expedicion="2025-03-03")
    hs = validar(expediente(UsoDeSuelo=uso), {}, AJ)
    assert decidir_estado(hs) == "No cumple"
    h = next(h for h in hs if h.categoria == "uso_suelo" and h.resultado == "no_cumple")
    assert h.evidencias and h.evidencias[0].pagina == 1


def test_agentes_discrepan_sobre_uso_de_suelo_requiere_revision():
    uso = hacer("UsoDeSuelo", nombre="Uso/u.pdf", calle="Fresno", clave_catastral=CLAVE, compatible_comercial="si",
                fecha_expedicion="2025-03-03", vigencia="03 DE MARZO DE 2026")
    ocr = {"Uso/u.pdf": {"Paginas": [{"Numero": 1, "Texto": "USO DE SUELO QUE SE AUTORIZA: HABITACION A L\n"
                                                            "RESTRICCIÓN: EN ESTA ZONA NO SE PERMITEN USOS COMERCIALES"}]}}
    hs = validar(expediente(UsoDeSuelo=uso), ocr, AJ)
    h = next(h for h in hs if h.categoria == "uso_suelo" and h.resultado != "informativo")
    assert h.resultado == "revisar" and "discrepan" in h.descripcion


def test_inconsistencias_requieren_revision_y_muestran_cada_valor():
    predial = hacer("Predial", propietario="BENITEZ ARROYO JORGE ARMANDO", calle="FRESNO", numero="51",
                    clave_catastral="112 03 145 19 00 0000", superficie_terreno_m2=290.0, ejercicio_fiscal=2025)
    esc = hacer("Escritura", propietario="JUAN CARLOS BENÍTEZ ARROYO", calle="Calle Fresno", numero="28",
                clave_catastral=CLAVE, superficie_terreno_m2=312.5, numero_escritura="47015", lote="9")
    hs = validar(expediente(Predial=predial, Escritura=esc), {}, AJ)
    assert decidir_estado(hs) == "Requiere revisión"
    por_id = {h.id: h for h in hs}
    assert por_id["identificacion:clave_catastral"].resultado == "revisar"
    assert "un dígito" in por_id["identificacion:clave_catastral"].descripcion
    assert "7.2%" in por_id["consistencia:superficie_terreno_m2"].descripcion
    assert por_id["consistencia:numero"].resultado == "revisar"
    assert por_id["consistencia:propietario"].resultado == "revisar"
    assert len(por_id["consistencia:propietario"].evidencias) == 2


def test_documento_de_otro_inmueble_no_cumple():
    otro = hacer("Predial", nombre="Predial/otro.pdf", propietario="PEÑALOZA RUIZ SILVIA ADRIANA",
                 calle="AVENIDA DE LAS TORRES", municipio="Ocotlán de las Torres", clave_catastral="077 04 310 12 00 0000",
                 superficie_terreno_m2=300.0, ejercicio_fiscal=2025)
    docs = expediente(Predial=otro)
    for d in docs:
        if d.tipo != "Predial":
            d.campos["municipio"] = CampoExtraido(campo="municipio", etiqueta="municipio", valor="San Jerónimo Atlaco")
    hs = validar(docs, {}, AJ)
    assert decidir_estado(hs) == "No cumple"
    h = next(h for h in hs if h.id.startswith("identificacion:otro_inmueble"))
    assert "otro.pdf" in h.descripcion and h.severidad == "critica"


def test_vigencias_vencidas_y_predial_atrasado():
    aj = Ajustes(fecha_referencia=date(2026, 11, 21))
    hs = validar(expediente(), {}, aj)
    vig = [h for h in hs if h.categoria == "vigencia"]
    assert {h.resultado for h in vig} == {"revisar"}
    assert any("03/03/2026" in h.descripcion for h in vig) and any("17/02/2026" in h.descripcion for h in vig)
    pred = next(h for h in hs if h.id == "predial:corriente")
    assert pred.resultado == "revisar" and "2025" in pred.descripcion
    assert decidir_estado(hs) == "Requiere revisión"
    assert next(h for h in validar(expediente(), {}, aj.con(predial_tolerancia_anios=1))
                if h.id == "predial:corriente").resultado == "cumple"


def test_afectacion_en_alineamiento():
    ali = hacer("Alineamiento", calle="Calle Fresno", numero="28", clave_catastral=CLAVE, fecha_expedicion="2025-06-09",
                vigencia="un año", afectaciones="Afectación de 4.00 m al frente por ampliación de la avenida; 60 m2")
    hs = validar(expediente(Alineamiento=ali), {}, AJ)
    h = next(h for h in hs if h.categoria == "alineamiento")
    assert h.resultado == "revisar" and "4.00 m" in h.descripcion
    assert not hay_afectacion("Restricción de construcción al frente: 0.00 m")
    assert not hay_afectacion("Sin afectaciones")
    assert hay_afectacion("Restricción de 3 m al frente")


def test_documento_ilegible_requiere_revision():
    ilegible = hacer("Predial", nombre="Predial/ilegible.pdf", estado_ocr="low_text", calidad=0.2)
    hs = validar(expediente(Predial=ilegible), {}, AJ)
    h = next(h for h in hs if h.categoria == "legibilidad")
    assert h.resultado == "revisar" and "ilegible" in h.descripcion
    assert decidir_estado(hs) == "Requiere revisión"


@pytest.mark.parametrize("exp,vig,venc,esperado", [
    ("2025-02-17", "un año a partir de su expedición", None, date(2026, 2, 17)),
    ("2025-03-03", "03 DE MARZO DE 2026", None, date(2026, 3, 3)),
    ("2025-01-31", "6 meses", None, date(2025, 7, 31)),
    ("2025-01-31", "1 (un) mes", None, date(2025, 2, 28)),
    ("2025-01-01", None, "2025-12-31", date(2025, 12, 31)),
    ("2025-01-01", "Indefinida", None, None),
    (None, None, None, None),
])
def test_calculo_de_vencimiento(exp, vig, venc, esperado):
    assert calcular_vencimiento(exp, vig, venc)[0] == esperado


def test_compatibilidad_por_reglas():
    assert compatibilidad_por_reglas("C O M E R C I A L", "MINISÚPER", []) == "si"
    assert compatibilidad_por_reglas("HABITACION A L", "VIVIENDA UNIFAMILIAR", []) == "no"
    assert compatibilidad_por_reglas("MIXTO", None, ["NO SE PERMITEN USOS COMERCIALES"]) == "no"
    assert compatibilidad_por_reglas(None, None, []) is None


def test_el_llm_solo_puede_escalar_el_estado():
    assert combinar_estados("Cumple", "No cumple") == "Requiere revisión"
    assert combinar_estados("Cumple", "Cumple") == "Cumple"
    assert combinar_estados("No cumple", "Cumple") == "No cumple"
    assert combinar_estados("Requiere revisión", "Cumple") == "Requiere revisión"


def test_redaccion_determinista_menciona_motivos():
    hs = validar(expediente(UsoDeSuelo=None), {}, AJ)
    resumen, acciones = redaccion_determinista("No cumple", hs)
    assert "Falta Licencia de Uso de Suelo" in resumen and acciones


def test_no_rechaza_lo_que_puede_continuar():
    """Refinamientos para no generar falsos 'No cumple' (criterio de evaluación del reto)."""
    from analisis.comparar import similitud

    # municipio con el estado pegado y nombre largo vs corto
    assert similitud("texto", "Tepeji del Río de Ocampo", "TEPEJI DEL RIO, HIDALGO") == 1.0
    # predio en esquina: coincide con cualquiera de las dos calles
    assert similitud("calle", "AV. INSURGENTES ESQUINA CON CALLE GLADIOLAS", "CALLE GLADIOLAS") >= 0.85
    # S/N contra un número: falta de dato (informativo), no contradicción
    pred = hacer("Predial", propietario="QUINTANAR LEDESMA ROSA MARIA", calle="FRESNO", numero="S/N",
                 clave_catastral=CLAVE, superficie_terreno_m2=245.0, ejercicio_fiscal=2025)
    hs = validar(expediente(Predial=pred), {}, AJ)
    assert decidir_estado(hs) == "Cumple"
    assert any(h.id == "consistencia:numero:sin_numero" and h.resultado == "informativo" for h in hs)


def test_otro_predio_con_el_mismo_titular_se_revisa_no_se_rechaza():
    uso = hacer("UsoDeSuelo", nombre="Uso/esquina.pdf", propietario="ROSA MARIA QUINTANAR LEDESMA",
                calle="CALLE OLIVOS", municipio="Otro Municipio", clave_catastral="077 04 310 12 00 0000",
                uso_autorizado="COMERCIAL", compatible_comercial="si", fecha_expedicion="2025-03-03",
                vigencia="03 DE MARZO DE 2026")
    docs = expediente(UsoDeSuelo=uso)
    for d in docs:
        if d.tipo != "UsoDeSuelo":
            d.campos["municipio"] = CampoExtraido(campo="municipio", etiqueta="municipio", valor="San Jerónimo Atlaco")
    hs = validar(docs, {}, AJ)
    h = next(h for h in hs if h.id.startswith("identificacion:otro_inmueble"))
    assert h.resultado == "revisar" and "mismo" in h.descripcion
    assert decidir_estado(hs) == "Requiere revisión"


def test_sin_clave_que_lo_confirme_no_se_rechaza():
    """Escritura antigua: otra calle y otro municipio, sin clave catastral -> revisión, no rechazo."""
    esc = hacer("Escritura", nombre="Escritura/antigua.pdf", propietario="FRANCISCO SANDOVAL ESCALONA",
                calle="Melchor Ocampo", municipio="Cuautitlán", superficie_terreno_m2=245.0, numero_escritura="123",
                lote="14")
    docs = expediente(Escritura=esc)
    for d in docs:
        if d.tipo != "Escritura":
            d.campos["municipio"] = CampoExtraido(campo="municipio", etiqueta="municipio", valor="Melchor Ocampo")
    hs = validar(docs, {}, AJ)
    h = next(h for h in hs if h.id.startswith("identificacion:otro_inmueble"))
    assert h.resultado == "revisar" and "clave catastral comparable" in h.descripcion
    assert decidir_estado(hs) == "Requiere revisión"
