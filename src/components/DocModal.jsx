import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Dot, Pill, Progress } from './ui.jsx';
import { CHECKS } from '../lib/seed.js';
import { DOC_LABEL, docSemaphore, docState, fmtDate, fmtVigencia, vigenciaVencida } from '../lib/selectors.js';
import { FiltroPill, useFiltro } from '../lib/filtro.jsx';

function FiltroDoc({ caseId, tipo }) {
  const d = useFiltro(caseId).docDe(tipo);
  if (!d) return null;
  const r = d.filtro;
  const tone = { APROBADO: 'green', REVISION_MANUAL: 'amber', VOLVER_A_SUBIR: 'red' }[d.estado] || 'amber';
  return (
    <div className={`notice notice-${tone} filtro-doc`}>
      <div className="row between">
        <strong>Filtro de calidad</strong>
        <FiltroPill estado={d.estado} />
      </div>
      {r ? (
        <>
          <p className="small" style={{ margin: '6px 0' }}>{r.mensaje}</p>
          <div className="tiny">
            {r.tipo_detectado_nombre && <>Tipo detectado: <strong>{r.tipo_detectado_nombre}</strong> · </>}
            {r.legibilidad != null && <>Legibilidad: <strong>{Math.round(r.legibilidad * 100)}%</strong> · </>}
            {r.confianza_ocr != null && <>Confianza OCR: <strong>{Number(r.confianza_ocr).toFixed(2)}</strong> · </>}
            Verificado {fmtDate(r.verificado_en)}
          </div>
          {r.observaciones && r.observaciones.length > 0 && (
            <ul className="filtro-obs">{r.observaciones.map((o) => <li key={o}>{o}</li>)}</ul>
          )}
        </>
      ) : (
        <p className="small" style={{ margin: '6px 0' }}>
          {d.tiene_archivo ? 'Aún no se verifica. Usa “Verificar documentos” en el detalle del caso.' : 'La base de datos no tiene archivo para este documento.'}
        </p>
      )}
      {tipo === 'numero_oficial' && <p className="tiny" style={{ margin: 0 }}>En la base de datos, Número oficial y Alineamiento son un solo documento.</p>}
    </div>
  );
}

const SEM_TEXT = { ok: 'Coincide', warn: 'Revisar', fail: 'Diferencia' };

export default function DocModal({ docId, onClose }) {
  const { state, dispatch } = useStore();
  const d = state.docs.find((x) => x.id === docId);
  const c = state.cases.find((x) => x.id === d.caseId);
  const [mode, setMode] = useState(null); // 'aprobar' | 'rechazar'
  const [text, setText] = useState('');

  const st = docState(d);
  const locked = d.review.status === 'rechazado'; // un rechazo bloquea la aceptación
  const incomplete = d.completitud < 100;
  const sem = docSemaphore(d);
  const userName = (id) => (state.users.find((u) => u.id === id) || {}).name || '—';
  const closedCase = c.decision && c.decision.value === 'aceptada';
  const ok = text.trim().length >= 5;

  const confirm = () => {
    dispatch({ type: mode === 'aprobar' ? 'APPROVE_DOC' : 'REJECT_DOC', id: d.id, text });
    onClose();
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal doc-modal" onClick={(e) => e.stopPropagation()}>
        <header className="row between">
          <div>
            <h3>{DOC_LABEL[d.type]}</h3>
            <p className="muted small">{c.name} · {d.file}</p>
          </div>
          <Pill status={st} />
        </header>

        <div className="doc-split">
          <div className="doc-data">
            <Progress label="Completitud del documento" value={d.completitud} tone={incomplete ? 'amber' : 'green'} />

            <FiltroDoc caseId={d.caseId} tipo={d.type} />

            {d.vigencia && (
              <p className={`notice ${vigenciaVencida(d.vigencia) ? 'notice-red' : 'notice-green'}`}>
                <strong>Vigencia del predial:</strong> hasta el {fmtVigencia(d.vigencia)} · {vigenciaVencida(d.vigencia) ? 'Vencida' : 'Vigente'}
              </p>
            )}

            <h4>Validaciones {sem !== 'ok' && <span className={`sem-label sem-${sem}`}>requiere revisión</span>}</h4>
            <ul className="checks">
              {CHECKS.map((k) => (
                <li key={k.key} className={`check check-${d.checks[k.key]}`}>
                  <Dot level={d.checks[k.key]} />
                  <div>
                    <strong>{k.label}</strong>
                    <span>{d.notes[k.key]}</span>
                  </div>
                  <em>{SEM_TEXT[d.checks[k.key]]}</em>
                </li>
              ))}
            </ul>

            {incomplete && !locked && (
              <p className="notice notice-amber">Este documento está incompleto ({d.completitud}%). No puede evaluarse hasta que se cargue completo.</p>
            )}

            {d.review.status === 'aprobado' && <p className="notice notice-green"><strong>Conclusión:</strong> {d.review.conclusion}<br /><span className="tiny">{userName(d.review.by)} · {fmtDate(d.review.at)}</span></p>}
            {locked && <p className="notice notice-red"><strong>Rechazado:</strong> {d.review.reason}<br /><span className="tiny">{userName(d.review.by)} · {fmtDate(d.review.at)} · Un documento rechazado ya no puede aceptarse.</span></p>}

            {!locked && !incomplete && !closedCase && (
              <>
                {!mode ? (
                  <div className="row end">
                    <button className="btn btn-ghost" onClick={() => setMode('rechazar')}>Denegar (es incorrecto)</button>
                    <button className="btn btn-green" onClick={() => setMode('aprobar')} disabled={d.review.status === 'aprobado'}>
                      Aceptar (es correcto)
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="field">
                      <span>{mode === 'aprobar' ? 'Conclusiones' : 'Motivo del rechazo'} <em>(obligatorio)</em></span>
                      <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
                    </label>
                    <div className="row end">
                      <button className="btn btn-ghost" onClick={() => { setMode(null); setText(''); }}>Atrás</button>
                      <button className={`btn ${mode === 'aprobar' ? 'btn-green' : 'btn-red'}`} disabled={!ok} onClick={confirm}>
                        {mode === 'aprobar' ? 'Confirmar aceptación' : 'Confirmar rechazo'}
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
            {(locked || incomplete || closedCase) && (
              <div className="row end"><button className="btn btn-ghost" onClick={onClose}>Cerrar</button></div>
            )}
          </div>

          <div className="doc-view">
            {d.pdf ? (
              <div className="pdf-box">
                <iframe title={d.file} src={d.pdf} />
                <a className="btn btn-ghost btn-sm" href={d.pdf} target="_blank" rel="noreferrer">Abrir documento en otra pestaña ↗</a>
              </div>
            ) : (
              <div className="doc-preview"><span>📄</span><div><strong>Documento no cargado</strong><div className="muted small">Aún no hay archivo para visualizar.</div></div></div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
