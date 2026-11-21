// Tarjeta "Análisis con IA" de la vista del caso.
// Datos: POST /api/analisis/caso con los PDFs del caso (procesamiento/api_analisis.py -> analisis/):
// filtro de calidad (Fase 1) + OCR paralelo + agentes extractores (LLM) + validación cruzada + dictamen.
// Cada hallazgo cita su evidencia: "Como se visualiza en la página N de <documento>"; al pasar el mouse
// por "página N" aparece la vista previa de la página y un acceso directo que abre el PDF en esa página.
import React, { useEffect, useRef, useState } from 'react';
import { Card } from './ui.jsx';
import { DOC_TYPES } from '../lib/seed.js';

const TONO = { VERDE: 'green', AMARILLO: 'amber', ROJO: 'red', GRIS: 'gray' };
const ICONO = { no_cumple: '✗', revisar: '!', cumple: '✓', informativo: 'i' };
const GRUPOS = [
  ['no_cumple', 'Incumplimientos', true],
  ['revisar', 'Requiere revisión', true],
  ['cumple', 'Validaciones que cumplen', false],
  ['informativo', 'Informativos', false],
];
const ETIQUETA_TIPO = Object.fromEntries(DOC_TYPES.map((t) => [t.key, t.label]));
const cacheKey = (caseId) => `analisis-ia:${caseId}`;

// "/docs/numero_oficial/caso-001.pdf" -> "Número oficial"
const nombreDoc = (ruta) => ETIQUETA_TIPO[(ruta || '').split('/')[2]] || (ruta || '').split('/').pop();

async function pedirAnalisis(documentos, forzar) {
  let r;
  try {
    r = await fetch('/api/analisis/caso', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ documentos, forzar }),
    });
  } catch {
    throw new Error('No se pudo conectar con el servidor (¿está corriendo python server/app.py?).');
  }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(datos.error || (r.status === 404
      ? 'El servidor no tiene el análisis con IA (faltan dependencias: pip install -r server/requirements.txt).'
      : `Error ${r.status}`));
  }
  return datos;
}

function EnlacePagina({ e }) {
  const destino = `${e.documento}#page=${e.pagina}`;
  const mini = `/api/analisis/miniatura?${new URLSearchParams({ ruta: e.documento, pagina: e.pagina })}`;
  return (
    <span className="ev">
      <a href={destino} target="_blank" rel="noreferrer">página {e.pagina}</a>
      <span className="ev-pop">
        <span className="ev-box">
          <img loading="lazy" src={mini} alt={`Vista previa de la página ${e.pagina}`} />
          {e.cita && <span className="ev-cita">“{e.cita.slice(0, 220)}”</span>}
          <a className="ev-abrir" href={destino} target="_blank" rel="noreferrer">Abrir página {e.pagina} ↗</a>
        </span>
      </span>
    </span>
  );
}

function Evidencias({ evidencias }) {
  const vistas = new Set();
  const ok = (evidencias || []).filter((e) => {
    const k = `${e.documento}|${e.pagina}`;
    if (!e.verificada || !e.pagina || vistas.has(k)) return false;
    vistas.add(k);
    return true;
  });
  if (!ok.length) {
    return evidencias && evidencias.length
      ? <span className="ia-nv">Evidencia no localizada en el texto del documento.</span> : null;
  }
  return (
    <span>
      Como se visualiza en{' '}
      {ok.slice(0, 5).map((e, i) => (
        <React.Fragment key={`${e.documento}-${e.pagina}`}>
          {i > 0 && (i === Math.min(ok.length, 5) - 1 ? ' y ' : ', ')}
          la <EnlacePagina e={e} /> de <strong>{nombreDoc(e.documento)}</strong>
        </React.Fragment>
      ))}
      {ok.length > 5 ? ` (y ${ok.length - 5} más)` : ''}.
    </span>
  );
}

function Hallazgo({ h }) {
  return (
    <li className={`ia-h ia-${h.resultado}`}>
      <span className="ia-icono">{ICONO[h.resultado]}</span>
      <div>
        <strong>{h.regla}</strong>{h.severidad === 'critica' && <span className="pill pill-red ia-crit">crítico</span>}
        <p>{h.descripcion}</p>
        <p className="tiny muted"><Evidencias evidencias={h.evidencias} /></p>
      </div>
    </li>
  );
}

