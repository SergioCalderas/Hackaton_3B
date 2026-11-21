"""De dónde sale cada documento.

El front ya no sube archivos: los documentos viven en la base de datos (Supabase
Postgres, tablas escrituras / predial / suelo / aliniamiento). Las tablas aún no
tienen columna para el archivo; el nombre se configura con FILTRO_COLUMNA_ARCHIVO
(por omisión "archivo") y el valor puede ser:

  - bytea con el archivo,
  - URL http(s) (p. ej. Supabase Storage, URL firmada),
  - ruta relativa al repo o a public/ (p. ej. "docs/predial/caso-001.pdf", lo que usa hoy el front).

Ver procesamiento/sql/propuesta.sql.
"""
from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]

# tabla en la BD -> tipo del filtro
TABLAS = {
    "escrituras": "escritura",
    "predial": "predial",
    "suelo": "uso_suelo",
    "aliniamiento": "alineamiento",
}
# columna de operacion_realizada -> tabla
COLUMNAS_OPERACION = {
    "escritura_id": "escrituras",
    "predial_id": "predial",
    "suelo_id": "suelo",
    "alineamiento_id": "aliniamiento",
}


class FuenteError(Exception):
    """No se pudo obtener el archivo (no existe, sin archivo, sin conexión...)."""

    def __init__(self, mensaje: str, http: int = 400):
        super().__init__(mensaje)
        self.http = http


@dataclass
class Archivo:
    contenido: bytes
    nombre: str
    tipo: str | None = None      # tipo declarado según la tabla
    tabla: str | None = None
    id: int | None = None


def _columnas() -> list[str]:
    """Columnas donde puede estar el archivo, en orden de preferencia (se usa la primera no vacía).
    El equipo guarda la ruta del bucket en `direccion_memoria`; `archivo` queda como alternativa."""
    cols = [c.strip() for c in os.environ.get("FILTRO_COLUMNA_ARCHIVO", "archivo,direccion_memoria").split(",")]
    if not cols or not all(re.fullmatch(r"[a-z_][a-z0-9_]*", c) for c in cols):
        raise FuenteError("FILTRO_COLUMNA_ARCHIVO no es una lista válida de columnas.", 500)
    return cols


def _expr_archivo(tabla: str):
    """SQL: COALESCE(col1, col2, ...) sobre la tabla (identificadores escapados)."""
    from psycopg import sql
    cols = [sql.Identifier(c) for c in _columnas()]
    return sql.SQL("COALESCE({})").format(sql.SQL(", ").join(cols)) if len(cols) > 1 else cols[0]


