"""Fase 2: extracción de campos — PLANTILLA (aún no implementada).

Llega aquí solo un documento APROBADO por la Fase 1, con:
  doc.ruta                          archivo local
  doc.resultados["calidad"]         resultado del filtro (tipo_detectado, sha256, páginas...)

Qué debe hacer (ver CLAUDE.md, sección "Fase 2"):
  1. Leer el texto de TODAS las páginas con leer_paginas(doc): reutiliza el OCR ya hecho
     por la Fase 1 y devuelve líneas con sus cajas (coordenadas) para la evidencia.
  2. Según tipo_detectado, extraer los campos del esquema (requerimientos, sección 2):
       escritura    propietario*, dirección*, superficie_terreno*, núm. escritura, notario, fecha, folio real
       predial      contribuyente*, dirección*, cuenta/clave predial*, superficie*, periodo pagado
       alineamiento dirección*, número_oficial*, clave catastral*, fecha emisión/vigencia*, autoridad*
       uso_suelo    dirección*, uso autorizado*, compatibilidad comercial*, restricciones, vigencia*, autoridad*
     Formatos fijos (predial, alineamiento, uso de suelo): regex y plantillas.
     Escrituras: buscar fragmentos por palabra clave y mandar solo esos a un LLM barato
     con salida estructurada (Pydantic).
  3. Cada campo: valor, valor_normalizado, confianza y evidencia {pagina, fragmento, bbox}.
  4. continuar=False si falta un campo obligatorio (-> VC-07 / revisión humana).
"""
from __future__ import annotations

from pathlib import Path


def leer_paginas(doc, paginas: list[int] | None = None) -> list[dict]:
    """[{numero, texto, lineas: [(texto, confianza, caja[[x,y]x4])]}] usando la caché OCR.
    Las coordenadas de las cajas están en píxeles del render (lado mayor = 2000 px)."""
    from .etapa_calidad import F
    from .pipeline import CANDADO_OCR, DIR_CACHE_OCR

    with CANDADO_OCR:
        pags = F.leer_documento(Path(doc.ruta), DIR_CACHE_OCR, paginas)
    return [{"numero": p.numero, "origen": p.origen, "texto": p.texto, "lineas": p.lineas} for p in pags]


def ejecutar(doc):
    from .pipeline import ResultadoEtapa

    # TODO(Fase 2): implementar la extracción por tipo.
    return ResultadoEtapa(
        datos={"estado": "PENDIENTE",
               "tipo": doc.resultados.get("calidad", {}).get("tipo_detectado"),
               "campos": {},
               "mensaje": "Extracción aún no implementada."},
        continuar=False,
    )
