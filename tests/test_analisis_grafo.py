"""Grafo multiagente de punta a punta con LLM y OCR simulados (rápido, sin Ollama ni Tesseract)."""
from datetime import date

import pytest
from conftest import ALINEAMIENTO, ESCRITURA, PREDIAL, USO_SUELO, hacer_documento

import analisis.agentes as agentes_mod
import analisis.dictamen as dictamen_mod
import analisis.grafo as grafo_mod
from analisis.config import Ajustes
from analisis.esquemas import (Clasificacion, ExtraccionAlineamiento, ExtraccionEscritura, ExtraccionPredial,
                               ExtraccionUsoSuelo, RedaccionDictamen, ResultadoExpediente)
from ocr_pipeline.matching import enriquecer_documento

CLAVE = "112 03 145 18 00 0000"
TEXTOS = {"Escritura/a.pdf": ESCRITURA, "Predial/a.pdf": PREDIAL, "Alineamiento/a.pdf": ALINEAMIENTO,
          "Uso/a.pdf": USO_SUELO, "Otros/luz.pdf": "COMISIÓN FEDERAL DE ELECTRICIDAD aviso recibo de luz periodo "
                                                    "consumo kWh total a pagar " * 3}
RESPUESTAS = {
    ExtraccionEscritura: ExtraccionEscritura(
        propietario="ROSA MARÍA QUINTANAR LEDESMA", vendedor="FRANCISCO JAVIER MORALES PIÑA", calle="Calle Fresno",
        numero="28", colonia="La Loma", municipio="San Jerónimo Atlaco", lote="14", manzana="6", clave_catastral=CLAVE,
        superficie_terreno_m2=245.0, acto="COMPRAVENTA", numero_escritura="21,487", fecha="2019-03-12"),
    ExtraccionPredial: ExtraccionPredial(
        propietario="QUINTANAR LEDESMA ROSA MARIA", calle="FRESNO", numero="28", colonia="LA LOMA", clave_catastral=CLAVE,
        superficie_terreno_m2=245.0, ejercicio_fiscal=2025, fecha_pago="2025-01-26", superficie_construccion_m2=96.4),
    ExtraccionAlineamiento: ExtraccionAlineamiento(
        propietario="ROSA MARÍA QUINTANAR LEDESMA", calle="Calle Fresno No. 28", numero="28", colonia="La Loma",
        lote="14", manzana="6", clave_catastral=CLAVE, superficie_terreno_m2=245.0, fecha_expedicion="2025-02-17"),
    ExtraccionUsoSuelo: ExtraccionUsoSuelo(
        propietario="ROSA MARÍA QUINTANAR LEDESMA", calle="Calle Fresno", numero="28", clave_catastral=CLAVE,
        superficie_terreno_m2=245.0, uso_autorizado="HABITACIONAL", compatible_comercial="no",
        cita_compatibilidad="USO DE SUELO QUE SE AUTORIZA: HABITACIONAL", fecha_expedicion="2025-03-03"),
    RedaccionDictamen: RedaccionDictamen(resumen="No cumple: la licencia solo autoriza uso habitacional.",
                                         observaciones=["Buscar un inmueble con uso comercial."],
                                         estado_sugerido="No cumple"),
    Clasificacion: Clasificacion(tipo="Otro"),
}


class LLMFalso:
    llamadas: list[str] = []

    def __init__(self, esquema, falla=False):
        self.esquema, self.falla = esquema, falla

    def invoke(self, mensajes):
        if self.falla:
            raise ConnectionError("Ollama no responde")
        LLMFalso.llamadas.append(self.esquema.__name__)
        assert "PÁGINA 1" in mensajes[-1].content or self.esquema in (RedaccionDictamen, Clasificacion)
        return RESPUESTAS[self.esquema]


def ocr_falso(ruta, nombre, tipo, aj):
    doc = enriquecer_documento(hacer_documento(TEXTOS[nombre], tipo, nombre), tipo)
    return doc, {"ocr_s": 0.01, "cache": False}


@pytest.fixture
def simulado(monkeypatch):
    def usar(falla=False):
        LLMFalso.llamadas = []
        fab = lambda aj, esquema, rol="general": LLMFalso(esquema, falla)  # noqa: E731
        monkeypatch.setattr(agentes_mod, "llm_estructurado", fab)
        monkeypatch.setattr(dictamen_mod, "llm_estructurado", fab)
        monkeypatch.setattr(grafo_mod, "ocr_documento", ocr_falso)
        monkeypatch.setattr(grafo_mod, "estado_ollama", lambda aj: {"modelo_cargado": True})
        monkeypatch.setattr(grafo_mod.calidad_mod, "evaluar", lambda ruta, nombre, tipo: CALIDAD.get(nombre))
    return usar


CALIDAD: dict[str, dict] = {}    # resultado simulado de la Fase 1 por archivo (vacío = filtro no disponible)


ARCHIVOS = [{"ruta": n, "nombre": n, "tipo": t} for n, t in
            (("Escritura/a.pdf", "Escritura"), ("Predial/a.pdf", "Predial"), ("Alineamiento/a.pdf", "Alineamiento"),
             ("Uso/a.pdf", "UsoDeSuelo"))]
AJ = Ajustes(fecha_referencia=date(2025, 11, 1), dictamen_llm="si")


