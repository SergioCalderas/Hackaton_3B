"""Utilidades del visor: copias servibles de los documentos, miniaturas y HTML de evidencias.

Streamlit sirve la carpeta static/ (junto a app_streamlit.py) en /app/static/. Cada análisis copia
sus documentos a static/expedientes/<id>/ para que "página N" abra el PDF en esa página
(visor PDF del navegador: archivo.pdf#page=N) y muestre una miniatura al pasar el mouse.
"""
from __future__ import annotations

import hashlib
import html
import re
import shutil
from pathlib import Path

import fitz

from .config import RAIZ
from .esquemas import NOMBRE_TIPO

STATIC = RAIZ / "static"
EXPEDIENTES_STATIC = STATIC / "expedientes"
MAX_CORRIDAS = 30

CSS = """
<style>
.ev{position:relative;display:inline-block}
.ev>a{color:inherit;text-decoration:none;border-bottom:1px dotted #7a8699}
.ev>a:hover{color:#1f5fbf;border-bottom-color:#1f5fbf}
.ev .pop{visibility:hidden;opacity:0;position:absolute;z-index:9999;bottom:100%;left:-8px;padding-bottom:6px;
  transition:opacity .12s ease-in-out}
.ev:hover .pop{visibility:visible;opacity:1}
.ev .box{width:270px;background:#fff;color:#222;border:1px solid #d9dde3;border-radius:8px;
  box-shadow:0 6px 18px rgba(0,0,0,.18);padding:8px;font-size:.82rem;line-height:1.3}
.ev .box img{width:100%;border:1px solid #eef0f3;border-radius:4px;display:block}
.ev .box .cita{display:block;color:#555;font-style:italic;margin-top:6px}
.ev .box .abrir{display:block;margin-top:6px;font-weight:600;color:#1f5fbf;text-decoration:none}
.nv{color:#9a6700;font-size:.9em}
.hz{border-left:4px solid #ccc;padding:6px 12px;margin:6px 0;background:#fafbfc;border-radius:0 6px 6px 0}
.hz.no_cumple{border-color:#c62828;background:#fdf3f3}.hz.revisar{border-color:#d08700;background:#fff8ea}
.hz.cumple{border-color:#2e7d32;background:#f3faf3}.hz.informativo{border-color:#5b6b82;background:#f5f7fa}
.hz .t{font-weight:600}.hz .ev-l{color:#4a5566;font-size:.9em;margin-top:2px}
.estado{border-radius:10px;padding:14px 18px;color:#fff;font-size:1.5rem;font-weight:700}
.estado small{display:block;font-size:.85rem;font-weight:400;opacity:.92}
.estado.Cumple{background:#2e7d32}.estado.Requiere{background:#c77700}.estado.No{background:#c62828}
table.campos{width:100%;border-collapse:collapse;font-size:.88rem}
table.campos td,table.campos th{border-bottom:1px solid #e6e9ee;padding:5px 6px;text-align:left;vertical-align:top}
table.campos th{color:#5b6b82;font-weight:600}
.chip{display:inline-block;border-radius:12px;padding:2px 10px;margin:2px;font-size:.85rem}
.chip.ok{background:#e6f4e7;color:#1b5e20}.chip.falta{background:#fde8e8;color:#b71c1c}
.fuente{font-size:.75rem;border-radius:8px;padding:1px 6px;background:#eef2f8;color:#3b4a61}
</style>
"""


def esc(s) -> str:
    """Escapa HTML y '$' (Streamlit interpreta $...$ como LaTeX)."""
    return html.escape("" if s is None else str(s)).replace("$", "&#36;")


