// Sección "Texto extraído del documento" de la vista del caso (DocModal).
// Datos: GET /api/texto?ruta=<pdf del caso> (procesamiento/texto.py). Primero se consulta solo la caché
// (instantáneo); si el documento aún no tiene texto, el botón "Verificar" lo extrae con OCR.
import React, { useEffect, useMemo, useRef, useState } from 'react';

const EXTRACTO = 1800;          // caracteres visibles antes de "Ver todo"
const CALIDAD_BAJA = 0.65;      // mismo umbral que low_confidence en ocr_pipeline

async function pedirTexto(ruta, tipo, soloCache, signal) {
  const q = new URLSearchParams({ ruta, ...(tipo ? { tipo } : {}), ...(soloCache ? { solo_cache: '1' } : {}) });
  let r;
  try {
    r = await fetch(`/api/texto?${q}`, { headers: { Accept: 'application/json' }, signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new Error('No se pudo conectar con el servidor del pipeline.');
  }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(datos.error || (r.status >= 500
      ? 'El servidor del pipeline no responde (¿está corriendo python server/app.py?).'
      : `Error ${r.status}`));
  }
  return datos;
}

const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Divide el texto en trozos y marca los valores de los campos extraídos (igual que /demo).
function resaltar(texto, campos) {
  const valores = Object.entries(campos || {})
    .map(([campo, c]) => ({ campo, valor: String(c.valor || '').trim() }))
    .filter((v) => v.valor.length >= 2)
    .sort((a, b) => b.valor.length - a.valor.length);
  if (!valores.length || !texto) return [texto];
  const patrones = valores.map((v) => ({ ...v, re: new RegExp(escRe(v.valor).replace(/\s+/g, '\\s+'), 'i') }));
  const todos = new RegExp(patrones.map((p) => `(?:${p.re.source})`).join('|'), 'gi');
  const out = [];
  let ultimo = 0;
  for (const m of texto.matchAll(todos)) {
    if (!m[0]) continue;
    if (m.index > ultimo) out.push(texto.slice(ultimo, m.index));
    const campo = (patrones.find((p) => p.re.test(m[0])) || {}).campo;
    out.push(<mark key={m.index} className="tx-mark" title={campo}>{m[0]}</mark>);
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) out.push(texto.slice(ultimo));
  return out;
}

function Cronometro() {
  const [s, setS] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const iv = setInterval(() => setS((Date.now() - t0) / 1000), 100);
    return () => clearInterval(iv);
  }, []);
  return <strong>{s.toFixed(1)} s</strong>;
}

