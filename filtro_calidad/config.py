"""Configuración del filtro de calidad (Fase 1: recepción).

Todo lo ajustable vive aquí: umbrales de legibilidad, frases clave por tipo
de documento y documentos que se deben rechazar. Las frases van en minúsculas
y sin acentos (el texto del OCR se normaliza igual antes de comparar).
"""

VERSION_REGLAS = "filtro-calidad v0.1"

# --------------------------------------------------------------------------
# Umbrales
# --------------------------------------------------------------------------
UMBRALES = {
    # Formato y tamaño
    "extensiones": [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"],
    "max_mb": 60,
    # Páginas a revisar por documento (primeras N + mitad + última)
    "paginas_inicio": 3,
    "max_paginas_ocr": 5,
    # Render: lado mayor de la página en px (≈150 dpi en carta)
    "lado_px": 2000,
    # PDF con texto nativo: si una página trae al menos esto, no se hace OCR
    "min_chars_texto_nativo": 200,
    # Página en blanco: desviación estándar de grises muy baja
    "std_pagina_blanca": 4.0,
    # Legibilidad de una página (OCR)
    "conf_linea_ok": 0.80,      # una línea cuenta como leída si su confianza >= esto
    "min_chars_legible": 150,   # caracteres leídos con confianza en una página con contenido
    "conf_media_ok": 0.85,      # confianza media ponderada para "legible"
    "conf_media_dudosa": 0.75,  # entre dudosa y ok -> revisión manual
    # Documento: proporción de páginas revisadas que deben ser legibles
    "prop_paginas_ok": 0.70,
    "prop_paginas_revision": 0.50,
    # Nitidez (varianza del Laplaciano a 1600 px). Solo genera observación.
    "laplaciano_bajo": 150,
    # Clasificación por frases clave
    "min_puntaje_tipo": 6,
    "margen_tipo": 3,
    # Similitud TF-IDF con los aprobados (segunda opinión)
    "min_similitud": 0.10,
}

# --------------------------------------------------------------------------
# Los 4 tipos válidos.
#   titulo:  frases que suelen estar en el encabezado (primeros ~800 caracteres
#            de la primera página). Valen 6 puntos.
#   fuertes: frases muy propias del tipo. Valen 3 puntos.
#   debiles: frases que ayudan pero pueden salir en otros tipos. Valen 1 punto.
#   carpetas: nombres de carpeta que indican el tipo declarado.
# --------------------------------------------------------------------------
TIPOS = {
    "escritura": {
        "nombre": "Escritura",
        "carpetas": ["escritura", "escrituras"],
        "titulo": ["notario publico", "notaria publica", "instrumento numero", "acta numero",
                   "volumen", "escritura publica", "escritura numero", "titulo de propiedad", "notaria"],
        "fuertes": ["notario publico", "notaria publica", "instrumento numero", "escritura publica",
                    "titulo de propiedad", "registro agrario nacional", "solar urbano", "ley agraria",
                    "sucesion", "adjudicacion", "albacea", "herencia", "volumen numero",
                    "ante mi", "comparecen", "comparece", "antecedentes", "clausulas",
                    "contrato de compraventa", "compraventa", "donacion", "doy fe",
                    "fe publica", "protocolo", "testimonio", "registro publico de la propiedad",
                    "folio real", "parte vendedora", "parte compradora", "personalidad",
                    "generales"],
        "debiles": ["medidas y colindancias", "al norte", "al sur", "al oriente", "al poniente",
                    "superficie", "inmueble", "lote", "manzana", "otorgantes", "apendice"],
    },
    "predial": {
        "nombre": "Predial",
        "carpetas": ["predial"],
        # "predial", "cuenta predial" y "clave catastral" salen en casi todos los
        # documentos del expediente, por eso solo cuentan como débiles.
        "titulo": ["impuesto predial", "recibo oficial de pago", "tesoreria", "tarjeta predial",
                   "boleta predial", "pago de predial", "pago predial", "folio predial",
                   "formato universal de pago", "comprobante de pago"],
        "fuertes": ["impuesto predial", "valor catastral", "tesoreria", "recibo oficial",
                    "linea de captura", "total pagado", "total a pagar", "contribuyente",
                    "bonificacion", "recargos", "datos de la contribucion", "ejercicio fiscal",
                    "tarjeta predial", "periodo pagado", "periodo de pago", "folio fiscal",
                    "forma de pago", "metodo de pago"],
        "debiles": ["predial", "cuenta predial", "clave catastral", "superficie de terreno",
                    "superficie construccion", "multas", "impuesto", "caja", "pagado", "importe",
                    "bimestre"],
    },
    "alineamiento": {
        "nombre": "Alineamiento y Número Oficial",
        "carpetas": ["alineamiento_y_numero_oficial", "alineamiento", "numero_oficial"],
        "titulo": ["alineamiento", "numero oficial", "constancia de alineamiento",
                   "certificacion de alineamiento"],
        "fuertes": ["alineamiento y numero oficial", "constancia de alineamiento",
                    "numero oficial", "alineamiento", "no oficial", "via publica",
                    "restriccion", "desarrollo urbano", "lineamiento", "licencia de alineamiento"],
        "debiles": ["vigencia", "vencimiento", "colindancias", "predio", "frente",
                    "metros lineales", "obras publicas", "ordenamiento territorial", "linda con"],
    },
    "uso_suelo": {
        "nombre": "Uso de Suelo",
        "carpetas": ["uso_de_suelo", "uso_suelo", "usodesuelo"],
        "titulo": ["uso de suelo", "uso del suelo", "licencia de uso", "zonificacion",
                   "factibilidad de uso"],
        "fuertes": ["licencia de uso de suelo", "licencia de uso del suelo", "uso de suelo",
                    "uso del suelo", "zonificacion", "giro", "coeficiente de ocupacion",
                    "coeficiente de utilizacion", "cos", "cus", "cajones de estacionamiento",
                    "estacionamiento", "niveles maximos", "area libre", "densidad",
                    "uso habitacional", "uso comercial", "compatible", "compatibilidad"],
        "debiles": ["vigencia", "desarrollo urbano", "superficie", "altura", "comercial",
                    "habitacional", "restricciones", "condicionantes", "plan municipal"],
    },
}

# --------------------------------------------------------------------------
# Documentos que NO forman parte del expediente. Si alguno gana a los 4 tipos,
# el archivo se manda a "volver a subir".
# --------------------------------------------------------------------------
NEGATIVOS = {
    "recibo_luz": {
        "nombre": "recibo de luz (CFE)",
        "frases": ["comision federal de electricidad", "cfe", "kwh", "suministrador de servicios basicos",
                   "consumo de energia", "lectura actual", "lectura anterior", "energia electrica"],
    },
    "recibo_agua": {
        "nombre": "recibo de agua",
        "frases": ["agua potable", "organismo operador", "consumo m3", "alcantarillado",
                   "servicio de agua", "sistema de agua", "consumo de agua"],
    },
    "ine": {
        "nombre": "identificación oficial (INE)",
        "frases": ["instituto nacional electoral", "credencial para votar", "clave de elector",
                   "curp", "fecha de nacimiento"],
    },
    "estado_cuenta": {
        "nombre": "estado de cuenta bancario",
        "frases": ["estado de cuenta", "saldo anterior", "saldo promedio", "saldo final",
                   "numero de cuenta", "tarjeta de credito", "movimientos del periodo"],
    },
    "constancia_fiscal": {
        "nombre": "constancia de situación fiscal (SAT)",
        "frases": ["constancia de situacion fiscal", "servicio de administracion tributaria",
                   "cedula de identificacion fiscal", "regimen fiscal", "id cif"],
    },
    "acta_civil": {
        "nombre": "acta del registro civil",
        "frases": ["acta de nacimiento", "acta de matrimonio", "registro civil", "oficialia",
                   "nombre del registrado", "datos de los padres"],
    },
    "telefono_internet": {
        "nombre": "recibo de teléfono / internet",
        "frases": ["telmex", "izzi", "totalplay", "megacable", "telefonia",
                   "numero telefonico", "servicio de telecomunicaciones"],
    },
    "contrato_arrendamiento": {
        "nombre": "contrato de arrendamiento",
        "frases": ["contrato de arrendamiento", "arrendador", "arrendatario", "renta mensual",
                   "deposito en garantia", "fiador"],
    },
}

# Señales de que el documento es del tipo correcto pero no sirve como está.
# Mandan el archivo a revisión manual (no se rechaza automáticamente).
SENALES_REVISION = [
    ("no es el comprobante de pago", "Es un formato/línea de captura, no el comprobante de pago."),
    ("solo es valido con la certificacion", "Es un formato de pago sin certificación bancaria."),
    ("documento cancelado", "El documento aparece como cancelado."),
    ("comprobante cancelado", "El comprobante aparece como cancelado."),
]

# Señales que solo se anotan como observación (las evalúa la fase de reglas: RG-01, RG-04).
SENALES_OBSERVACION = [
    ("pendientes de pago", "Menciona adeudos o ejercicios pendientes de pago (RG-04)."),
    ("con adeudo", "Menciona adeudos (RG-04)."),
    ("adeudo pendiente", "Menciona adeudos (RG-04)."),
]

# Mensajes para quien sube el documento
MENSAJES = {
    "archivo_invalido": "No pudimos abrir el archivo. Súbelo de nuevo en PDF, JPG o PNG.",
    "formato_no_soportado": "Formato no soportado. Sube el documento en PDF, JPG o PNG.",
    "archivo_grande": "El archivo es demasiado grande. Comprímelo o súbelo escaneado a 200–300 dpi.",
    "en_blanco": "El archivo está en blanco. Sube el documento completo.",
    "ilegible": "El documento no se puede leer (borroso, oscuro o con muy baja resolución). "
                "Escanéalo a 200–300 dpi o toma la foto de frente, con buena luz y sin sombras.",
    "parcialmente_ilegible": "Varias páginas no se pueden leer. Revísalas y vuelve a subir el documento completo.",
    "tipo_no_reconocido": "El archivo no parece ser ninguno de los 4 documentos del expediente "
                          "(Escritura, Predial, Alineamiento y Número Oficial, Uso de Suelo).",
    "otro_documento": "El archivo parece ser {doc}, que no forma parte del expediente. "
                      "Sube el documento solicitado.",
    "tipo_incorrecto": "Subiste {detectado} en el lugar de {declarado}. Sube el documento correcto.",
}
