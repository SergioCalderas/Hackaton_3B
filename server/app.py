import os
from pathlib import Path

import bcrypt
import psycopg
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = Flask(__name__)


def role_name(tipo_usuario):
    return "admin" if tipo_usuario == 1 else "gestor"


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    correo = str(data.get("correo") or "").strip().lower()
    contrasena = str(data.get("contrasena") or "")
    if not correo or not contrasena:
        return jsonify(error="Correo y contraseña son obligatorios."), 400

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return jsonify(error="Falta DATABASE_URL en el servidor."), 500

    try:
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
                row = cur.fetchone()
    except psycopg.Error:
        app.logger.exception("No se pudo consultar usuarios")
        return jsonify(error="No se pudo consultar la base de datos."), 503

    if row is None:
        return jsonify(error="Correo o contraseña incorrectos."), 401

    user_id, nombre, apellidos, email, stored_hash, tipo_usuario = row
    try:
        password_ok = bcrypt.checkpw(contrasena.encode(), stored_hash.encode())
    except (ValueError, TypeError):
        password_ok = False
    if not password_ok:
        return jsonify(error="Correo o contraseña incorrectos."), 401

    return jsonify(
        user={
            "id": user_id,
            "name": f"{nombre} {apellidos}".strip(),
            "email": email,
            "role": role_name(tipo_usuario),
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