def _limpiar_corridas() -> None:
    if not EXPEDIENTES_STATIC.is_dir():
        return
    corridas = sorted((p for p in EXPEDIENTES_STATIC.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    for p in corridas[:-MAX_CORRIDAS]:
        shutil.rmtree(p, ignore_errors=True)


def preparar_corrida(archivos: list[dict]) -> tuple[str, dict[str, str]]:
    """Copia los archivos a static/expedientes/<id>/. Devuelve (id, {nombre: archivo servido})."""
    h = hashlib.sha1()
    for a in archivos:
        h.update(Path(a["ruta"]).read_bytes()[:1_000_000])
        h.update(a["nombre"].encode())
    corrida = h.hexdigest()[:12]
    destino = EXPEDIENTES_STATIC / corrida
    destino.mkdir(parents=True, exist_ok=True)
    mapa = {}
    for i, a in enumerate(archivos):
        seguro = re.sub(r"[^A-Za-z0-9._-]", "_", Path(a["nombre"]).name)
        nombre_static = f"{i:02d}_{seguro}"
        if not (destino / nombre_static).is_file():
            shutil.copyfile(a["ruta"], destino / nombre_static)
        mapa[a["nombre"]] = nombre_static
    (destino).touch()
    _limpiar_corridas()
    return corrida, mapa


class Enlaces:
    """Construye URLs y miniaturas para (documento, página)."""

    def __init__(self, corrida: str, mapa: dict[str, str]):
        self.corrida, self.mapa = corrida, mapa
        self.dir = EXPEDIENTES_STATIC / corrida

    def url(self, documento: str) -> str | None:
        f = self.mapa.get(documento)
        return f"app/static/expedientes/{self.corrida}/{f}" if f else None

    def miniatura(self, documento: str, pagina: int) -> str | None:
        f = self.mapa.get(documento)
        if not f:
            return None
        rel = f"thumbs/{Path(f).stem}_p{pagina}.jpg"
        destino = self.dir / rel
        if not destino.is_file():
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                origen = self.dir / f
                if origen.suffix.lower() == ".pdf":
                    with fitz.open(origen) as doc:
                        pix = doc[pagina - 1].get_pixmap(dpi=48)
                else:
                    pix = fitz.Pixmap(str(origen))
                    if pix.width > 600:
                        pix = fitz.Pixmap(pix, 600, int(pix.height * 600 / pix.width))
                destino.write_bytes(pix.tobytes("jpg", jpg_quality=70))
            except Exception:  # noqa: BLE001 - una miniatura fallida no debe romper el visor
                return None
        return f"app/static/expedientes/{self.corrida}/{rel}"


def enlace_pagina(e: dict, enlaces: Enlaces | None) -> str:
    """'página N' discreto: al pasar el mouse muestra miniatura, cita y acceso directo a la página."""
    n = e.get("pagina")
    etiqueta = f"página {n}"
    url = enlaces.url(e["documento"]) if enlaces else None
    if not url:
        return f"<b>{etiqueta}</b>"
    destino = f"{url}#page={n}"
    mini = enlaces.miniatura(e["documento"], n)
    img = f'<img loading="lazy" src="{mini}" alt="Vista previa de la página {n}"/>' if mini else ""
    cita = f'<span class="cita">“{esc(e.get("cita", "")[:220])}”</span>' if e.get("cita") else ""
    return (f'<span class="ev"><a href="{destino}" target="_blank">{etiqueta}</a><span class="pop"><span class="box">'
            f'{img}{cita}<a class="abrir" href="{destino}" target="_blank">Abrir página {n} ↗</a></span></span></span>')


def _nombre_doc(e: dict) -> str:
    return NOMBRE_TIPO.get(e.get("tipo_documento") or "", Path(e.get("documento", "")).name)


def frase_evidencias(evidencias: list[dict], enlaces: Enlaces | None, maximo: int = 5) -> str:
    """'Como se visualiza en la página 1 de Escritura y la página 2 de Predial.'"""
    vistas, ok = set(), []
    for e in evidencias:
        clave = (e.get("documento"), e.get("pagina"))
        if e.get("verificada") and e.get("pagina") and clave not in vistas:
            vistas.add(clave)
            ok.append(e)
    if not ok:
        return '<span class="nv">Evidencia no localizada en el texto del documento.</span>' if evidencias else ""
    partes = [f"la {enlace_pagina(e, enlaces)} de <b>{esc(_nombre_doc(e))}</b>" for e in ok[:maximo]]
    texto = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
    extra = f" (y {len(ok) - maximo} más)" if len(ok) > maximo else ""
    return f"Como se visualiza en {texto}{extra}."


def grafo_dot() -> str:
    """Diagrama de agentes (LangGraph) en DOT para st.graphviz_chart."""
    from .grafo import grafo

    g = grafo().get_graph(xray=True)
    lineas = ['digraph G { rankdir=TB; node [shape=box, style="rounded,filled", fillcolor="#eef2f8", '
              'fontname="Helvetica", fontsize=11]; edge [color="#7a8699"];']
    for nid, nodo in g.nodes.items():
        nombre = nid.split(":")[-1]
        color = "#fde9c8" if nombre.startswith("extractor") else "#dff0e0" if nombre in (
            "validador_cruzado", "dictaminador") else "#e3e9f6"
        forma = ', shape=ellipse, fillcolor="#ffffff"' if nombre in ("__start__", "__end__") else f', fillcolor="{color}"'
        etiqueta = {"__start__": "inicio", "__end__": "fin"}.get(nombre, nombre)
        lineas.append(f'"{nid}" [label="{etiqueta}"{forma}];')
    for e in g.edges:
        estilo = ' [style=dashed]' if e.conditional else ""
        lineas.append(f'"{e.source}" -> "{e.target}"{estilo};')
    lineas.append("}")
    return "\n".join(lineas)
