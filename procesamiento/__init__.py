"""Pipeline de procesamiento de documentos del expediente.

  fuentes.py           de dónde sale el archivo (base de datos, URL, ruta, bytes)
  pipeline.py          orden de las etapas y contrato entre ellas
  etapa_calidad.py     Fase 1: filtro de calidad (usa filtro_calidad/)
  etapa_extraccion.py  Fase 2: extracción de campos (adaptador sobre ocr_pipeline)
  etapa_verificacion.py validación cruzada del expediente (VC-xx) -> observaciones
  observaciones.py     observaciones estructuradas (Fase 1 + VC) para front y dictamen
  dictamen.py          semáforo determinista + redacción (LLM o plantilla)
  api.py               endpoints Flask que registra server/app.py
"""
