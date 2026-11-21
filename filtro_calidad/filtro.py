"""Filtro de calidad de documentos — Fase 1 (Recepción).

Decide, antes de extraer información, si cada archivo:
  1. se puede abrir y está en un formato aceptado,
  2. es legible (no está en blanco, borroso ni demasiado oscuro),
  3. es uno de los 4 documentos del expediente (y el que se declaró),
y lo manda a una de tres categorías:

  APROBADO         -> pasa a extracción de información
  REVISION_MANUAL  -> dudoso; lo revisa una persona
  VOLVER_A_SUBIR   -> mala calidad o documento equivocado; se pide de nuevo

Uso:
  python filtro.py <carpeta_entrada> [--salida carpeta] [--sin-copias]

<carpeta_entrada> puede tener subcarpetas por tipo (Escritura/, Predial/,
Alineamiento_y_Numero_Oficial/, Uso_de_suelo/). El nombre de la subcarpeta
se toma como el tipo declarado por quien subió el archivo.

Todo corre local en CPU: PyMuPDF (texto/render), OpenCV (métricas de imagen)
y RapidOCR (motor de PaddleOCR sobre ONNX) solo cuando el PDF no trae texto.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

U = C.UMBRALES

# ==========================================================================
# Utilidades de texto
# ==========================================================================

def normalizar(texto: str) -> str:
    """minúsculas, sin acentos, solo letras/números y espacios simples.
    Corrige confusiones típicas del OCR (0 <-> o dentro de palabras)."""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"(?<=[a-z])0|0(?=[a-z])", "o", t)
    t = re.sub(r"[^a-z0-9ñ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_regex_cache: dict[str, re.Pattern] = {}


def contiene(texto_norm: str, frase: str) -> bool:
    pat = _regex_cache.get(frase)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(frase).replace(r"\ ", r"\s?") + r"\b")
        _regex_cache[frase] = pat
    return bool(pat.search(texto_norm))


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# ==========================================================================
# OCR (carga perezosa: solo si algún documento lo necesita)
# ==========================================================================
_ocr = None


def motor_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        _ocr = RapidOCR(params={
            "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE,
            "Rec.lang_type": LangRec.LATIN,  # español
            "Cls.ocr_version": OCRVersion.PPOCRV4,
            "Global.log_level": "error",
        })
    return _ocr


def ocr_imagen(img_rgb: np.ndarray) -> list[tuple[str, float, list]]:
    r = motor_ocr()(img_rgb)
    if not r.txts:
        return []
    return [(t, float(s), np.asarray(b).round().astype(int).tolist())
            for t, s, b in zip(r.txts, r.scores, r.boxes)]


# ==========================================================================
# Análisis por página
# ==========================================================================

@dataclass
class Pagina:
    numero: int
    origen: str = ""            # "texto_nativo" | "ocr"
    en_blanco: bool = False
    chars_leidos: int = 0
    confianza: float = 0.0
    laplaciano: float = 0.0
    contraste: float = 0.0
    dpi_imagen: float = 0.0
    rotacion: int = 0
    foto: bool = False
    estado: str = ""            # "legible" | "dudosa" | "ilegible" | "en_blanco"
    texto: str = field(default="", repr=False)
    lineas: list = field(default_factory=list, repr=False)


def paginas_a_revisar(n: int) -> list[int]:
    idx = list(range(min(n, U["paginas_inicio"])))
    for extra in (n // 2, n - 1):
        if 0 <= extra < n and extra not in idx:
            idx.append(extra)
    return idx[: U["max_paginas_ocr"]]


def render(pg: pymupdf.Page) -> np.ndarray:
    lado = max(pg.rect.width, pg.rect.height)
    zoom = min(U["lado_px"] / lado, 4.0)
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3).copy()


def dpi_efectivo(pg: pymupdf.Page) -> float:
    """dpi real de la imagen más grande de la página (escaneos)."""
    mejor = 0.0
    try:
        for info in pg.get_image_info():
            w_pt = info["bbox"][2] - info["bbox"][0]
            if w_pt > pg.rect.width * 0.5 and info.get("width"):
                mejor = max(mejor, info["width"] / (w_pt / 72.0))
    except Exception:
        pass
    return mejor


def metricas_imagen(img_rgb: np.ndarray) -> tuple[float, float, bool]:
    gris = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    escala = 1600 / max(gris.shape)
    peq = cv2.resize(gris, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    lap = float(cv2.Laplacian(peq, cv2.CV_64F).var())
    std = float(peq.std())
    # Foto de celular: bordes oscuros / fondo (mesa) alrededor de la hoja
    b = max(4, int(min(peq.shape) * 0.03))
    borde = np.concatenate([peq[:b].ravel(), peq[-b:].ravel(), peq[:, :b].ravel(), peq[:, -b:].ravel()])
    foto = float(np.median(borde)) < 150
    return lap, std, foto


def leer_ocr(img: np.ndarray) -> tuple[list, int]:
    """OCR; si casi no sale texto prueba la página girada 90/270 grados."""
    lineas = ocr_imagen(img)
    if sum(len(t) for t, s, _ in lineas if s >= U["conf_linea_ok"]) >= U["min_chars_legible"]:
        return lineas, 0
    mejor, rot = lineas, 0
    for k, grados in ((1, 90), (3, 270)):
        otra = ocr_imagen(np.ascontiguousarray(np.rot90(img, k)))
        if sum(len(t) for t, *_ in otra) > sum(len(t) for t, *_ in mejor) * 1.5:
            mejor, rot = otra, grados
    return mejor, rot


def analizar_pagina(pg: pymupdf.Page, numero: int, cache: dict) -> Pagina:
    p = Pagina(numero=numero + 1)
    nativo = pg.get_text().strip()
    img = render(pg)
    p.laplaciano, p.contraste, p.foto = metricas_imagen(img)
    p.dpi_imagen = round(dpi_efectivo(pg), 1)

    if len(nativo) >= U["min_chars_texto_nativo"]:
        p.origen, p.texto, p.chars_leidos, p.confianza = "texto_nativo", nativo, len(nativo), 1.0
        p.estado = "legible"
        return p

    if p.contraste < U["std_pagina_blanca"]:
        p.en_blanco, p.estado, p.origen = True, "en_blanco", "imagen"
        return p

    clave = str(numero)
    if clave in cache:
        lineas, p.rotacion = cache[clave]["lineas"], cache[clave]["rotacion"]
    else:
        lineas, p.rotacion = leer_ocr(img)
        cache[clave] = {"lineas": lineas, "rotacion": p.rotacion}

    p.origen = "ocr"
    p.lineas = lineas
    p.texto = "\n".join(t for t, *_ in lineas)
    ok = [(t, s) for t, s, _ in lineas if s >= U["conf_linea_ok"]]
    p.chars_leidos = sum(len(t) for t, _ in ok)
    total = sum(len(t) for t, *_ in lineas)
    p.confianza = round(sum(len(t) * s for t, s, _ in lineas) / total, 3) if total else 0.0

    if p.chars_leidos >= U["min_chars_legible"] and p.confianza >= U["conf_media_ok"]:
        p.estado = "legible"
    elif p.chars_leidos >= U["min_chars_legible"] and p.confianza >= U["conf_media_dudosa"]:
        p.estado = "dudosa"
    else:
        p.estado = "ilegible"
    return p


# ==========================================================================
# Clasificación del tipo de documento
# ==========================================================================

def puntuar_tipos(texto_doc: str, texto_pag1: str) -> tuple[dict, dict, dict]:
    doc_n = normalizar(texto_doc)
    enc_n = normalizar(texto_pag1)[:800]
    puntos, evidencia = {}, {}
    for clave, t in C.TIPOS.items():
        pts, ev = 0, []
        for f in t["titulo"]:
            if contiene(enc_n, f):
                pts += 6; ev.append(f"[encabezado] {f}")
        for f in t["fuertes"]:
            if contiene(doc_n, f):
                pts += 3; ev.append(f)
        for f in t["debiles"]:
            if contiene(doc_n, f):
                pts += 1
        puntos[clave], evidencia[clave] = pts, ev
    negativos = {}
    for clave, t in C.NEGATIVOS.items():
        hits = [f for f in t["frases"] if contiene(doc_n, f)]
        negativos[clave] = (3 * len(hits), hits)
    return puntos, evidencia, negativos


def tipos_por_pagina(paginas: list) -> dict:
    """Tipo de cada página con señal clara (para detectar archivos combinados).
    Solo cuenta una página si su encabezado la identifica y gana con margen."""
    salida = {}
    for p in paginas:
        pts, evid, _ = puntuar_tipos(p.texto, p.texto)
        orden = sorted(pts.items(), key=lambda kv: kv[1], reverse=True)
        (t1, a), (_, b) = orden[0], orden[1]
        con_titulo = any(e.startswith("[encabezado]") for e in evid[t1])
        salida[p.numero] = t1 if (con_titulo and a >= 12 and a - b >= 6) else None
    return salida


def tipo_declarado(ruta: Path, raiz: Path) -> str | None:
    try:
        partes = ruta.relative_to(raiz).parts[:-1]
    except ValueError:
        partes = ()
    for parte in reversed(partes):
        n = normalizar(parte).replace(" ", "_")
        for clave, t in C.TIPOS.items():
            if n in t["carpetas"]:
                return clave
    return None


# ==========================================================================
# Documento
# ==========================================================================

@dataclass
class Resultado:
    archivo: str
    sha256: str = ""
    tamano_kb: int = 0
    paginas_total: int = 0
    paginas_revisadas: list = field(default_factory=list)
    tipo_declarado: str | None = None
    tipo_detectado: str | None = None
    confianza_tipo: float = 0.0
    puntajes: dict = field(default_factory=dict)
    evidencia_tipo: list = field(default_factory=list)
    margen_tipo: int = 0
    tipos_por_pagina: dict = field(default_factory=dict)
    similitud_aprobados: float | None = None
    tipo_similitud: str | None = None
    legibilidad: float = 0.0
    confianza_ocr: float = 0.0
    estado: str = ""
    motivo: str = ""
    mensaje: str = ""
    observaciones: list = field(default_factory=list)
    segundos: float = 0.0
    texto: str = field(default="", repr=False)


def abrir(ruta: Path) -> pymupdf.Document:
    doc = pymupdf.open(ruta)
    if not doc.is_pdf:  # imagen -> PDF de 1 página
        pdf = pymupdf.open("pdf", doc.convert_to_pdf())
        doc.close()
        return pdf
    return doc


def evaluar(ruta: Path, raiz: Path, dir_cache: Path) -> Resultado:
    t0 = time.time()
    r = Resultado(archivo=str(ruta.relative_to(raiz)) if ruta.is_relative_to(raiz) else ruta.name)
    r.tipo_declarado = tipo_declarado(ruta, raiz)
    r.tamano_kb = ruta.stat().st_size // 1024

    def fin(estado, motivo, **fmt):
        r.estado, r.motivo = estado, motivo
        r.mensaje = C.MENSAJES.get(motivo, motivo).format(**fmt) if motivo in C.MENSAJES else motivo
        r.segundos = round(time.time() - t0, 1)
        return r

    # ---- 1. Formato ---------------------------------------------------------
    if ruta.suffix.lower() not in U["extensiones"]:
        return fin("VOLVER_A_SUBIR", "formato_no_soportado")
    if r.tamano_kb > U["max_mb"] * 1024:
        return fin("VOLVER_A_SUBIR", "archivo_grande")
    r.sha256 = sha256(ruta)
    try:
        doc = abrir(ruta)
        if doc.needs_pass:
            r.observaciones.append("PDF protegido con contraseña.")
            return fin("VOLVER_A_SUBIR", "archivo_invalido")
        r.paginas_total = doc.page_count
        if r.paginas_total == 0:
            return fin("VOLVER_A_SUBIR", "archivo_invalido")
    except Exception as e:  # archivo corrupto
        r.observaciones.append(f"Error al abrir: {e}")
        return fin("VOLVER_A_SUBIR", "archivo_invalido")

    # ---- 2. Legibilidad -----------------------------------------------------
    f_cache = dir_cache / f"{r.sha256[:16]}.json"
    cache = json.loads(f_cache.read_text("utf-8")) if f_cache.exists() else {}
    paginas = [analizar_pagina(doc[i], i, cache) for i in paginas_a_revisar(doc.page_count)]
    f_cache.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
    doc.close()

    r.paginas_revisadas = [{k: v for k, v in asdict(p).items() if k not in ("texto", "lineas")}
                           for p in paginas]
    con_contenido = [p for p in paginas if not p.en_blanco]
    blancas = len(paginas) - len(con_contenido)
    if blancas:
        r.observaciones.append(f"{blancas} página(s) en blanco entre las revisadas.")
    if not con_contenido:
        return fin("VOLVER_A_SUBIR", "en_blanco")

    legibles = [p for p in con_contenido if p.estado == "legible"]
    dudosas = [p for p in con_contenido if p.estado == "dudosa"]
    r.legibilidad = round((len(legibles) + 0.5 * len(dudosas)) / len(con_contenido), 2)
    ocr_pags = [p for p in con_contenido if p.origen == "ocr"]
    r.confianza_ocr = round(float(np.mean([p.confianza for p in ocr_pags])), 3) if ocr_pags else 1.0

    if any(p.foto for p in con_contenido):
        r.observaciones.append("Parece foto de celular (se ve fondo alrededor de la hoja).")
    if any(p.rotacion for p in con_contenido):
        r.observaciones.append("Hay páginas giradas; se leyeron rotándolas.")
    bajos_dpi = [p.numero for p in con_contenido if 0 < p.dpi_imagen < 120]
    if bajos_dpi:
        r.observaciones.append(f"Resolución baja (<120 dpi) en página(s) {bajos_dpi}.")
    borrosas = [p.numero for p in con_contenido if p.laplaciano < U["laplaciano_bajo"]]
    if borrosas:
        r.observaciones.append(f"Imagen poco nítida en página(s) {borrosas}.")
    ilegibles = [p.numero for p in con_contenido if p.estado == "ilegible"]
    if ilegibles:
        r.observaciones.append(f"No se pudo leer la(s) página(s) {ilegibles}.")

    r.texto = "\n".join(p.texto for p in paginas)
    primera = con_contenido[0]

    if r.legibilidad < U["prop_paginas_revision"] or (primera.estado == "ilegible" and r.legibilidad < U["prop_paginas_ok"]):
        return fin("VOLVER_A_SUBIR", "ilegible" if r.legibilidad < 0.25 else "parcialmente_ilegible")

    # ---- 3. Tipo de documento ----------------------------------------------
    puntos, evid, negativos = puntuar_tipos(r.texto, primera.texto)
    r.puntajes = puntos
    orden = sorted(puntos.items(), key=lambda kv: kv[1], reverse=True)
    (mejor, p1), (_, p2) = orden[0], orden[1]
    r.confianza_tipo = round(p1 / (p1 + p2), 2) if p1 else 0.0
    neg_clave, (neg_pts, neg_hits) = max(negativos.items(), key=lambda kv: kv[1][0])

    if neg_pts >= U["min_puntaje_tipo"] and neg_pts > p1:
        r.evidencia_tipo = neg_hits
        return fin("VOLVER_A_SUBIR", "otro_documento", doc=C.NEGATIVOS[neg_clave]["nombre"])
    if p1 < U["min_puntaje_tipo"]:
        r.evidencia_tipo = evid[mejor]
        # Legible y con algo de señal del tipo declarado: mejor que lo vea una persona
        if r.tipo_declarado and puntos[r.tipo_declarado] >= 3 and r.legibilidad >= U["prop_paginas_ok"]:
            r.tipo_detectado = r.tipo_declarado
            return fin("REVISION_MANUAL", "Legible, pero no se pudo confirmar el tipo de documento "
                       f"(puntaje {puntos[r.tipo_declarado]} para {C.TIPOS[r.tipo_declarado]['nombre']}).")
        return fin("VOLVER_A_SUBIR", "tipo_no_reconocido")

    r.tipo_detectado = mejor
    r.evidencia_tipo = evid[mejor][:8]
    nombre = lambda k: C.TIPOS[k]["nombre"] if k else "—"  # noqa: E731

    tipos_pag = tipos_por_pagina(con_contenido)
    if (r.tipo_declarado and r.tipo_declarado != mejor
            and p1 - puntos[r.tipo_declarado] >= U["margen_tipo"]
            and r.tipo_declarado not in tipos_pag.values()):
        return fin("VOLVER_A_SUBIR", "tipo_incorrecto",
                   detectado=nombre(mejor), declarado=nombre(r.tipo_declarado))

    # ---- 4. Señales de revisión -----------------------------------------
    pendientes = []
    r.tipos_por_pagina = tipos_pag
    distintos = sorted({t for t in tipos_pag.values() if t})
    if len(distintos) > 1:
        detalle = ", ".join(f"p{n}: {nombre(t)}" for n, t in tipos_pag.items() if t)
        pendientes.append(f"El archivo parece traer varios documentos juntos ({detalle}).")
    if p1 - p2 < U["margen_tipo"]:
        pendientes.append(f"Tipo ambiguo: {nombre(mejor)} ({p1}) vs {nombre(orden[1][0])} ({p2}).")
    if r.tipo_declarado and r.tipo_declarado != mejor:
        pendientes.append(f"Declarado como {nombre(r.tipo_declarado)}, se detectó {nombre(mejor)}.")
    if r.legibilidad < U["prop_paginas_ok"]:
        pendientes.append("Calidad de lectura baja en varias páginas.")
    elif dudosas:
        r.observaciones.append(f"Lectura con confianza media en página(s) {[p.numero for p in dudosas]}.")
    doc_n = normalizar(r.texto)
    for frase, explicacion in C.SENALES_REVISION:
        if contiene(doc_n, frase):
            pendientes.append(explicacion)
    for frase, explicacion in C.SENALES_OBSERVACION:
        if contiene(doc_n, frase) and explicacion not in r.observaciones:
            r.observaciones.append(explicacion)
    r.margen_tipo = p1 - p2

    vencida = revisar_vigencia(r.texto)
    if vencida:
        r.observaciones.append(vencida)

    if pendientes:
        r.observaciones = pendientes + r.observaciones
        return fin("REVISION_MANUAL", pendientes[0])
    return fin("APROBADO", "Documento legible y del tipo correcto.")


# ==========================================================================
# Vigencia (solo observación; el riesgo RG-01 se evalúa en la fase de reglas)
# ==========================================================================
MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}


def revisar_vigencia(texto: str) -> str | None:
    t = normalizar(texto)
    fechas = []
    for m in re.finditer(r"(vigencia|vencimiento|vigente hasta|valido hasta)\D{0,25}"
                         r"(\d{1,2}) (?:de )?([a-z]+) (?:de )?(?:del )?(\d{4})", t):
        mes = MESES.get(m.group(3))
        if mes:
            try:
                fechas.append(dt.date(int(m.group(4)), mes, int(m.group(2))))
            except ValueError:
                pass
    for m in re.finditer(r"(vigencia|vencimiento|vigente hasta)\D{0,25}(\d{1,2}) (\d{1,2}) (\d{4})", t):
        try:
            fechas.append(dt.date(int(m.group(4)), int(m.group(3)), int(m.group(2))))
        except ValueError:
            pass
    if fechas and max(fechas) < dt.date.today():
        return f"Posible vigencia vencida: {max(fechas).isoformat()}."
    return None


# ==========================================================================
# Segunda opinión: similitud TF-IDF con los documentos aprobados
# ==========================================================================

def segunda_opinion(resultados: list[Resultado]) -> None:
    """Compara cada documento contra los aprobados de cada tipo (sin contarse a sí mismo).
    Si el tipo más parecido no coincide con el detectado, pasa a revisión manual."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        return
    con_texto = [r for r in resultados if r.texto.strip()]
    ref = [r for r in con_texto if r.estado == "APROBADO"]
    if len({r.tipo_detectado for r in ref}) < 2:
        return
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True,
                          preprocessor=normalizar)
    vec.fit([r.texto for r in ref])
    X = vec.transform([r.texto for r in con_texto])
    idx_ref = {id(r): i for i, r in enumerate(con_texto)}
    sim = (X @ X.T).toarray()
    for i, r in enumerate(con_texto):
        por_tipo = {}
        for a in ref:
            j = idx_ref[id(a)]
            if j != i:
                por_tipo.setdefault(a.tipo_detectado, []).append(sim[i, j])
        if not por_tipo:
            continue
        # promedio de los 3 más parecidos de cada tipo
        puntaje = {k: float(np.mean(sorted(v)[-3:])) for k, v in por_tipo.items()}
        tipo, s = max(puntaje.items(), key=lambda kv: kv[1])
        r.similitud_aprobados, r.tipo_similitud = round(s, 3), tipo
        if r.estado != "APROBADO":
            continue
        # Alineamiento y Uso de suelo comparten formato municipal: la similitud de texto
        # solo decide cuando las frases clave no dieron un margen claro.
        if tipo != r.tipo_detectado and r.margen_tipo >= 2 * U["margen_tipo"]:
            pass  # las frases clave son concluyentes; la similitud queda en el reporte
        elif tipo != r.tipo_detectado:
            r.estado = "REVISION_MANUAL"
            r.motivo = (f"Las frases clave dicen {C.TIPOS[r.tipo_detectado]['nombre']} pero se parece más a "
                        f"{C.TIPOS[tipo]['nombre']}.")
            r.mensaje = r.motivo
        elif s < U["min_similitud"]:
            r.estado = "REVISION_MANUAL"
            r.motivo = "Es del tipo correcto pero se parece poco a los documentos aprobados."
            r.mensaje = r.motivo


