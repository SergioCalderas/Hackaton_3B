// Filtro de documentos: lo que hay en la BD (Supabase Storage), su resultado de calidad,
// sus observaciones y el dictamen (última etapa, LLM) para un expediente armado a mano.
import React, { useCallback, useEffect, useState } from 'react';
import { Card } from '../components/ui.jsx';
import { FiltroPill } from '../lib/filtro.jsx';
import { fmtDate } from '../lib/selectors.js';

const TABLAS = [
  ['escrituras', 'Escrituras'],
  ['predial', 'Predial'],
  ['aliniamiento', 'Alineamiento y Núm. Oficial'],
  ['suelo', 'Uso de suelo'],
];
const SEV_LABEL = { CRITICA: 'Crítica', ALTA: 'Alta', MEDIA: 'Media', BAJA: 'Baja' };
const SEMAFORO_TONE = { VERDE: 'green', AMARILLO: 'amber', ROJO: 'red', GRIS: 'gray' };

async function pedir(url, opts) {
  const r = await fetch(url, { headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, ...opts });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.error || `Error ${r.status}`);
  return datos;
}

export function Observaciones({ items }) {
  if (!items || items.length === 0) return <p className="muted tiny">Sin observaciones.</p>;
  return (
    <ul className="obs-lista">
      {items.map((o) => (
        <li key={o.id} className={`obs obs-${o.severidad}`}>
          <span className="obs-sev">{SEV_LABEL[o.severidad]}</span>
          <span>
            {o.texto}
            <span className="tiny"> · {o.codigo}{o.regla ? ` · ${o.regla}` : ''}{o.bloquea ? ' · bloquea' : ''}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Dictamen({ d }) {
  const r = d.redaccion;
  const tone = SEMAFORO_TONE[d.semaforo];
  return (
    <div className="stack-col">
      <p className={`notice notice-${tone === 'gray' ? 'amber' : tone}`} style={{ marginTop: 0 }}>
        <span className={`pill pill-${tone}`}>{d.semaforo_texto}</span>{' '}
        <strong>{d.razon_semaforo}</strong>
        <br /><span className="tiny">El color lo decide el motor de reglas; el LLM solo redacta la justificación.</span>
      </p>
      <div>
        <h4 style={{ marginTop: 0 }}>Justificación</h4>
        <p>{r.resumen}</p>
        {r.puntos.length > 0 && (
          <ul className="dict-puntos">
            {r.puntos.map((p, i) => (
              <li key={i}>
                {p.texto}
                <span className="tiny"> {p.observaciones_citadas.length ? `[${p.observaciones_citadas.join(', ')}]` : '[sin evidencia]'}</span>
              </li>
            ))}
          </ul>
        )}
        {r.acciones_sugeridas.length > 0 && (
          <>
            <h4>Acciones sugeridas</h4>
            <ul className="dict-puntos">{r.acciones_sugeridas.map((a) => <li key={a}>{a}</li>)}</ul>
          </>
        )}
        <p className="tiny">
          {r.origen === 'llm' ? `Redactado por ${r.modelo}` : 'Redactado por plantilla'}
          {r.nota ? ` · ${r.nota}` : ''} · {d.version}
        </p>
      </div>
      <details>
        <summary className="small">Ver lo que se envía al LLM ({d.entrada_llm.observaciones.length} observaciones)</summary>
        <pre className="json-box">{JSON.stringify(d.entrada_llm, null, 2)}</pre>
      </details>
    </div>
  );
}

export default function Filtro() {
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState(null);
  const [corriendo, setCorriendo] = useState({});
  const [sel, setSel] = useState({});
  const [dict, setDict] = useState(null);
  const [dictCargando, setDictCargando] = useState(false);

  const cargar = useCallback(async () => {
    try { setDocs(await pedir('/api/documentos')); setError(null); } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  const verificar = async (tabla, id) => {
    const k = `${tabla}-${id}`;
    setCorriendo((c) => ({ ...c, [k]: true }));
    try {
      await pedir(`/api/documentos/${tabla}/${id}/verificar?hasta=calidad`, { method: 'POST' });
      await cargar();
    } catch (e) { setError(e.message); }
    finally { setCorriendo((c) => ({ ...c, [k]: false })); }
  };

  const generar = async () => {
    setDictCargando(true);
    try { setDict(await pedir('/api/dictamen', { method: 'POST', body: JSON.stringify(sel) })); setError(null); }
    catch (e) { setError(e.message); }
    finally { setDictCargando(false); }
  };

  const elegidos = TABLAS.filter(([t]) => sel[t] != null).length;

  return (
    <div className="stack-col">
      <div>
        <h1>Filtro de documentos</h1>
        <p className="muted">Documentos en la base de datos, resultado del filtro de calidad (Fase 1), sus observaciones y el dictamen preliminar.</p>
      </div>
      {error && <p className="notice notice-red">{error}</p>}

      <Card
        title={`Dictamen preliminar · ${elegidos} de 4 documentos elegidos`}
        action={<button className="btn btn-red btn-sm" onClick={generar} disabled={dictCargando}>{dictCargando ? 'Generando…' : 'Generar dictamen'}</button>}
      >
        <p className="muted small" style={{ marginTop: 0 }}>
          Elige un documento de cada tipo con “Usar en dictamen”. Las observaciones de los elegidos se mandan a la última etapa (LLM).
          Los tipos sin documento cuentan como faltantes.
        </p>
        {dict && <Dictamen d={dict} />}
      </Card>

      {!docs ? <p className="muted">{error ? '' : 'Cargando documentos…'}</p> : (
        <div className="filtro-grid">
          {TABLAS.map(([tabla, label]) => (
            <Card key={tabla} title={`${label} (${docs[tabla].length})`}>
              <div className="filtro-docs">
                {docs[tabla].map((d) => {
                  const k = `${tabla}-${d.id}`;
                  const elegido = sel[tabla] === d.id;
                  return (
                    <div key={d.id} className={`filtro-doc-item ${elegido ? 'elegido' : ''}`}>
                      <div className="row between">
                        <strong className="small">#{d.id} · {d.archivo || 'sin archivo'}</strong>
                        <FiltroPill estado={d.estado} />
                      </div>
                      {d.filtro && <p className="tiny" style={{ margin: '4px 0' }}>{d.filtro.mensaje} · {fmtDate(d.filtro.verificado_en)}</p>}
                      <Observaciones items={d.observaciones.filter((o) => o.codigo !== 'SIN-VERIFICAR')} />
                      <div className="row" style={{ marginTop: 8 }}>
                        <button className="btn btn-ghost btn-sm" disabled={!d.tiene_archivo || corriendo[k]} onClick={() => verificar(tabla, d.id)}>
                          {corriendo[k] ? 'Verificando…' : d.filtro ? 'Volver a verificar' : 'Verificar'}
                        </button>
                        <button className={`btn btn-sm ${elegido ? 'btn-green' : 'btn-light'}`}
                          onClick={() => setSel((s) => ({ ...s, [tabla]: elegido ? null : d.id }))}>
                          {elegido ? '✓ En dictamen' : 'Usar en dictamen'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
