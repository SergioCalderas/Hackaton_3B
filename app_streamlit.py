"""Visor de pruebas del análisis de expedientes (Streamlit).

    .venv\\Scripts\\streamlit run app_streamlit.py

Permite analizar los expedientes de ejemplo del reto o subir documentos, ver el estado, los
hallazgos con su evidencia ("Como se visualiza en la página N", con vista previa al pasar el mouse),
los datos extraídos por cada agente, los tiempos por etapa y correr las pruebas de tiempo (< 60 s).
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from analisis import ejemplos
from analisis.config import Ajustes, ConfiguracionError
from analisis.esquemas import NOMBRE_TIPO, TIPOS
from analisis.llm import estado_ollama, precalentar
from analisis.visor import CSS, Enlaces, esc, frase_evidencias, grafo_dot, preparar_corrida

st.set_page_config(page_title="Análisis de expedientes de inmuebles", page_icon="🏢", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

ETAPA = {"ocr": "🔤 OCR", "clasificacion": "🏷️ Clasificador", "extraccion": "🤖 Extractor", "validacion": "🧮 Validador cruzado",
         "dictamen": "⚖️ Dictaminador", "carga_modelo": "⏳ Cargando el modelo en la GPU (no cuenta en el tiempo)"}
ICONO = {"no_cumple": "❌", "revisar": "⚠️", "cumple": "✅", "informativo": "ℹ️"}


# ---------------------------------------------------------------------------------------
# Barra lateral: configuración
# ---------------------------------------------------------------------------------------
def barra_lateral() -> Ajustes | None:
    st.sidebar.header("⚙️ Configuración")
    try:
        base = Ajustes.desde_entorno()
    except ConfiguracionError as e:
        st.sidebar.error(str(e))
        return None
    opciones = {"local": "Local · Ollama", "online": "Online · API de Claude"}
    proveedor = st.sidebar.radio("Proveedor del LLM (LLM_PROVIDER)", list(opciones), format_func=opciones.get,
                                 index=0 if base.es_local else 1)
    cambios: dict = {"proveedor": proveedor}
    if proveedor == "local":
        cambios["ollama_modelo"] = st.sidebar.text_input("Modelo (OLLAMA_MODEL)", base.ollama_modelo)
        aj_tmp = base.con(**cambios)
        est = estado_ollama(aj_tmp)
        if not est["servidor"]:
            st.sidebar.error(f"Ollama no responde en {base.ollama_url}")
        elif not est["modelo_instalado"]:
            st.sidebar.error(f"Falta el modelo: `ollama pull {aj_tmp.ollama_modelo}`")
        else:
            st.sidebar.success("Modelo cargado en GPU" + (f" ({est['vram_gb']} GB)" if est["vram_gb"] else "")
                               if est["modelo_cargado"] else "Modelo instalado (sin cargar)")
            if not est["modelo_cargado"] and st.sidebar.button("Precargar modelo (~15 s)"):
                with st.spinner("Cargando modelo en la GPU…"):
                    st.sidebar.info(f"Cargado en {precalentar(aj_tmp)} s")
    else:
        cambios["claude_modelo"] = st.sidebar.text_input("Modelo (CLAUDE_MODEL)", base.claude_modelo)
        if not base.anthropic_api_key:
            clave = st.sidebar.text_input("ANTHROPIC_API_KEY (solo esta sesión)", type="password")
            if clave:
                cambios["anthropic_api_key"] = clave.strip()
        st.sidebar.warning("En modo online el texto OCR de los documentos se envía a la API de Anthropic. "
                           "Las bases del reto piden no subir los documentos a otros servicios: confírmalo con "
                           "el comité antes de usarlo con documentos del reto.")
    with st.sidebar.expander("OCR y reglas de negocio"):
        cambios["ocr_dpi"] = st.select_slider("DPI del OCR", [200, 250, 300], value=base.ocr_dpi)
        cambios["ocr_idioma"] = st.selectbox("Modelo de idioma", ["spa_fast", "spa"],
                                             index=0 if base.ocr_idioma == "spa_fast" else 1,
                                             help="spa_fast es ~3x más rápido que spa (best) con calidad similar")
        cambios["ocr_cache"] = st.checkbox("Reutilizar OCR de archivos ya procesados", base.ocr_cache)
        cambios["fecha_referencia"] = st.date_input("Fecha de referencia (vigencias y predial)", base.fecha_referencia)
        cambios["uso_requerido"] = st.text_area("Uso requerido", base.uso_requerido, height=70)
        cambios["superficie_tolerancia"] = st.slider("Tolerancia de superficie", 0.0, 0.2, base.superficie_tolerancia,
                                                     0.01, format="%.2f")
        cambios["predial_tolerancia_anios"] = st.number_input("Años de atraso tolerados en predial", 0, 5,
                                                              base.predial_tolerancia_anios)
        cambios["dictamen_llm"] = st.selectbox("Dictamen con LLM", ["auto", "si", "no"],
                                               index=["auto", "si", "no"].index(base.dictamen_llm),
                                               help="auto: lo omite si no alcanza el tiempo objetivo")
    try:
        aj = base.con(**cambios)
        aj.validar()
        return aj
    except ConfiguracionError as e:
        st.sidebar.error(str(e))
        return None


# ---------------------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------------------
def ejecutar(archivos: list[dict], aj: Ajustes) -> dict | None:
    from analisis.grafo import analizar_expediente

    corrida, mapa = preparar_corrida(archivos)
    t0 = time.perf_counter()
    with st.status("Analizando expediente…", expanded=True) as estado:
        def progreso(e: dict) -> None:
            s = f"{e.get('s', 0):.1f} s"
            nombre = Path(e["archivo"]).name if e.get("archivo") else ""
            if e["etapa"] == "ocr":
                extra = f"{e['paginas']} pág. · calidad {e['calidad'] or 0:.0%}" + (" · caché" if e.get("cache") else "")
            elif e["etapa"] == "clasificacion":
                extra = f"{NOMBRE_TIPO.get(e.get('tipo') or '', 'sin tipo')} ({e['metodo']})"
            elif e["etapa"] == "extraccion":
                extra = f"{e['campos']} campos" + (f" · ⚠️ {e['error']}" if e.get("error") else "")
            elif e["etapa"] == "validacion":
                extra = f"{e['hallazgos']} hallazgos"
            elif e["etapa"] == "carga_modelo":
                st.write(f"**{ETAPA['carga_modelo']}**…")
                return
            else:
                extra = f"redactado por {e.get('por')} · {e.get('estado')}"
            st.write(f"**{ETAPA[e['etapa']]}** · {esc(nombre)} · {extra} · `{s}` · t={time.perf_counter() - t0:.1f} s")

        try:
            res = analizar_expediente(archivos, aj, progreso)
        except Exception as e:  # noqa: BLE001
            estado.update(label=f"Error: {e}", state="error")
            st.exception(e)
            return None
        total = res["tiempos"]["total_s"]
        ok = total <= aj.tiempo_objetivo_s
        estado.update(label=f"Análisis completo en {total:.1f} s {'✅' if ok else '⚠️ (supera ' + str(int(aj.tiempo_objetivo_s)) + ' s)'}",
                      state="complete", expanded=False)
    return {"resultado": res, "corrida": corrida, "mapa": mapa}


# ---------------------------------------------------------------------------------------
# Presentación del resultado
# ---------------------------------------------------------------------------------------
def tarjeta_estado(res: dict) -> str:
    clase = res["estado"].split()[0]
    sub = f"Recomendación inicial · confianza {res['nivel_confianza']} ({res['confianza']:.0%})"
    return f'<div class="estado {clase}">{esc(res["estado"])}<small>{esc(sub)}</small></div>'


def bloque_hallazgo(h: dict, enlaces: Enlaces) -> str:
    ev = frase_evidencias(h["evidencias"], enlaces)
    critico = " · <b>crítico</b>" if h["severidad"] == "critica" else ""
    return (f'<div class="hz {h["resultado"]}"><div class="t">{ICONO[h["resultado"]]} {esc(h["regla"])}{critico}</div>'
            f'<div>{esc(h["descripcion"])}</div>' + (f'<div class="ev-l">{ev}</div>' if ev else "") + "</div>")


def tabla_campos(doc: dict, enlaces: Enlaces) -> str:
    filas = []
    for c in doc["campos"].values():
        v = c["valor"]
        valor = "; ".join(map(str, v)) if isinstance(v, list) else (f"{v:,.2f}" if isinstance(v, float) else v)
        fuente = {"llm": "LLM", "reglas": "Reglas", "llm+reglas": "LLM + reglas ✓"}[c["fuente"]]
        if c["coincide_reglas"] is False:
            fuente = f"LLM (reglas: {esc(c['valor_reglas'])})"
        ev = c.get("evidencia")
        celda_ev = frase_evidencias([ev], enlaces).replace("Como se visualiza en ", "").rstrip(".") if ev else "—"
        filas.append(f"<tr><td>{esc(c['etiqueta'])}</td><td>{esc(valor)}</td><td><span class='fuente'>{fuente}</span>"
                     f"</td><td>{celda_ev}</td></tr>")
    return ("<table class='campos'><tr><th>Dato</th><th>Valor</th><th>Agente</th><th>Evidencia</th></tr>"
            + "".join(filas) + "</table>")


def mostrar_resultado(r: dict, aj: Ajustes) -> None:
    res = r["resultado"]
    enlaces = Enlaces(r["corrida"], r["mapa"])
    t = res["tiempos"]
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    c1.markdown(tarjeta_estado(res), unsafe_allow_html=True)
    c2.metric("Tiempo total", f"{t['total_s']:.1f} s", "dentro de 60 s" if t["total_s"] <= aj.tiempo_objetivo_s
              else "excede 60 s", delta_color="normal" if t["total_s"] <= aj.tiempo_objetivo_s else "inverse")
    c3.metric("Documentos", f"{len(res['documentos_recibidos'])} / 4", f"{int(t['paginas'])} páginas",
              delta_color="off")
    c4.metric("Modelo", res["modelo_llm"], res["proveedor_llm"], delta_color="off")

    st.subheader("Dictamen")
    st.write(res["resumen"])
    for o in res["observaciones"]:
        st.markdown(f"- {esc(o)}", unsafe_allow_html=True)
    nota = f"Redactado por el agente {'LLM' if res['dictamen_por'] == 'llm' else 'de reglas'}. "
    if res["estado_llm"] and res["estado_llm"] != res["estado_reglas"]:
        nota += f"Reglas: {res['estado_reglas']} · LLM sugirió: {res['estado_llm']} (el LLM solo puede escalar el estado). "
    nota += f"Fecha de referencia: {res['fecha_referencia']}. Uso requerido: {res['uso_requerido']}."
    st.caption(nota)

    chips = "".join(f'<span class="chip ok">✓ {esc(d)}</span>' for d in res["documentos_recibidos"])
    chips += "".join(f'<span class="chip falta">✗ Falta: {esc(d)}</span>' for d in res["documentos_faltantes"])
    st.markdown(f"<div>{chips}</div>", unsafe_allow_html=True)

    tabs = st.tabs(["Hallazgos y evidencia", "Requisitos", "Datos extraídos", "Tiempos", "JSON"])
    with tabs[0]:
        grupos = [("no_cumple", "Incumplimientos"), ("revisar", "Requiere revisión"), ("cumple", "Validaciones que cumplen"),
                  ("informativo", "Informativos")]
        for clave, titulo in grupos:
            hs = [h for h in res["hallazgos"] if h["resultado"] == clave]
            if hs:
                st.markdown(f"**{ICONO[clave]} {titulo} ({len(hs)})**")
                st.markdown("".join(bloque_hallazgo(h, enlaces) for h in hs), unsafe_allow_html=True)
    with tabs[1]:
        a, b = st.columns(2)
        a.markdown("**✅ Requisitos cumplidos**")
        for x in res["requisitos_cumplidos"]:
            a.markdown(f"- {esc(x)}", unsafe_allow_html=True)
        b.markdown("**❌ / ⚠️ Requisitos no cumplidos o por revisar**")
        for x in res["requisitos_no_cumplidos"]:
            b.markdown(f"- {esc(x)}", unsafe_allow_html=True)
        st.caption("Factores de confianza: " + ", ".join(f"{k.replace('_', ' ')} {v:.0%}"
                                                          for k, v in res["factores_confianza"].items()))
    with tabs[2]:
        docs = res["documentos"]
        if docs:
            sub = st.tabs([f"{NOMBRE_TIPO.get(d['tipo'] or '', 'Sin tipo')} · {Path(d['nombre_archivo']).name[:28]}"
                           for d in docs])
            for s, d in zip(sub, docs):
                with s:
                    st.caption(f"{d['ruta_archivo']} · {d['num_paginas']} pág. · calidad OCR "
                               f"{(d['calidad_texto'] or 0):.0%} · estado OCR {d['estado_ocr']} · páginas enviadas al "
                               f"LLM: {d['paginas_enviadas_llm']}" + (f" · ⚠️ {d['error_llm']}" if d["error_llm"] else ""))
                    st.markdown(tabla_campos(d, enlaces), unsafe_allow_html=True)
    with tabs[3]:
        df = pd.DataFrame([{"documento": Path(d["nombre_archivo"]).name[:30], "OCR (s)": d["tiempos"].get("ocr_s", 0),
                            "LLM (s)": d["tiempos"].get("llm_s", 0)} for d in res["documentos"]]).set_index("documento")
        st.bar_chart(df, horizontal=True, stack=False)
        st.dataframe(pd.DataFrame([t]).T.rename(columns={0: "segundos"}), width="stretch")
        st.caption("El OCR y el LLM corren en paralelo entre documentos: el tiempo del LLM de cada documento incluye "
                   "la espera en la cola de Ollama. Con OLLAMA_NUM_PARALLEL=4 las extracciones corren simultáneas.")
    with tabs[4]:
        st.download_button("Descargar JSON", json.dumps(res, ensure_ascii=False, indent=2),
                           file_name=f"{res['expediente_id']}.json", mime="application/json")
        st.json(res, expanded=False)


# ---------------------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------------------
def pestana_analizar(aj: Ajustes) -> None:
    fuente = st.radio("Documentos", ["Ejemplos del reto", "Subir archivos"], horizontal=True)
    archivos: list[dict] = []
    if fuente == "Ejemplos del reto":
        nombre = st.selectbox("Expediente", ejemplos.disponibles())
        info = ejemplos.EXPEDIENTES[nombre]
        st.caption(f"{info['nota']}" + (f" · Estado esperado: **{info['esperado']}**" if info["esperado"] else ""))
        archivos = ejemplos.rutas(nombre)
        st.caption(" · ".join(f"{NOMBRE_TIPO[a['tipo']]}: `{Path(a['nombre']).name}`" for a in archivos))
    else:
        subidos = st.file_uploader("PDF o imágenes del expediente (un inmueble)", accept_multiple_files=True,
                                   type=["pdf", "jpg", "jpeg", "png", "tif", "tiff"])
        if subidos:
            carpeta = Path(tempfile.gettempdir()) / "expedientes_3b"
            carpeta.mkdir(exist_ok=True)
            cols = st.columns(min(4, len(subidos)))
            for i, up in enumerate(subidos):
                destino = carpeta / f"{i:02d}_{Path(up.name).name}"
                destino.write_bytes(up.getbuffer())
                tipo = cols[i % len(cols)].selectbox(up.name[:40], ["Detectar"] + list(TIPOS), key=f"tipo_{i}",
                                                     format_func=lambda t: NOMBRE_TIPO.get(t, "Detectar automáticamente"))
                archivos.append({"ruta": str(destino), "nombre": up.name, "tipo": None if tipo == "Detectar" else tipo})
    if st.button("Analizar expediente", type="primary", disabled=not archivos):
        r = ejecutar(archivos, aj)
        if r:
            st.session_state["ultimo"] = r
    if "ultimo" in st.session_state:
        mostrar_resultado(st.session_state["ultimo"], aj)


def pestana_pruebas(aj: Ajustes) -> None:
    from analisis.grafo import analizar_expediente

    st.write("Corre expedientes completos (OCR + extracción + validación + dictamen) y verifica el estado esperado "
             f"y el objetivo de **{aj.tiempo_objetivo_s:.0f} s** por expediente.")
    seleccion = st.multiselect("Expedientes", ejemplos.disponibles(), default=ejemplos.disponibles()[:4])
    frio = st.checkbox("OCR en frío (sin caché)", value=True)
    if st.button("Ejecutar pruebas", type="primary", disabled=not seleccion):
        aj_prueba = aj.con(ocr_cache=not frio)
        if aj.es_local:
            with st.spinner("Precargando el modelo (no cuenta en el tiempo del expediente)…"):
                st.caption(f"Precarga del modelo: {precalentar(aj_prueba)} s")
        filas, barra = [], st.progress(0.0)
        for i, nombre in enumerate(seleccion):
            with st.spinner(f"{nombre}…"):
                res = analizar_expediente(ejemplos.rutas(nombre), aj_prueba)
            t, esperado = res["tiempos"], ejemplos.EXPEDIENTES[nombre]["esperado"]
            filas.append({"Expediente": nombre, "Esperado": esperado or "—", "Obtenido": res["estado"],
                          "Estado OK": "✅" if esperado in (None, res["estado"]) else "❌",
                          "Total (s)": t["total_s"], "< 60 s": "✅" if t["total_s"] <= aj.tiempo_objetivo_s else "❌",
                          "OCR máx (s)": t["ocr_max_s"], "LLM máx (s)": t["llm_extraccion_max_s"],
                          "Dictamen (s)": t["dictamen_s"], "Páginas": int(t["paginas"]), "Confianza": res["confianza"]})
            barra.progress((i + 1) / len(seleccion))
            st.session_state["pruebas"] = filas
    if st.session_state.get("pruebas"):
        st.dataframe(pd.DataFrame(st.session_state["pruebas"]), width="stretch", hide_index=True)


def pestana_arquitectura() -> None:
    st.write("Grafo multiagente en **LangGraph**: cada documento recorre su propio subgrafo en paralelo "
             "(OCR en CPU, extracción en GPU), después un validador cruzado determinista y un dictaminador.")
    st.graphviz_chart(grafo_dot(), width="stretch")
    st.markdown("""
