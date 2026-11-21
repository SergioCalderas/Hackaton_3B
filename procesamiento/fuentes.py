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


def _columna() -> str:
    col = os.environ.get("FILTRO_COLUMNA_ARCHIVO", "archivo")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", col):
        raise FuenteError("FILTRO_COLUMNA_ARCHIVO no es un nombre de columna válido.", 500)
    return col


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
    if texto.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(texto, timeout=60) as r:
                return r.read(), Path(texto.split("?")[0]).name or f"{nombre_base}.pdf"
        except Exception as e:
            raise FuenteError(f"No se pudo descargar el archivo: {e}", 502)
    rel = texto.lstrip("/\\")
    for base in (RAIZ_REPO, RAIZ_REPO / "public"):
        ruta = (base / rel).resolve()
        if ruta.is_file() and RAIZ_REPO in ruta.parents:
            return ruta.read_bytes(), ruta.name
    raise FuenteError(f"No se encontró el archivo '{texto}'.", 404)


def desde_bd(tabla: str, id_: int) -> Archivo:
    if tabla not in TABLAS:
        raise FuenteError(f"Tabla no válida: {tabla}. Usa una de {sorted(TABLAS)}.")
    from psycopg import sql
    consulta = sql.SQL("SELECT {} FROM {} WHERE id = %s").format(
        sql.Identifier(_columna()), sql.Identifier(tabla))
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


def resumen_operaciones(operacion_id: int | None = None) -> list[dict]:
    """Operaciones con el último resultado guardado del filtro por documento (sin correr OCR)."""
    col = _columna()
    from psycopg import sql
    try:
        with _conectar() as conn, conn.cursor() as cur:
            filtro = "WHERE id = %s" if operacion_id is not None else ""
            cur.execute(f"SELECT id, escritura_id, predial_id, suelo_id, alineamiento_id, latitud, longitud, estado "
                        f"FROM operacion_realizada {filtro} ORDER BY id",
                        (operacion_id,) if operacion_id is not None else None)
            ops = cur.fetchall()
            con_archivo = {}
            for tabla in TABLAS:
                cur.execute(sql.SQL("SELECT id, {} IS NOT NULL FROM {}").format(sql.Identifier(col), sql.Identifier(tabla)))
                con_archivo[tabla] = dict(cur.fetchall())
            guardados = {}
            try:
                cur.execute(
                    "SELECT DISTINCT ON (tabla, documento_id) tabla, documento_id, estado, motivo, mensaje, "
                    "tipo_detectado, detalle->'calidad'->'observaciones', detalle->'calidad'->'legibilidad', "
                    "detalle->'calidad'->'confianza_ocr', detalle->'calidad'->>'tipo_detectado_nombre', creado_en "
                    "FROM filtro_resultados ORDER BY tabla, documento_id, creado_en DESC")
                for t, d, est, mot, msg, tipo, obs, leg, conf, tipo_nom, en in cur.fetchall():
                    guardados[(t, d)] = {"estado": est, "motivo": mot, "mensaje": msg, "tipo_detectado": tipo,
                                         "tipo_detectado_nombre": tipo_nom, "observaciones": obs or [],
                                         "legibilidad": leg, "confianza_ocr": conf,
                                         "verificado_en": en.isoformat()}
            except Exception:  # la tabla filtro_resultados aún no existe
                conn.rollback()
    except FuenteError:
        raise
    except Exception as e:
        raise FuenteError(f"No se pudo consultar la base de datos: {e.__class__.__name__}", 503)

    salida = []
    for op_id, *doc_ids, lat, lng, semaforo in ops:
        docs = {}
        for tabla, doc_id in zip(COLUMNAS_OPERACION.values(), doc_ids):
            docs[tabla] = {"id": doc_id, "tiene_archivo": bool(con_archivo[tabla].get(doc_id)),
                           "filtro": guardados.get((tabla, doc_id))}
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
