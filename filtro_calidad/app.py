"""App local para probar el filtro de calidad.

  python filtro_calidad/app.py              -> http://127.0.0.1:8000
  python filtro_calidad/app.py --red        -> accesible desde otras PCs de la misma red

Subes uno o varios archivos, eliges el tipo declarado (o "detectar") y la app
muestra el estado (APROBADO / REVISION_MANUAL / VOLVER_A_SUBIR), el motivo,
el mensaje para el usuario, observaciones y métricas por página.
Los archivos se guardan en filtro_calidad/_subidas/ (ignorado por git).
"""
from __future__ import annotations

import argparse
import base64
import sys
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

import pymupdf
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import filtro as F  # noqa: E402

BASE = Path(__file__).resolve().parent / "_subidas"
CACHE = BASE / ".cache_ocr"
CACHE.mkdir(parents=True, exist_ok=True)
CARPETA = {"escritura": "Escritura", "predial": "Predial",
           "alineamiento": "Alineamiento_y_Numero_Oficial", "uso_suelo": "Uso_de_suelo",
           "auto": "_sin_tipo"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
historial: list[dict] = []
candado = threading.Lock()  # el motor OCR no es thread-safe


def miniatura(ruta: Path) -> str | None:
    try:
        doc = F.abrir(ruta)
        pg = doc[0]
        zoom = 260 / max(pg.rect.width, pg.rect.height)
        png = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")
        doc.close()
        return "data:image/png;base64," + base64.b64encode(png).decode()
    except Exception:
        return None


@app.post("/api/verificar")
def verificar():
    tipo = request.form.get("tipo", "auto")
    if tipo not in CARPETA:
        tipo = "auto"
    salida = []
    for f in request.files.getlist("archivos"):
        if not f.filename:
            continue
        nombre = Path(f.filename).name
        destino = BASE / CARPETA[tipo] / f"{uuid.uuid4().hex[:8]}_{nombre}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        f.save(destino)
        with candado:
            r = F.evaluar(destino, BASE, CACHE)
        d = {k: v for k, v in asdict(r).items() if k != "texto"}
        d["archivo"] = nombre
        d["tipo_declarado_nombre"] = C.TIPOS[r.tipo_declarado]["nombre"] if r.tipo_declarado else "Detectar"
        d["tipo_detectado_nombre"] = C.TIPOS[r.tipo_detectado]["nombre"] if r.tipo_detectado else "—"
        d["miniatura"] = miniatura(destino)
        d["id"] = uuid.uuid4().hex[:8]
        historial.insert(0, d)
        salida.append(d)
    return jsonify(salida)


@app.get("/api/historial")
def ver_historial():
    return jsonify(historial)


@app.post("/api/limpiar")
def limpiar():
    historial.clear()
    return jsonify(ok=True)


@app.get("/")
def inicio():
    return PAGINA


PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Filtro de documentos · Hackathon 3B</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1d2330;--mu:#667085;--bd:#e3e6eb;--ok:#127a3e;--okb:#e5f5ec;
--rv:#9a6700;--rvb:#fff5d6;--ko:#b42318;--kob:#fde8e6;--ac:#2f5bd3}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--tx)}
main{max-width:1100px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mu);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px}
.subir{display:grid;grid-template-columns:1fr 240px;gap:16px;align-items:stretch}
@media(max-width:720px){.subir{grid-template-columns:1fr}}
#zona{border:2px dashed #b9c0cc;border-radius:10px;padding:28px;text-align:center;cursor:pointer;color:var(--mu);transition:.15s}
#zona.sobre{border-color:var(--ac);background:#eef2fd;color:var(--ac)}
#zona b{color:var(--tx)}
label{font-weight:600;display:block;margin-bottom:6px}
select,button{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--bd);width:100%}
button{background:var(--ac);color:#fff;border:0;font-weight:600;cursor:pointer;margin-top:10px}
button.sec{background:#fff;color:var(--tx);border:1px solid var(--bd)}
button:disabled{opacity:.5;cursor:wait}
.exp{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.chip{flex:1 1 200px;border:1px solid var(--bd);border-radius:10px;padding:10px 12px;background:#fff}
.chip small{display:block;color:var(--mu)}.chip.ok{border-color:#9fd9b6;background:var(--okb)}
.res{display:grid;grid-template-columns:130px 1fr;gap:14px;margin-top:12px}
@media(max-width:560px){.res{grid-template-columns:1fr}}
.res img{width:130px;border:1px solid var(--bd);border-radius:6px;background:#fff}
.est{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:12px;letter-spacing:.3px}
.APROBADO{background:var(--okb);color:var(--ok)}.REVISION_MANUAL{background:var(--rvb);color:var(--rv)}
.VOLVER_A_SUBIR{background:var(--kob);color:var(--ko)}
.nom{font-weight:600;word-break:break-all;margin-left:6px}
.msg{margin:8px 0;padding:8px 10px;border-radius:8px;background:#f2f4f7}
.kv{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--mu);font-size:13px}.kv b{color:var(--tx)}
ul.obs{margin:6px 0 0;padding-left:18px;color:#475467}
details{margin-top:8px}summary{cursor:pointer;color:var(--ac)}
.tbl{overflow-x:auto}table{border-collapse:collapse;font-size:12.5px;margin-top:6px}
td,th{border-bottom:1px solid var(--bd);padding:4px 8px;text-align:left;white-space:nowrap}
.cargando{color:var(--mu);padding:10px 0}.vacio{color:var(--mu);text-align:center;padding:24px}
.fila{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:22px}
.fila h2{font-size:16px;margin:0}.fila button{width:auto;margin:0}
</style></head><body><main>
<h1>Filtro de documentos · Fase 1</h1>
<p class="sub">Sube Escrituras, Predial, Alineamiento y Número Oficial o Uso de Suelo (PDF, JPG o PNG). El filtro revisa formato, legibilidad y tipo antes de extraer información. Todo corre en esta computadora.</p>

<div class="card subir">
  <div id="zona"><b>Arrastra archivos aquí</b><br>o haz clic para elegirlos<br><small id="sel"></small>
    <input id="arch" type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff,.webp,.bmp,application/pdf,image/*"></div>
  <div>
    <label for="tipo">Tipo declarado</label>
    <select id="tipo">
      <option value="auto">Detectar automáticamente</option>
      <option value="escritura">Escritura</option>
      <option value="predial">Predial</option>
      <option value="alineamiento">Alineamiento y Número Oficial</option>
      <option value="uso_suelo">Uso de Suelo</option>
    </select>
    <button id="btn" disabled>Verificar</button>
    <small style="color:var(--mu);display:block;margin-top:8px">Si eliges un tipo y subes otro documento, se marca como <i>tipo incorrecto</i>.</small>
  </div>
</div>

<div class="exp" id="exp"></div>

<div class="fila"><h2>Resultados</h2><button class="sec" id="limpiar">Limpiar</button></div>
<div id="estado"></div>
<div id="lista"></div>
</main>
<script>
const $=s=>document.querySelector(s), zona=$('#zona'), inp=$('#arch'), btn=$('#btn');
const TIPOS={escritura:'Escritura',predial:'Predial',alineamiento:'Alineamiento y Número Oficial',uso_suelo:'Uso de Suelo'};
let archivos=[];
zona.onclick=()=>inp.click();
inp.onchange=()=>elegir([...inp.files]);
['dragenter','dragover'].forEach(e=>zona.addEventListener(e,ev=>{ev.preventDefault();zona.classList.add('sobre')}));
['dragleave','drop'].forEach(e=>zona.addEventListener(e,ev=>{ev.preventDefault();zona.classList.remove('sobre')}));
zona.addEventListener('drop',ev=>elegir([...ev.dataTransfer.files]));
function elegir(f){archivos=f;$('#sel').textContent=f.length?f.length+' archivo(s): '+f.map(x=>x.name).join(', '):'';btn.disabled=!f.length}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
btn.onclick=async()=>{
  btn.disabled=true;$('#estado').innerHTML='<div class="cargando">Verificando '+archivos.length+' archivo(s)… (OCR local, ~10 s por documento)</div>';
  const fd=new FormData();fd.append('tipo',$('#tipo').value);archivos.forEach(f=>fd.append('archivos',f));
  try{const r=await fetch('/api/verificar',{method:'POST',body:fd});if(!r.ok)throw new Error(r.status);await cargar()}
  catch(e){$('#estado').innerHTML='<div class="msg" style="background:var(--kob)">Error al verificar: '+esc(e.message)+'</div>';return}
  finally{btn.disabled=false}
  $('#estado').innerHTML='';elegir([]);inp.value='';
};
$('#limpiar').onclick=async()=>{await fetch('/api/limpiar',{method:'POST'});cargar()};
async function cargar(){
  const h=await (await fetch('/api/historial')).json();
  const ok=new Set(h.filter(d=>d.estado==='APROBADO').map(d=>d.tipo_detectado));
  $('#exp').innerHTML=Object.entries(TIPOS).map(([k,n])=>`<div class="chip ${ok.has(k)?'ok':''}"><small>${ok.has(k)?'Aprobado':'Pendiente'}</small>${n}</div>`).join('')
    +`<div class="chip ${ok.size===4?'ok':''}"><small>Expediente</small>${ok.size} de 4 · ${ok.size===4?'En revisión':'No validado'}</div>`;
  $('#lista').innerHTML=h.length?h.map(tarjeta).join(''):'<div class="card vacio">Aún no hay archivos verificados.</div>';
}
function tarjeta(d){
  const pags=(d.paginas_revisadas||[]).map(p=>`<tr><td>${p.numero}</td><td>${p.estado}</td><td>${p.origen}</td><td>${p.chars_leidos}</td><td>${(+p.confianza).toFixed(2)}</td><td>${Math.round(p.laplaciano)}</td><td>${p.dpi_imagen||'—'}</td><td>${p.foto?'sí':'no'}</td></tr>`).join('');
  const pts=Object.entries(d.puntajes||{}).map(([k,v])=>`${TIPOS[k]}: <b>${v}</b>`).join(' · ');
  return `<div class="card res">
   ${d.miniatura?`<img src="${d.miniatura}" alt="">`:'<div></div>'}
   <div><span class="est ${d.estado}">${d.estado.replaceAll('_',' ')}</span><span class="nom">${esc(d.archivo)}</span>
    <div class="msg">${esc(d.mensaje)}</div>
    <div class="kv"><span>Declarado: <b>${esc(d.tipo_declarado_nombre)}</b></span><span>Detectado: <b>${esc(d.tipo_detectado_nombre)}</b></span>
     <span>Legibilidad: <b>${Math.round(d.legibilidad*100)}%</b></span><span>Confianza OCR: <b>${(+d.confianza_ocr).toFixed(2)}</b></span>
     <span>Páginas: <b>${d.paginas_total}</b></span><span>${d.segundos}s</span></div>
    ${d.observaciones?.length?`<ul class="obs">${d.observaciones.map(o=>`<li>${esc(o)}</li>`).join('')}</ul>`:''}
    <details><summary>Detalle técnico</summary>
     <div class="kv" style="margin-top:6px">${pts||'Sin puntajes'}</div>
     ${d.evidencia_tipo?.length?`<div class="kv">Frases encontradas: ${esc(d.evidencia_tipo.join(', '))}</div>`:''}
     ${pags?`<div class="tbl"><table><tr><th>Pág.</th><th>Estado</th><th>Origen</th><th>Caract.</th><th>Conf.</th><th>Nitidez</th><th>dpi</th><th>Foto</th></tr>${pags}</table></div>`:''}
     <div class="kv">SHA-256: ${esc(d.sha256)}</div>
    </details></div></div>`;
}
cargar();
</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--red", action="store_true", help="escuchar en 0.0.0.0 (otras PCs de la red)")
    a = ap.parse_args()
    print("Cargando modelo OCR…", flush=True)
    F.motor_ocr()
    host = "0.0.0.0" if a.red else "127.0.0.1"
    print(f"Listo: http://127.0.0.1:{a.puerto}", flush=True)
    app.run(host=host, port=a.puerto, threaded=True)