| Agente | Qué hace | Tecnología |
|---|---|---|
| `agente_ocr` | Texto de cada página (nativo del PDF o Tesseract en paralelo con todos los núcleos) y campos por reglas (regex) | Tesseract `spa_fast`, PyMuPDF, `ocr_pipeline` |
| `agente_clasificador` | Tipo de documento por palabras clave; LLM si no es concluyente | reglas + LLM |
| `extractor_*` (4) | Extracción especializada por tipo con salida estructurada; evidencia localizada en el texto y doble verificación contra las reglas | LangChain `with_structured_output` |
| `validador_cruzado` | Completitud, legibilidad, mismo inmueble, dirección, propietario, superficie, número oficial, uso de suelo, vigencias, predial, afectaciones | reglas deterministas |
| `dictaminador` | Redacta el dictamen y puede escalar el estado (nunca relajarlo) | LLM |
""")


def main() -> None:
    st.title("🏢 Análisis de expedientes de inmuebles")
    st.caption("Sistema multiagente (LangChain + LangGraph) · OCR Tesseract · validación cruzada con evidencia")
    aj = barra_lateral()
    tabs = st.tabs(["🔎 Analizar", "⏱️ Pruebas de tiempo", "🧩 Arquitectura"])
    with tabs[2]:
        pestana_arquitectura()
    if aj is None:
        for t in tabs[:2]:
            t.warning("Corrige la configuración en la barra lateral.")
        return
    with tabs[0]:
        pestana_analizar(aj)
    with tabs[1]:
        pestana_pruebas(aj)


main()