# ==========================================================================
# Salida
# ==========================================================================

def carpeta_destino(salida: Path, r: Resultado) -> Path:
    if r.estado == "APROBADO":
        return salida / "APROBADO" / C.TIPOS[r.tipo_detectado]["nombre"]
    if r.estado == "REVISION_MANUAL":
        return salida / "REVISION_MANUAL"
    return salida / "VOLVER_A_SUBIR" / r.motivo


def guardar(resultados: list[Resultado], raiz: Path, salida: Path, copiar: bool) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    for r in resultados:
        if copiar:
            d = carpeta_destino(salida, r)
            d.mkdir(parents=True, exist_ok=True)
            origen = raiz / r.archivo
            nombre = origen.name if not (d / origen.name).exists() else f"{origen.parent.name}__{origen.name}"
            shutil.copy2(origen, d / nombre)

    datos = {
        "version_reglas": C.VERSION_REGLAS,
        "fecha": dt.datetime.now().isoformat(timespec="seconds"),
        "umbrales": U,
        "resumen": {e: sum(r.estado == e for r in resultados)
                    for e in ("APROBADO", "REVISION_MANUAL", "VOLVER_A_SUBIR")},
        "documentos": [{k: v for k, v in asdict(r).items() if k != "texto"} for r in resultados],
    }
    (salida / "reporte.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), "utf-8")

    cols = ["archivo", "estado", "motivo", "mensaje", "tipo_declarado", "tipo_detectado",
            "confianza_tipo", "similitud_aprobados", "legibilidad", "confianza_ocr",
            "paginas_total", "observaciones", "sha256"]
    with open(salida / "reporte.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in resultados:
            fila = asdict(r)
            fila["observaciones"] = " | ".join(r.observaciones)
            w.writerow([fila[c] for c in cols])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--sin-copias", action="store_true", help="solo genera el reporte")
    a = ap.parse_args()

    raiz = a.entrada.resolve()
    salida = (a.salida or raiz.parent / f"{raiz.name}_filtrado").resolve()
    dir_cache = salida / ".cache_ocr"
    dir_cache.mkdir(parents=True, exist_ok=True)

    ignorar = {"filtro_calidad", "__pycache__"}
    archivos = [p for p in sorted(raiz.rglob("*"))
                if p.is_file() and p.suffix.lower() not in (".md", ".py", ".txt", ".gitignore")
                and not any(x.startswith(".") or x in ignorar for x in p.relative_to(raiz).parts)
                and salida not in p.parents]
    resultados = []
    for i, ruta in enumerate(archivos, 1):
        r = evaluar(ruta, raiz, dir_cache)
        resultados.append(r)
        print(f"[{i:>3}/{len(archivos)}] {r.estado:<16} {r.archivo}  ({r.motivo[:70]}) {r.segundos}s", flush=True)

    segunda_opinion(resultados)
    guardar(resultados, raiz, salida, copiar=not a.sin_copias)
    res = {e: sum(r.estado == e for r in resultados) for e in ("APROBADO", "REVISION_MANUAL", "VOLVER_A_SUBIR")}
    print(f"\nResumen: {res}\nReporte: {salida / 'reporte.csv'}")


if __name__ == "__main__":
    main()
