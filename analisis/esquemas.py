"""Esquemas de datos.

1. Esquemas de EXTRACCIÓN (salida estructurada del LLM), uno por tipo de documento. Solo piden
   valores: la página y la cita de cada valor las calcula `evidencia.py` buscando el valor en el
   texto OCR. Así la salida del LLM es corta (rápida) y la evidencia es verificable.
2. Contrato de SALIDA del análisis (ResultadoExpediente), pensado para el front.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

VERSION_ANALISIS = "1.0.0"

TipoDoc = Literal["Escritura", "Predial", "Alineamiento", "UsoDeSuelo"]
TIPOS: tuple[str, ...] = ("Escritura", "Predial", "Alineamiento", "UsoDeSuelo")
NOMBRE_TIPO = {"Escritura": "Escritura", "Predial": "Predial",
               "Alineamiento": "Alineamiento y Número Oficial", "UsoDeSuelo": "Licencia de Uso de Suelo"}
EstadoExpediente = Literal["Cumple", "Requiere revisión", "No cumple"]


class _Extraccion(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------------------
# 1. Extracción (LLM)
# ---------------------------------------------------------------------------------------
class DatosInmueble(_Extraccion):
    propietario: Optional[str] = Field(None, description="Nombre completo del propietario o titular")
    calle: Optional[str] = Field(None, description="Solo el nombre de la calle, avenida o carretera (sin número, lote ni colonia)")
    numero: Optional[str] = Field(None, description="Número oficial o exterior; 'S/N' si no tiene")
    colonia: Optional[str] = Field(None, description="Colonia, barrio o fraccionamiento")
    municipio: Optional[str] = None
    entidad: Optional[str] = Field(None, description="Estado de la República")
    lote: Optional[str] = None
    manzana: Optional[str] = None
    clave_catastral: Optional[str] = Field(None, description="Clave catastral tal como aparece")
    superficie_terreno_m2: Optional[float] = Field(None, description="Superficie del terreno o predio en m2")


class ExtraccionEscritura(DatosInmueble):
    propietario: Optional[str] = Field(None, description="Quien ADQUIERE el inmueble (comprador, donatario)")
    vendedor: Optional[str] = Field(None, description="Quien transmite el inmueble")
    acto: Optional[str] = Field(None, description="Compraventa, donación, adjudicación, etc.")
    numero_escritura: Optional[str] = Field(None, description="Número de escritura o instrumento")
    fecha: Optional[str] = Field(None, description="Fecha de la escritura, AAAA-MM-DD")
    notario: Optional[str] = Field(None, description="Nombre del notario y número de notaría")
    folio_real: Optional[str] = Field(None, description="Folio real o datos de inscripción registral")


class ExtraccionPredial(DatosInmueble):
    propietario: Optional[str] = Field(None, description="Propietario, poseedor o contribuyente")
    cuenta_predial: Optional[str] = Field(None, description="Número de cuenta predial, si es distinto de la clave")
    ejercicio_fiscal: Optional[int] = Field(None, description="Año más reciente que se pagó")
    fecha_pago: Optional[str] = Field(None, description="AAAA-MM-DD")
    superficie_construccion_m2: Optional[float] = None


class ExtraccionAlineamiento(DatosInmueble):
    propietario: Optional[str] = Field(None, description="Solicitante o titular a cuyo nombre se expide")
    numero: Optional[str] = Field(None, description="Número oficial ASIGNADO al predio; 'S/N' si no tiene")
    alineamiento: Optional[str] = Field(None, description="Alineamiento oficial en pocas palabras (frente, restricción)")
    afectaciones: Optional[str] = Field(None, description="Afectaciones o restricciones que limitan el predio; null si no hay")
    fecha_expedicion: Optional[str] = Field(None, description="AAAA-MM-DD")
    vigencia: Optional[str] = Field(None, description="Vigencia tal como aparece en el texto")
    fecha_vencimiento: Optional[str] = Field(None, description="AAAA-MM-DD, solo si el texto la indica")
    autoridad: Optional[str] = Field(None, description="Dependencia y municipio que expide")
    folio: Optional[str] = None


class ExtraccionUsoSuelo(DatosInmueble):
    propietario: Optional[str] = Field(None, description="Titular o solicitante de la licencia")
    uso_autorizado: Optional[str] = Field(None, description="Uso de suelo que se autoriza, tal como aparece")
    giro: Optional[str] = Field(None, description="Giro o actividad autorizada")
    compatible_comercial: Literal["si", "no", "condicionado", "no_determinado"] = Field(
        "no_determinado", description="¿El uso/giro autorizado permite operar el comercio requerido?")
    cita_compatibilidad: Optional[str] = Field(
        None, description="Fragmento COPIADO literalmente del texto (máx. 12 palabras) que justifica compatible_comercial")
    restricciones: list[str] = Field(default_factory=list,
                                     description="Hasta 3 condiciones específicas del uso, máx. 10 palabras cada una")
    superficie_autorizada_m2: Optional[float] = Field(None, description="Superficie máxima autorizada para el uso/giro")
    fecha_expedicion: Optional[str] = Field(None, description="AAAA-MM-DD")
    vigencia: Optional[str] = Field(None, description="Vigencia tal como aparece en el texto")
    fecha_vencimiento: Optional[str] = Field(None, description="AAAA-MM-DD, solo si el texto la indica")
    autoridad: Optional[str] = Field(None, description="Dependencia y municipio que expide")
    folio: Optional[str] = None


ESQUEMA_EXTRACCION: dict[str, type[_Extraccion]] = {
    "Escritura": ExtraccionEscritura, "Predial": ExtraccionPredial,
    "Alineamiento": ExtraccionAlineamiento, "UsoDeSuelo": ExtraccionUsoSuelo,
}


class Clasificacion(_Extraccion):
    tipo: Literal["Escritura", "Predial", "Alineamiento", "UsoDeSuelo", "Otro"]


class RedaccionDictamen(_Extraccion):
    resumen: str = Field(description="Máximo 3 oraciones con los motivos principales")
    observaciones: list[str] = Field(default_factory=list, description="Hasta 3 acciones concretas a seguir")
    estado_sugerido: EstadoExpediente


ETIQUETAS = {
    "propietario": "Propietario / titular", "vendedor": "Vendedor", "acto": "Acto jurídico",
    "calle": "Calle", "numero": "Número oficial", "colonia": "Colonia", "municipio": "Municipio",
    "entidad": "Estado", "lote": "Lote", "manzana": "Manzana", "clave_catastral": "Clave catastral",
    "cuenta_predial": "Cuenta predial", "superficie_terreno_m2": "Superficie del terreno (m²)",
    "superficie_construccion_m2": "Superficie de construcción (m²)", "numero_escritura": "Número de escritura",
    "fecha": "Fecha", "notario": "Notario", "folio_real": "Folio real", "ejercicio_fiscal": "Ejercicio fiscal pagado",
    "fecha_pago": "Fecha de pago", "alineamiento": "Alineamiento", "afectaciones": "Afectaciones",
    "fecha_expedicion": "Fecha de expedición", "vigencia": "Vigencia", "fecha_vencimiento": "Fecha de vencimiento",
    "autoridad": "Autoridad emisora", "folio": "Folio", "uso_autorizado": "Uso autorizado", "giro": "Giro autorizado",
    "compatible_comercial": "Compatible con uso comercial", "cita_compatibilidad": "Justificación de compatibilidad",
    "restricciones": "Restricciones / condiciones", "superficie_autorizada_m2": "Superficie autorizada (m²)",
}


# ---------------------------------------------------------------------------------------
# 2. Salida del análisis
# ---------------------------------------------------------------------------------------
class _Salida(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidencia(_Salida):
    documento: str = Field(description="RutaArchivo del documento (trazabilidad)")
    tipo_documento: Optional[str] = None
    pagina: Optional[int] = Field(None, description="Página 1-based donde aparece el dato")
    cita: str = Field("", description="Fragmento literal del texto OCR alrededor del dato")
    valor: Optional[str] = None
    verificada: bool = Field(False, description="True si el valor se localizó en el texto del documento")


class CampoExtraido(_Salida):
    campo: str
    etiqueta: str
    valor: Any
    evidencia: Optional[Evidencia] = None
    fuente: Literal["llm", "reglas", "llm+reglas"] = "llm"
    valor_reglas: Any = Field(None, description="Valor del extractor por reglas (regex), para doble verificación")
    coincide_reglas: Optional[bool] = Field(None, description="LLM y reglas coinciden (None si solo hay uno)")


class DocumentoAnalizado(_Salida):
    nombre_archivo: str
    ruta_archivo: str
    tipo: Optional[TipoDoc]
    tipo_declarado: Optional[TipoDoc] = None
    tipo_detectado: Optional[TipoDoc] = None
    num_paginas: int = 0
    calidad_texto: Optional[float] = None
    estado_ocr: str = "ok"
    paginas_enviadas_llm: list[int] = Field(default_factory=list)
    campos: dict[str, CampoExtraido] = Field(default_factory=dict)
    error_llm: Optional[str] = None
    calidad: Optional[dict] = Field(None, description="Fase 1 (filtro de calidad del equipo): estado, motivo, mensaje…")
    tiempos: dict[str, float] = Field(default_factory=dict)


class Hallazgo(_Salida):
    id: str
    regla: str
    categoria: Literal["completitud", "calidad", "legibilidad", "identificacion", "consistencia", "vigencia", "uso_suelo",
                       "alineamiento", "predial", "extraccion"]
    resultado: Literal["cumple", "no_cumple", "revisar", "informativo"]
    severidad: Literal["critica", "revision", "info"]
    descripcion: str
    evidencias: list[Evidencia] = Field(default_factory=list)


class ResultadoExpediente(_Salida):
    version: str = VERSION_ANALISIS
    expediente_id: str
    estado: EstadoExpediente
    semaforo: Literal["VERDE", "AMARILLO", "ROJO", "GRIS"] = Field(
        "GRIS", description="Semáforo de main: GRIS = no validado (faltan documentos o hay que volver a subirlos)")
    semaforo_texto: str = ""
    estado_reglas: EstadoExpediente
    estado_llm: Optional[EstadoExpediente] = None
    confianza: float
    nivel_confianza: Literal["alta", "media", "baja"]
    factores_confianza: dict[str, float] = Field(default_factory=dict)
    resumen: str
    observaciones: list[str] = Field(default_factory=list)
    dictamen_por: Literal["llm", "reglas"] = "reglas"
    uso_requerido: str
    fecha_referencia: str
    documentos_recibidos: list[str]
    documentos_faltantes: list[str]
    requisitos_cumplidos: list[str]
    requisitos_no_cumplidos: list[str]
    hallazgos: list[Hallazgo]
    documentos: list[DocumentoAnalizado]
    proveedor_llm: str
    modelo_llm: str
    tiempos: dict[str, float]