export default function TextoExtraido({ ruta, tipo }) {
  const [estado, setEstado] = useState(ruta ? 'cargando' : 'sin-archivo'); // cargando | extrayendo | vacio | ok | error | sin-archivo
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [pagina, setPagina] = useState(0);
  const [verTodo, setVerTodo] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const abortRef = useRef(null);

  const cargar = async (soloCache) => {
    if (!ruta) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setEstado(soloCache ? 'cargando' : 'extrayendo');
    setError(null);
    try {
      const d = await pedirTexto(ruta, tipo, soloCache, ctrl.signal);
      if (d.estado === 'SIN_EXTRAER') { setEstado('vacio'); return; }
      setDatos(d);
      setPagina(0);
      setVerTodo(false);
      setEstado('ok');
    } catch (e) {
      if (e.name === 'AbortError') return;
      setError(e.message);
      setEstado('error');
    }
  };

  useEffect(() => {
    setDatos(null);
    if (ruta) cargar(true); else setEstado('sin-archivo');
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruta, tipo]);

  const paginas = datos?.paginas || [];
  const actual = paginas[pagina] || { texto: '' };
  const largo = actual.texto.length > EXTRACTO;
  const visible = verTodo || !largo ? actual.texto : `${actual.texto.slice(0, EXTRACTO).trimEnd()} …`;
  const trozos = useMemo(() => resaltar(visible, datos?.campos), [visible, datos]);
  const calidadBaja = datos && (datos.calidad_texto == null || datos.calidad_texto < CALIDAD_BAJA);

  const copiar = async () => {
    const todo = paginas.map((p) => `— Página ${p.numero} de ${paginas.length} —\n${p.texto}`).join('\n\n');
    try { await navigator.clipboard.writeText(todo); }
    catch (_) {
      const ta = Object.assign(document.createElement('textarea'), { value: todo });
      document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
    }
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1500);
  };

  const irA = (i) => { setPagina(i); setVerTodo(false); };

  return (
    <section className="texto-ext">
      <div className="row between">
        <h4>Texto extraído del documento</h4>
        {estado === 'ok' && paginas.some((p) => p.texto) && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={copiar}>{copiado ? 'Copiado ✓' : 'Copiar texto'}</button>
        )}
      </div>

      {estado === 'ok' && (
        <p className="tiny tx-meta">
          Motor: <strong>{datos.motores.join(', ') || '—'}</strong>
          {' · '}Calidad del texto: <strong>{datos.calidad_texto == null ? '—' : `${Math.round(datos.calidad_texto * 100)} %`}</strong>
          {' · '}{datos.num_paginas} {datos.num_paginas === 1 ? 'página' : 'páginas'}
          {datos.origen === 'ocr' ? ` · extraído en ${datos.segundos} s` : ''}
        </p>
      )}

      {(estado === 'cargando' || estado === 'extrayendo') && (
        <div className="tx-estado">
          <span className="tx-spinner" aria-hidden="true" />
          <span className="small">
            {estado === 'cargando' ? 'Buscando el texto…' : <>Extrayendo el texto con OCR… <Cronometro /> <span className="muted">(los documentos largos pueden tardar un par de minutos)</span></>}
          </span>
        </div>
      )}

      {estado === 'sin-archivo' && (
        <p className="tx-vacio small muted">Este documento no tiene archivo cargado, así que no hay texto que mostrar.</p>
      )}

      {estado === 'vacio' && (
        <div className="tx-vacio row between wrap">
          <span className="small">Aún no se ha extraído el texto; presiona <strong>Verificar</strong>.</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => cargar(false)}>Verificar</button>
        </div>
      )}

      {estado === 'error' && (
        <div className="notice notice-red row between wrap">
          <span className="small"><strong>No se pudo obtener el texto.</strong> {error}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => cargar(true)}>Reintentar</button>
        </div>
      )}

      {estado === 'ok' && (
        <>
          {calidadBaja && (
            <p className="notice notice-amber small tx-aviso">
              El texto puede contener errores de lectura (calidad {datos.calidad_texto == null ? 'desconocida' : `${Math.round(datos.calidad_texto * 100)} %`}).
            </p>
          )}

          {paginas.length > 1 && (
            <div className="tx-paginas">
              <button type="button" className="btn btn-ghost btn-sm" disabled={pagina === 0} onClick={() => irA(pagina - 1)} aria-label="Página anterior">‹</button>
              <select value={pagina} onChange={(e) => irA(Number(e.target.value))} aria-label="Página">
                {paginas.map((p, i) => (
                  <option key={p.numero} value={i}>Página {p.numero} de {paginas.length}</option>
                ))}
              </select>
              <button type="button" className="btn btn-ghost btn-sm" disabled={pagina === paginas.length - 1} onClick={() => irA(pagina + 1)} aria-label="Página siguiente">›</button>
              <span className="tiny muted">
                {actual.metodo === 'native' ? 'texto nativo' : actual.motor || actual.metodo}
                {actual.calidad != null ? ` · calidad ${Math.round(actual.calidad * 100)} %` : ''}
              </span>
            </div>
          )}

          <div className="tx-caja" tabIndex={0} aria-label={`Texto de la página ${actual.numero || 1}`}>
            {actual.texto ? trozos : <span className="muted">(Esta página no tiene texto legible.)</span>}
          </div>

          <div className="row between tx-pie">
            <span className="tiny muted">
              {Object.keys(datos.campos || {}).length > 0 && <><mark className="tx-mark">resaltado</mark> = campos extraídos · </>}
              {largo && !verTodo ? `${EXTRACTO.toLocaleString('es-MX')} de ${actual.texto.length.toLocaleString('es-MX')} caracteres` : `${actual.texto.length.toLocaleString('es-MX')} caracteres`}
            </span>
            {largo && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setVerTodo((v) => !v)}>{verTodo ? 'Ver menos' : 'Ver todo'}</button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
