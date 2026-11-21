import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

import bcrypt
import psycopg
from dotenv import load_dotenv
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

app = Flask(__name__)

# Pipeline de documentos (Fase 1: filtro de calidad). Ver procesamiento/api.py y CLAUDE.md.
import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from procesamiento.api import bp as procesamiento_bp  # noqa: E402

    app.register_blueprint(procesamiento_bp)
except ImportError as e:  # faltan dependencias del OCR: el login sigue funcionando
    print(f"[server] Pipeline de documentos deshabilitado: {e}", flush=True)

# Análisis multiagente con LLM (analisis/, LLM_PROVIDER=local|online). Ver README_ANALISIS.md.
try:
    from procesamiento.api_analisis import bp as analisis_bp  # noqa: E402

    app.register_blueprint(analisis_bp)
except ImportError as e:
    print(f"[server] Análisis con LLM deshabilitado: {e}", flush=True)


def role_name(tipo_usuario):
    return "admin" if tipo_usuario == 1 else "gestor"


def find_user(correo):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Falta DATABASE_URL")
    with psycopg.connect(database_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, apellidos, correo, contrasena, tipo_usuario
                FROM usuarios
                WHERE lower(correo) = %s
                """,
                (correo,),
            )
            return cur.fetchone()


def public_user(row):
    user_id, nombre, apellidos, email, _stored_hash, tipo_usuario = row
    return {
        "id": user_id,
        "name": f"{nombre} {apellidos}".strip(),
        "email": email,
        "role": role_name(tipo_usuario),
    }


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    correo = str(data.get("correo") or "").strip().lower()
    contrasena = str(data.get("contrasena") or "")
    if not correo or not contrasena:
        return jsonify(error="Correo y contraseña son obligatorios."), 400

    try:
        row = find_user(correo)
    except RuntimeError:
        return jsonify(error="Falta DATABASE_URL en el servidor."), 500
    except psycopg.Error:
        app.logger.exception("No se pudo consultar usuarios")
        return jsonify(error="No se pudo consultar la base de datos."), 503

    if row is None:
        return jsonify(error="Correo o contraseña incorrectos."), 401

    _user_id, _nombre, _apellidos, _email, stored_hash, _tipo_usuario = row
    try:
        password_ok = bcrypt.checkpw(contrasena.encode(), stored_hash.encode())
    except (ValueError, TypeError):
        password_ok = False
    if not password_ok:
        return jsonify(error="Correo o contraseña incorrectos."), 401

    return jsonify(user=public_user(row))


@app.post("/api/login/google")
def login_google():
    data = request.get_json(silent=True) or {}
    credential = str(data.get("credential") or "")
    nonce = str(data.get("nonce") or "")
    if not credential:
        return jsonify(error="Falta el token de Google."), 400

    client_id = os.environ.get("VITE_GOOGLE_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID") or ""
    if not client_id:
        return jsonify(error="Falta el ID de cliente de Google en el servidor."), 500

    try:
        url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(credential)
        with urllib.request.urlopen(url, timeout=10) as resp:
            info = json.loads(resp.read().decode())
    except Exception:
        return jsonify(error="No se pudo verificar la cuenta de Google."), 401

    if info.get("aud") != client_id:
        return jsonify(error="Token para otra aplicacion."), 401
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return jsonify(error="Emisor no valido."), 401
    if str(info.get("email_verified")).lower() not in ("true", "1"):
        return jsonify(error="Correo de Google no verificado."), 401
    if nonce and info.get("nonce") != nonce:
        return jsonify(error="Token no valido (nonce)."), 401

    correo = str(info.get("email") or "").strip().lower()
    try:
        row = find_user(correo)
    except RuntimeError:
        return jsonify(error="Falta DATABASE_URL en el servidor."), 500
    except psycopg.Error:
        app.logger.exception("No se pudo consultar usuarios")
        return jsonify(error="No se pudo consultar la base de datos."), 503

    if row is None:
        return jsonify(error="Tu cuenta de Google no tiene acceso a este sistema."), 401

    return jsonify(user=public_user(row))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