def _url_storage(ruta: str) -> str | None:
    """URL pública del objeto en Supabase Storage (bucket FILTRO_BUCKET, por omisión 'documentos')."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        return None
    from urllib.parse import quote
    bucket = os.environ.get("FILTRO_BUCKET", "documentos")
    return f"{base}/storage/v1/object/public/{bucket}/{quote(ruta.lstrip('/'), safe='/')}"


def _conectar():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise FuenteError("Falta DATABASE_URL en el servidor.", 500)
    import psycopg  # import perezoso: la app local de pruebas no lo necesita
    return psycopg.connect(url, connect_timeout=10)


def resolver_valor(valor, nombre_base: str) -> tuple[bytes, str]:
    """Convierte lo guardado en la columna en (bytes, nombre de archivo)."""
    if valor is None:
        raise FuenteError("El registro no tiene archivo asociado.", 404)
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return bytes(valor), f"{nombre_base}.pdf"
    texto = str(valor).strip()
    if re.match(r"^\$2[aby]\$", texto):
        raise FuenteError("La columna tiene un hash, no la ruta del archivo.", 404)
    if texto.startswith(("http://", "https://")):
        return _descargar(texto), Path(texto.split("?")[0]).name or f"{nombre_base}.pdf"
    rel = texto.lstrip("/\\")
    for base in (RAIZ_REPO, RAIZ_REPO / "public"):
        ruta = (base / rel).resolve()
        if ruta.is_file() and RAIZ_REPO in ruta.parents:
            return ruta.read_bytes(), ruta.name
    url = _url_storage(rel)  # ruta dentro del bucket de Supabase Storage
    if url:
        return _descargar(url), Path(rel).name
    raise FuenteError(f"No se encontró el archivo '{texto}'.", 404)


def _descargar(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise FuenteError(f"El almacenamiento respondió {e.code} para el archivo.", 404 if e.code in (400, 404) else 502)
    except Exception as e:
        raise FuenteError(f"No se pudo descargar el archivo: {e.__class__.__name__}", 502)


def desde_bd(tabla: str, id_: int) -> Archivo:
    if tabla not in TABLAS:
        raise FuenteError(f"Tabla no válida: {tabla}. Usa una de {sorted(TABLAS)}.")
    from psycopg import sql
    consulta = sql.SQL("SELECT {} FROM {} WHERE id = %s").format(_expr_archivo(tabla), sql.Identifier(tabla))
    try:
        with _conectar() as conn, conn.cursor() as cur:
            cur.execute(consulta, (id_,))
            fila = cur.fetchone()
    except FuenteError:
        raise
    except Exception as e:
        raise FuenteError(f"No se pudo consultar la base de datos: {e.__class__.__name__}", 503)
    if fila is None:
        raise FuenteError(f"No existe {tabla} con id {id_}.", 404)
    contenido, nombre = resolver_valor(fila[0], f"{tabla}-{id_}")
    return Archivo(contenido, nombre, TABLAS[tabla], tabla, id_)


def ids_de_operacion(operacion_id: int) -> dict[str, int | None]:
    """{tabla: id} de los 4 documentos de una operación."""
    try:
        with _conectar() as conn, conn.cursor() as cur:
            cur.execute("SELECT escritura_id, predial_id, suelo_id, alineamiento_id "
                        "FROM operacion_realizada WHERE id = %s", (operacion_id,))
            fila = cur.fetchone()
    except FuenteError:
        raise
    except Exception as e:
        raise FuenteError(f"No se pudo consultar la base de datos: {e.__class__.__name__}", 503)
    if fila is None:
        raise FuenteError(f"No existe la operación {operacion_id}.", 404)
    return dict(zip(COLUMNAS_OPERACION.values(), fila))


def _consultar_estado(cur, conn) -> tuple[dict, dict]:
    """({tabla: {id: ruta o None}}, {(tabla, id): último resultado del filtro})."""
    from psycopg import sql
    archivos = {}
    for tabla in TABLAS:
        cur.execute(sql.SQL("SELECT id, {} FROM {} ORDER BY id").format(_expr_archivo(tabla), sql.Identifier(tabla)))
        archivos[tabla] = {i: (v if v and not re.match(r"^\$2[aby]\$", str(v)) else None) for i, v in cur.fetchall()}
    guardados = {}
    try:
        cur.execute(
            "SELECT DISTINCT ON (tabla, documento_id) tabla, documento_id, estado, motivo, mensaje, "
            "tipo_detectado, detalle->'calidad'->'observaciones', detalle->'calidad'->'legibilidad', "
            "detalle->'calidad'->'confianza_ocr', detalle->'calidad'->>'tipo_detectado_nombre', "
            "detalle->>'nombre', creado_en, detalle->'extraccion' "
            "FROM filtro_resultados ORDER BY tabla, documento_id, creado_en DESC")
        for t, d, est, mot, msg, tipo, obs, leg, conf, tipo_nom, nombre, en, ext in cur.fetchall():
            guardados[(t, d)] = {"estado": est, "motivo": mot, "mensaje": msg, "tipo_detectado": tipo,
                                 "tipo_detectado_nombre": tipo_nom, "observaciones": obs or [],
                                 "legibilidad": leg, "confianza_ocr": conf, "archivo_verificado": nombre,
                                 "verificado_en": en.isoformat(),
                                 "extraccion": ext}  # Fase 2 (None si se verificó con ?hasta=calidad)
    except Exception:  # la tabla filtro_resultados aún no existe
        conn.rollback()
    return archivos, guardados


def _doc(tabla: str, doc_id, archivos: dict, guardados: dict) -> dict:
    ruta = archivos.get(tabla, {}).get(doc_id)
    filtro = guardados.get((tabla, doc_id))
    # Sin archivo, o con un resultado de otro archivo (la fila cambió), lo guardado ya no aplica
    if filtro and (not ruta or (filtro.get("archivo_verificado")
                                and filtro["archivo_verificado"] != Path(str(ruta)).name)):
        filtro = None
    return {"id": doc_id, "archivo": Path(str(ruta)).name if ruta else None,
            "tiene_archivo": bool(ruta), "filtro": filtro}


def resumen_documentos() -> dict[str, list[dict]]:
    """Todos los documentos de cada tabla con su último resultado del filtro (sin OCR)."""
    try:
        with _conectar() as conn, conn.cursor() as cur:
            archivos, guardados = _consultar_estado(cur, conn)
    except FuenteError:
        raise
    except Exception as e:
        raise FuenteError(f"No se pudo consultar la base de datos: {e.__class__.__name__}", 503)
    return {t: [_doc(t, i, archivos, guardados) for i in ids] for t, ids in archivos.items()}


def resumen_seleccion(ids: dict[str, int | None]) -> dict:
    """Arma un expediente con un documento elegido por tabla ({tabla: id}); las tablas sin id
    quedan como faltantes. Misma forma que una operación, con operacion_id=None."""
    try:
        with _conectar() as conn, conn.cursor() as cur:
            archivos, guardados = _consultar_estado(cur, conn)
    except FuenteError:
        raise
    except Exception as e:
        raise FuenteError(f"No se pudo consultar la base de datos: {e.__class__.__name__}", 503)
    docs = {}
    for tabla in TABLAS:
        i = ids.get(tabla)
        if i is not None and i not in archivos[tabla]:
            raise FuenteError(f"No existe {tabla} con id {i}.", 404)
        docs[tabla] = _doc(tabla, i, archivos, guardados) if i is not None else \
            {"id": None, "archivo": None, "tiene_archivo": False, "filtro": None}
    return {"operacion_id": None, "seleccion": ids, "documentos": docs}


def resumen_operaciones(operacion_id: int | None = None) -> list[dict]:
    """Operaciones con el último resultado guardado del filtro por documento (sin correr OCR)."""
    try:
        with _conectar() as conn, conn.cursor() as cur:
            filtro = "WHERE id = %s" if operacion_id is not None else ""
            cur.execute(f"SELECT id, escritura_id, predial_id, suelo_id, alineamiento_id, latitud, longitud, estado "
                        f"FROM operacion_realizada {filtro} ORDER BY id",
                        (operacion_id,) if operacion_id is not None else None)
            ops = cur.fetchall()
            archivos, guardados = _consultar_estado(cur, conn)
    except FuenteError:
        raise
    except Exception as e:
        raise FuenteError(f"No se pudo consultar la base de datos: {e.__class__.__name__}", 503)

    salida = []
    for op_id, *doc_ids, lat, lng, semaforo in ops:
        docs = {tabla: _doc(tabla, doc_id, archivos, guardados)
                for tabla, doc_id in zip(COLUMNAS_OPERACION.values(), doc_ids)}
        estados = [d["filtro"]["estado"] if d["filtro"] else None for d in docs.values()]
        if all(e == "APROBADO" for e in estados):
            expediente = "EN_REVISION"
        elif all(e is None for e in estados) and all(d["tiene_archivo"] for d in docs.values()):
            expediente = "SIN_VERIFICAR"
        else:
            expediente = "NO_VALIDADO"
        salida.append({"operacion_id": op_id, "latitud": float(lat), "longitud": float(lng),
                       "semaforo": semaforo, "expediente": expediente, "documentos": docs})
    return salida


def guardar_resultado(resultado: dict) -> None:
    """Guarda el resultado en filtro_resultados si FILTRO_GUARDAR_RESULTADOS=1.
    No rompe el flujo si la tabla no existe (solo registra el error)."""
    if os.environ.get("FILTRO_GUARDAR_RESULTADOS") != "1" or not resultado.get("tabla"):
        return
    import json
    try:
        with _conectar() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO filtro_resultados (tabla, documento_id, sha256, estado, motivo, mensaje, "
                "tipo_detectado, detalle, version_reglas) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (resultado["tabla"], resultado["id"], resultado["calidad"].get("sha256"),
                 resultado["calidad"]["estado"], resultado["calidad"]["motivo"],
                 resultado["calidad"]["mensaje"], resultado["calidad"].get("tipo_detectado"),
                 json.dumps(resultado, ensure_ascii=False), resultado.get("version_reglas")))
    except Exception as e:  # noqa: BLE001
        print(f"[procesamiento] No se guardó el resultado: {e}", flush=True)
