"""Análisis inteligente de expedientes de inmuebles (multiagente con LangChain + LangGraph).

    from analisis import analizar_expediente
    res = analizar_expediente([("Escritura/01 Escritura.pdf", "Escritura"),
                               ("Predial/02 Predial.pdf", "Predial"),
                               ("Alineamiento_y_Numero_Oficial/03 Alineamiento y Numero Oficial.pdf", "Alineamiento"),
                               ("Uso_de_suelo/04 Licencia de Uso de Suelo.pdf", "UsoDeSuelo")])
    res["estado"], res["hallazgos"], res["tiempos"]["total_s"]

El proveedor del LLM se elige con LLM_PROVIDER=local|online en el archivo .env (ver .env.example).
"""
from .config import Ajustes, ConfiguracionError


def analizar_expediente(*args, **kwargs):
    from .grafo import analizar_expediente as _f  # import diferido: no carga LangGraph/PyMuPDF al importar
    return _f(*args, **kwargs)


__all__ = ["Ajustes", "ConfiguracionError", "analizar_expediente"]
