"""Pipeline OCR local para expedientes de inmuebles.

API pública:
    procesar_documento(ruta, tipo_declarado=None) -> dict (Documento)
    verificar_expediente([(ruta, tipo_declarado), ...]) -> dict (Expediente)
"""
def __getattr__(name):
    if name == "VERSION_ESQUEMA":
        from .schemas import VERSION_ESQUEMA
        return VERSION_ESQUEMA
    raise AttributeError(name)


def procesar_documento(*args, **kwargs):
    from .servicio import procesar_documento as _f  # import diferido: no carga OpenCV/Paddle al importar
    return _f(*args, **kwargs)


def verificar_expediente(*args, **kwargs):
    from .servicio import verificar_expediente as _f
    return _f(*args, **kwargs)


__all__ = ["procesar_documento", "verificar_expediente", "VERSION_ESQUEMA"]
