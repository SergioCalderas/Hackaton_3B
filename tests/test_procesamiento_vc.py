"""Integración con el pipeline del equipo (procesamiento/): validación cruzada -> observaciones -> semáforo.

Sin OCR ni BD: los documentos se arman con textos sintéticos y se colocan donde la Fase 2 los deja
guardados (filtro_resultados.detalle -> 'extraccion' -> 'documento').
"""
from conftest import ALINEAMIENTO, ESCRITURA, PREDIAL, PREDIAL_ALTERADO, USO_SUELO, hacer_documento

from ocr_pipeline.matching import aplicar_modo, enriquecer_documento
from procesamiento import dictamen, observaciones

TABLAS = {"escrituras": (ESCRITURA, "Escritura"), "predial": (PREDIAL, "Predial"),
          "suelo": (USO_SUELO, "UsoDeSuelo"), "aliniamiento": (ALINEAMIENTO, "Alineamiento")}


def op_con(textos: dict, estado: str = "APROBADO", con_extraccion: bool = True) -> dict:
    docs = {}
    for i, (tabla, (texto, tipo)) in enumerate(textos.items(), 1):
        d = aplicar_modo(enriquecer_documento(hacer_documento(texto, tipo, f"{tabla}/{tabla}.pdf")),
                         "compacto", es_expediente=False)
        filtro = {"estado": estado, "motivo": None, "mensaje": "", "observaciones": [],
                  "extraccion": {"estado": "OK", "documento": d} if con_extraccion else None}
        docs[tabla] = {"id": i, "archivo": f"{tabla}.pdf", "tiene_archivo": True, "filtro": filtro}
    return {"operacion_id": None, "documentos": docs}


def test_expediente_coherente_sale_verde():
    op = op_con(TABLAS)
    obs = observaciones.de_operacion(op)
    assert [o for o in obs if o["etapa"] == "validacion_cruzada"] == []
    color, razon = dictamen.semaforo(op, obs)
    assert color == "VERDE" and "validación cruzada" in razon
    entrada = dictamen.entrada_llm(op, obs)
    assert entrada["etapas_completadas"] == dictamen.ETAPAS_COMPLETADAS_VC
    assert entrada["validacion_cruzada"]["puntaje"] == 1.0


def test_discrepancias_criticas_salen_rojo():
    textos = {**TABLAS, "predial": (PREDIAL_ALTERADO, "Predial")}
    op = op_con(textos)
    obs = observaciones.de_operacion(op)
    vc = {o["regla"]: o for o in obs if o["etapa"] == "validacion_cruzada"}
    assert {"VC-05", "VC-02", "VC-04"} <= set(vc)
    assert vc["VC-05"]["severidad"] == vc["VC-02"]["severidad"] == "CRITICA"
    assert vc["VC-04"]["severidad"] == "ALTA"
    assert any(e["documento"] == "predial/predial.pdf" for e in vc["VC-02"]["evidencia"])
    assert dictamen.semaforo(op, obs)[0] == "ROJO"
    acciones = dictamen.dictaminar(op, obs)["redaccion"]["acciones_sugeridas"]  # plantilla (sin LLM)
    assert any("VC-02" in a for a in acciones)


def test_aprobado_sin_extraccion_pide_reverificar():
    op = op_con(TABLAS, con_extraccion=False)
    obs = observaciones.de_operacion(op)
    assert sum(o["codigo"] == "SIN-EXTRAER" for o in obs) == 4
    assert dictamen.semaforo(op, obs)[0] == "AMARILLO"
    assert dictamen.entrada_llm(op, obs)["etapas_completadas"] == dictamen.ETAPAS_COMPLETADAS


def test_documentos_no_aprobados_no_entran_a_la_validacion():
    op = op_con(TABLAS, estado="VOLVER_A_SUBIR")
    vc = [o for o in observaciones.de_operacion(op) if o["etapa"] == "validacion_cruzada"]
    assert vc == []  # la Fase 1 ya genera su observación (CAL-RECHAZO, bloquea)
