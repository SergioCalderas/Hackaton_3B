"""Benchmark de punta a punta: OCR + extracción LLM + validación cruzada + dictamen.

    .venv\\Scripts\\python benchmark_analisis.py                       # todos los ejemplos, OCR en frío
    .venv\\Scripts\\python benchmark_analisis.py -e "Sintético B"      # uno (coincidencia por prefijo)
    .venv\\Scripts\\python benchmark_analisis.py --con-cache           # reutiliza OCR (mide solo el LLM)
    .venv\\Scripts\\python benchmark_analisis.py --archivos Escritura/x.pdf:Escritura Predial/y.pdf:Predial

Guarda cada resultado en output/analisis/<expediente>.json. El proveedor sale de LLM_PROVIDER (.env).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from analisis import ejemplos
from analisis.config import RAIZ, Ajustes, ConfiguracionError
from analisis.grafo import analizar_expediente
from analisis.llm import precalentar


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-e", "--expediente", action="append", help="Nombre (o prefijo) de un expediente de ejemplo")
    p.add_argument("--archivos", nargs="+", help="ruta[:Tipo] de un expediente propio")
    p.add_argument("--con-cache", action="store_true", help="Reutiliza el OCR ya hecho")
    p.add_argument("--fecha-referencia", help="AAAA-MM-DD (por defecto hoy o FECHA_REFERENCIA)")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    try:
        cambios = {"ocr_cache": args.con_cache}
        if args.fecha_referencia:
            from datetime import date
            cambios["fecha_referencia"] = date.fromisoformat(args.fecha_referencia)
        aj = Ajustes.desde_entorno(**cambios)
        print(f"LLM: {aj.proveedor} · {aj.modelo} | OCR: {aj.ocr_idioma} {aj.ocr_dpi} DPI, {aj.hilos_ocr} hilos | "
              f"referencia {aj.fecha_referencia} | caché OCR: {'sí' if aj.ocr_cache else 'no'}")
        print(f"Precarga del modelo (no cuenta): {precalentar(aj)} s\n")
    except ConfiguracionError as e:
        print(f"Error de configuración: {e}", file=sys.stderr)
        return 2

    if args.archivos:
        trabajos = {"personalizado": {"archivos": [{"ruta": a.split(":")[0], "nombre": Path(a.split(":")[0]).name,
                                                    "tipo": (a.split(":")[1] if ":" in a else None)}
                                                   for a in args.archivos], "esperado": None}}
    else:
        nombres = [n for n in ejemplos.disponibles()
                   if not args.expediente or any(n.startswith(x) for x in args.expediente)]
        trabajos = {n: {"archivos": ejemplos.rutas(n), "esperado": ejemplos.EXPEDIENTES[n]["esperado"]} for n in nombres}

    salida = RAIZ / "output" / "analisis"
    salida.mkdir(parents=True, exist_ok=True)
    filas, fallos = [], 0
    for nombre, t in trabajos.items():
        res = analizar_expediente(t["archivos"], aj)
        ti = res["tiempos"]
        ok_estado = t["esperado"] in (None, res["estado"])
        ok_tiempo = ti["total_s"] <= aj.tiempo_objetivo_s
        fallos += (not ok_estado) + (not ok_tiempo)
        filas.append((nombre[:46], t["esperado"] or "—", res["estado"], "✓" if ok_estado else "✗", ti["total_s"],
                      "✓" if ok_tiempo else "✗", ti["ocr_max_s"], ti["llm_extraccion_max_s"], ti["dictamen_s"],
                      int(ti["paginas"])))
        archivo = salida / f"{res['expediente_id']}.json"
        archivo.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"· {nombre}: {res['estado']} en {ti['total_s']:.1f} s → {archivo.relative_to(RAIZ)}")
        print(f"  {res['resumen']}")

    enc = ("Expediente", "Esperado", "Obtenido", "", "Total s", "<60", "OCR máx", "LLM máx", "Dictamen", "Págs")
    anchos = [max(len(str(f[i])) for f in [enc, *filas]) for i in range(len(enc))]
    print("\n" + " | ".join(str(c).ljust(a) for c, a in zip(enc, anchos)))
    print("-+-".join("-" * a for a in anchos))
    for f in filas:
        print(" | ".join((f"{c:.1f}" if isinstance(c, float) else str(c)).ljust(a) for c, a in zip(f, anchos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
