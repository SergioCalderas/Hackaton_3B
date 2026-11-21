"""Regenera los JSON para el LLM a partir de los .json/.txt existentes (sin repetir OCR):

  output/documentos.json   un objeto por documento (texto, páginas, campos extraídos, ExpedienteId)
  output/expedientes.json  un objeto por inmueble (campos consolidados, coincidencias, faltantes)
  output/expedientes.xlsx  hojas expedientes / campos / sin_match / revisar

  python export_json.py
  python export_json.py --sin-matching          # solo documentos.json (ExpedienteId = null)
  python export_json.py --umbral 0.8 --umbral-revisar 0.6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ocr_pipeline.config import PROJECT_ROOT
from ocr_pipeline.export import export_documents_json, exportar_todo
from ocr_pipeline.matching import MatchConfig


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "output", help="Carpeta de salida del pipeline")
    p.add_argument("--sin-matching", action="store_true", help="Solo documentos.json, sin agrupar expedientes")
    p.add_argument("--umbral", type=float, default=0.75, help="Puntaje mínimo para agrupar automáticamente")
    p.add_argument("--umbral-revisar", type=float, default=0.55, help="Puntaje mínimo para la hoja 'revisar'")
    args = p.parse_args(argv)
    if not args.output.is_dir():
        print(f"No existe {args.output}. Corre primero run_ocr.py", file=sys.stderr)
        return 2
    if args.sin_matching:
        path, n = export_documents_json(args.output)
        print(f"{n} documentos -> {path}")
        return 0
    r = exportar_todo(args.output, MatchConfig(auto_threshold=args.umbral, review_threshold=args.umbral_revisar))
    print(f"documentos={r['documentos']} expedientes={r['expedientes']} completos={r['completos']} "
          f"revisar={r['revisar']} sin_match={r['sin_match']}")
    for f in r["archivos"]:
        print("  ->", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
