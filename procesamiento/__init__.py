"""Pipeline de procesamiento de documentos del expediente.

  fuentes.py           de dónde sale el archivo (base de datos, URL, ruta, bytes)
  pipeline.py          orden de las etapas y contrato entre ellas
  etapa_calidad.py     Fase 1: filtro de calidad (usa filtro_calidad/)
  etapa_extraccion.py  Fase 2: extracción de campos (pendiente; aquí se conecta)
  api.py               endpoints Flask que registra server/app.py
"""
