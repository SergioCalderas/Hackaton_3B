"""Contrato de datos (Pydantic v2) para documentos.json y expedientes.json.

El JSON Schema se exporta a schemas/ con: python -m ocr_pipeline.schemas
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

VERSION_ESQUEMA = "1.1.0"
# 1.1.0: campo Modo ("completo" | "compacto"); en compacto TextoExtraido y Pagina.Texto son null
#        y Paginas solo incluye las páginas donde se encontró algún campo.

TipoDoc = Literal["Predial", "Alineamiento", "Escritura", "UsoDeSuelo"]
EstadoDoc = Literal["ok", "low_text", "low_confidence", "partial", "error"]
ModoSalida = Literal["completo", "compacto"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Campo(_Base):
    """Un dato extraído del texto, con su evidencia para trazabilidad."""
    Valor: str = Field(description="Valor tal como aparece en el texto (limpio)")
    Normalizado: Union[str, float, list[str], None] = Field(
        description="Valor normalizado para comparar (mayúsculas, sin acentos, solo dígitos, ISO, m2...)")
    Pagina: Optional[int] = Field(description="Página de donde se extrajo (1-based)")
    Evidencia: str = Field(description="Fragmento de texto alrededor del valor")
    Regla: str = Field(description="Regla de extracción que lo encontró")


class Pagina(_Base):
    Numero: int
    Texto: Optional[str] = Field(description="Texto de la página (null en modo compacto)")
    Metodo: Literal["native", "ocr", "error"]
    Motor: Optional[str] = Field(description="tesseract | paddle | null (texto nativo del PDF)")
    CalidadTexto: Optional[float] = Field(description="Proporción 0..1 de tokens válidos en español")


class Documento(_Base):
    VersionEsquema: str = VERSION_ESQUEMA
    Modo: ModoSalida = Field("completo", description="completo: con texto; compacto: solo campos y evidencia")
    NombreArchivo: str
    RutaArchivo: str = Field(description="Ruta relativa del archivo de origen (trazabilidad)")
    TipoDocumento: Optional[TipoDoc] = Field(description="TipoDeclarado si existe; si no, TipoDetectado")
    TipoDeclarado: Optional[TipoDoc] = Field(description="Tipo indicado por el usuario o por la carpeta")
    TipoDetectado: Optional[TipoDoc] = Field(description="Tipo inferido del contenido por palabras clave")
    TextoExtraido: Optional[str] = Field(
        description="Texto completo; páginas unidas con doble salto de línea (null en modo compacto)")
    Paginas: list[Pagina] = Field(
        description="Todas las páginas (completo) o solo aquellas donde se encontró algún campo (compacto)")
    Estado: EstadoDoc
    CalidadTexto: Optional[float]
    NumPaginas: int
    Hash: Optional[str] = Field(description="SHA-256 truncado a 16 caracteres")
    DuplicadoDe: Optional[str] = Field(description="RutaArchivo del documento idéntico ya procesado")
    CamposExtraidos: dict[str, Campo] = Field(default_factory=dict)
    Discrepancias: list[str] = Field(default_factory=list,
                                     description="Problemas propios del documento (p. ej. tipo declarado != detectado)")
    ExpedienteId: Optional[str] = None


class ValorFuente(_Base):
    Documento: str = Field(description="RutaArchivo del documento")
    TipoDocumento: Optional[TipoDoc]
    Valor: str
    Normalizado: Union[str, float, list[str], None]
    Pagina: Optional[int]


class CampoConsolidado(_Base):
    Valor: str = Field(description="Valor más frecuente entre los documentos")
    Normalizado: Union[str, float, list[str], None]
    Fuentes: list[ValorFuente]


class Discrepancia(_Base):
    Campo: str
    Detalle: str
    Similitud: Optional[float] = Field(None, description="0..1 (1 = idéntico) cuando aplica")
    Valores: list[ValorFuente]


class ComparacionPar(_Base):
    DocumentoA: str
    DocumentoB: str
    Puntaje: Optional[float]
    Coinciden: list[str]
    NoCoinciden: list[str]


class Expediente(_Base):
    VersionEsquema: str = VERSION_ESQUEMA
    Modo: ModoSalida = Field("completo", description="Modo de los Documentos incluidos")
    ExpedienteId: str
    CamposConsolidados: dict[str, CampoConsolidado]
    PuntajeMatch: Optional[float] = Field(description="Promedio 0..1 del puntaje entre pares de documentos")
    NivelMatch: Literal["alto", "medio", "bajo", "sin_datos"]
    CamposCoinciden: list[str]
    CamposNoCoinciden: list[Discrepancia]
    TiposPresentes: list[TipoDoc]
    DocumentosFaltantes: list[TipoDoc]
    Alertas: list[str] = Field(default_factory=list)
    Comparaciones: list[ComparacionPar] = Field(default_factory=list)
    Documentos: list[Documento]


MODELOS = {"Campo": Campo, "Pagina": Pagina, "Documento": Documento, "Expediente": Expediente}


def exportar_schemas(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, model in MODELOS.items():
        p = dest / f"{name}.schema.json"
        p.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(p)
    return paths


if __name__ == "__main__":
    from .config import PROJECT_ROOT
    for p in exportar_schemas(PROJECT_ROOT / "schemas"):
        print(p)