def test_flujo_completo_con_evidencia(simulado):
    simulado()
    eventos = []
    res = grafo_mod.analizar_expediente(ARCHIVOS, AJ, eventos.append)
    ResultadoExpediente.model_validate(res)
    assert res["estado"] == "No cumple" and res["estado_reglas"] == "No cumple" and res["dictamen_por"] == "llm"
    assert res["expediente_id"] == "EXP-1120314518000000"
    assert res["documentos_faltantes"] == [] and len(res["documentos"]) == 4
    assert sorted(LLMFalso.llamadas) == sorted(["ExtraccionEscritura", "ExtraccionPredial", "ExtraccionAlineamiento",
                                                "ExtraccionUsoSuelo", "RedaccionDictamen"])
    etapas = [(e["etapa"], e.get("archivo")) for e in eventos]
    for a in ARCHIVOS:
        assert ("ocr", a["nombre"]) in etapas and ("extraccion", a["nombre"]) in etapas
    assert ("validacion", None) in etapas and ("dictamen", None) in etapas

    hz = {h["id"]: h for h in res["hallazgos"]}
    uso = next(h for h in res["hallazgos"] if h["categoria"] == "uso_suelo" and h["resultado"] == "no_cumple")
    assert uso["evidencias"][0]["documento"] == "Uso/a.pdf" and uso["evidencias"][0]["pagina"] == 1
    assert hz["consistencia:propietario"]["resultado"] == "cumple"
    assert all(e["verificada"] for e in hz["consistencia:propietario"]["evidencias"])
    esc = next(d for d in res["documentos"] if d["tipo"] == "Escritura")
    assert esc["campos"]["propietario"]["fuente"] == "llm+reglas"            # doble verificación
    assert esc["campos"]["superficie_terreno_m2"]["evidencia"]["verificada"]
    assert esc["campos"]["calle"]["valor"] == "Calle Fresno"


def test_degradado_si_el_llm_no_responde(simulado):
    simulado(falla=True)
    res = grafo_mod.analizar_expediente(ARCHIVOS, AJ)
    assert res["dictamen_por"] == "reglas" and res["estado"] == "No cumple"   # el texto dice "HABITACIONAL"
    assert all(d["error_llm"] for d in res["documentos"])
    pred = next(d for d in res["documentos"] if d["tipo"] == "Predial")
    assert pred["campos"]["clave_catastral"]["fuente"] == "reglas"
    assert any(h["categoria"] == "extraccion" for h in res["hallazgos"])


def test_documento_desconocido_y_faltantes(simulado):
    simulado()
    res = grafo_mod.analizar_expediente([ARCHIVOS[1], {"ruta": "Otros/luz.pdf", "nombre": "Otros/luz.pdf", "tipo": None}],
                                        AJ)
    assert "Clasificacion" in LLMFalso.llamadas
    assert res["estado"] == "No cumple"
    assert set(res["documentos_faltantes"]) == {"Escritura", "Alineamiento y Número Oficial", "Licencia de Uso de Suelo"}
    assert any(h["id"].startswith("completitud:sin_tipo") for h in res["hallazgos"])


def test_arquitectura_tiene_agentes_especializados():
    mermaid = grafo_mod.diagrama_mermaid()
    for nodo in ("agente_ocr", "agente_clasificador", "extractor_escritura", "extractor_predial",
                 "extractor_alineamiento", "extractor_uso_suelo", "validador_cruzado", "dictaminador"):
        assert nodo in mermaid


def test_archivo_danado_no_tumba_el_expediente(simulado):
    simulado()
    danado = {"ruta": "Uso/danado.pdf", "nombre": "Uso/danado.pdf", "tipo": "UsoDeSuelo"}  # el OCR falso lanza KeyError
    res = grafo_mod.analizar_expediente(ARCHIVOS[:3] + [danado], AJ)
    uso = next(d for d in res["documentos"] if d["ruta_archivo"] == "Uso/danado.pdf")
    assert uso["estado_ocr"] == "error" and uso["tipo"] == "UsoDeSuelo"
    assert any(h["categoria"] == "legibilidad" and "danado.pdf" in h["descripcion"] for h in res["hallazgos"])
    assert res["estado"] == "Requiere revisión"


def test_filtro_de_calidad_rechaza_y_excluye_de_la_validacion(simulado, monkeypatch):
    simulado()
    monkeypatch.setitem(CALIDAD, "Predial/a.pdf", {"estado": "VOLVER_A_SUBIR", "motivo": "otro_documento",
                                                   "mensaje": "Es un recibo de luz, no una boleta predial."})
    monkeypatch.setitem(CALIDAD, "Escritura/a.pdf", {"estado": "APROBADO", "motivo": None, "mensaje": "Documento válido."})
    res = grafo_mod.analizar_expediente(ARCHIVOS, AJ)
    # el documento rechazado no participa en la validación cruzada (sus datos no se comparan)
    assert not any(h["categoria"] == "consistencia" and "Predial" in h["descripcion"] for h in res["hallazgos"])
    assert res["semaforo"] == "GRIS" and res["semaforo_texto"] == "No validado"
    assert "Predial" in res["documentos_faltantes"]
    falta = next(h for h in res["hallazgos"] if h["id"] == "completitud:Predial")
    assert "volver a subirlo" in falta["descripcion"]
    assert any(h["categoria"] == "calidad" and h["resultado"] == "cumple" for h in res["hallazgos"])
    pred = next(d for d in res["documentos"] if d["ruta_archivo"] == "Predial/a.pdf")
    assert pred["calidad"]["estado"] == "VOLVER_A_SUBIR" and pred["tipo"] == "Predial"


def test_semaforo_sin_filtro_sigue_el_estado(simulado):
    simulado()
    res = grafo_mod.analizar_expediente(ARCHIVOS, AJ)
    assert res["estado"] == "No cumple" and res["semaforo"] == "ROJO"