function DatosExtraidos({ documentos }) {
  return (
    <details className="ia-datos">
      <summary>Datos extraídos por los agentes ({documentos.length} documentos)</summary>
      {documentos.map((d) => (
        <div key={d.ruta_archivo} className="ia-doc">
          <strong>{nombreDoc(d.ruta_archivo)}</strong>
          <span className="muted tiny">
            {' '}· {d.num_paginas} pág. · calidad OCR {Math.round((d.calidad_texto || 0) * 100)} %
            {d.calidad && ` · filtro: ${d.calidad.estado}`}{d.error_llm && ` · ${d.error_llm}`}
          </span>
          <table className="ia-tabla">
            <tbody>
              {Object.values(d.campos).map((c) => (
                <tr key={c.campo}>
                  <td>{c.etiqueta}</td>
                  <td>{Array.isArray(c.valor) ? c.valor.join('; ') : String(c.valor)}</td>
                  <td className="tiny muted">{{ llm: 'LLM', reglas: 'Reglas', 'llm+reglas': 'LLM + reglas ✓' }[c.fuente]}</td>
                  <td className="tiny">{c.evidencia ? <Evidencias evidencias={[c.evidencia]} /> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </details>
  );
}

export default function AnalisisIA({ caseId, docs }) {
  const documentos = docs.filter((d) => d.pdf && d.completitud === 100).map((d) => ({ ruta: d.pdf, tipo: d.type }));
  const [res, setRes] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(cacheKey(caseId))); } catch { return null; }
  });
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const [seg, setSeg] = useState(0);
  const reloj = useRef(null);

  useEffect(() => () => clearInterval(reloj.current), []);

  const analizar = async (forzar = false) => {
    setCargando(true); setError(null); setSeg(0);
    const t0 = Date.now();
    reloj.current = setInterval(() => setSeg(Math.round((Date.now() - t0) / 1000)), 500);
    try {
      const r = await pedirAnalisis(documentos, forzar);
      setRes(r);
      try { sessionStorage.setItem(cacheKey(caseId), JSON.stringify(r)); } catch { /* sin espacio */ }
    } catch (e) {
      setError(e.message);
    } finally {
      clearInterval(reloj.current);
      setCargando(false);
    }
  };

  const accion = (
    <button className="btn btn-yellow btn-sm" disabled={cargando || !documentos.length} onClick={() => analizar(!!res)}>
      {cargando ? `Analizando… ${seg} s` : res ? 'Volver a analizar' : 'Analizar con IA'}
    </button>
  );

  return (
    <Card title="Análisis con IA · dictamen del expediente" action={accion}>
      {!res && !cargando && !error && (
        <p className="muted small">
          Revisa los {documentos.length} documentos del caso: filtro de calidad, extracción con agentes de IA,
          validación cruzada (dirección, titular, superficie, número oficial, clave), uso de suelo, vigencias y
          predial. Tarda menos de 1 minuto; cada hallazgo enlaza a la página del documento donde se ve.
        </p>
      )}
      {cargando && <p className="notice notice-amber small">Leyendo y analizando los documentos… ({seg} s)</p>}
      {error && <p className="notice notice-red small">{error}</p>}
      {res && (
        <div className="ia">
          <div className="ia-cabeza">
            <span className={`pill pill-${TONO[res.semaforo] || 'gray'} ia-estado`}>{res.estado}</span>
            <span className="muted small">
              Semáforo {res.semaforo_texto.toLowerCase()} · confianza {res.nivel_confianza} ({Math.round(res.confianza * 100)} %)
              {' '}· {res.tiempos.total_s.toFixed(1)} s{res.desde_cache ? ' (guardado)' : ''} · {res.modelo_llm}
            </span>
          </div>
          <p className="ia-resumen">{res.resumen}</p>
          {res.observaciones.length > 0 && (
            <ul className="ia-acciones">{res.observaciones.map((o) => <li key={o}>{o}</li>)}</ul>
          )}
          {res.documentos_faltantes.length > 0 && (
            <p className="notice notice-red small">Faltan: {res.documentos_faltantes.join(', ')}</p>
          )}
          {GRUPOS.map(([clave, titulo, abierto]) => {
            const hs = res.hallazgos.filter((h) => h.resultado === clave);
            if (!hs.length) return null;
            return (
              <details key={clave} open={abierto} className="ia-grupo">
                <summary>{titulo} ({hs.length})</summary>
                <ul className="ia-lista">{hs.map((h) => <Hallazgo key={h.id} h={h} />)}</ul>
              </details>
            );
          })}
          <DatosExtraidos documentos={res.documentos} />
          <p className="tiny muted">
            Fecha de referencia {res.fecha_referencia} · uso requerido: {res.uso_requerido} · dictamen redactado
            por {res.dictamen_por === 'llm' ? 'el agente LLM' : 'reglas'}. El estado lo deciden reglas deterministas.
          </p>
        </div>
      )}
    </Card>
  );
}
