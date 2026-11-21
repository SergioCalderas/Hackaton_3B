import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, Dot, MapCard, Pill, ReasonModal, Steps } from '../components/ui.jsx';
import DocModal from '../components/DocModal.jsx';
import { CHECKS, DOC_TYPES } from '../lib/seed.js';
import { TOTAL_DOCS, approvedCount, canAcceptCase, caseStatus, docSemaphore, docState, docsOf, fmtDate, fmtVigencia, vigenciaVencida } from '../lib/selectors.js';
import { EXPEDIENTE_LABEL, FiltroPill, useFiltro } from '../lib/filtro.jsx';

const TIPOS_BD = [
  ['escrituras', 'Escrituras'],
  ['predial', 'Predial'],
  ['alineamiento', 'Alineamiento y Núm. Oficial'],
  ['uso_suelo', 'Uso de suelo'],
];

function FiltroCard({ caseId }) {
  const f = useFiltro(caseId);
  const exp = f.op ? f.op.expediente : null;
  const tone = { EN_REVISION: 'green', NO_VALIDADO: 'red', SIN_VERIFICAR: 'amber' }[exp] || 'amber';
  const ultima = f.op && Object.values(f.op.documentos).map((d) => d.filtro && d.filtro.verificado_en).filter(Boolean).sort().pop();
  return (
    <Card title="Filtro de calidad · Fase 1">
      {!f.op ? (
        <p className="muted small">{f.error ? `No se pudo consultar el filtro: ${f.error}` : `Sin operación en la base de datos para este caso.`}</p>
      ) : (
        <>
          <p className={`notice notice-${tone}`} style={{ marginTop: 0 }}>
            <strong>{EXPEDIENTE_LABEL[exp]}</strong>
            <br /><span className="tiny">Operación #{f.opId}{ultima ? ` · verificado ${fmtDate(ultima)}` : ''}</span>
          </p>
          <ul className="filtro-lista">
            {TIPOS_BD.map(([tipo, label]) => {
              const d = f.docDe(tipo);
              return (
                <li key={tipo}>
                  <div>
                    <strong>{label}</strong>
                    {d && d.filtro && d.estado !== 'APROBADO' && <span className="muted tiny">{d.filtro.mensaje}</span>}
                    {d && !d.tiene_archivo && <span className="muted tiny">La operación no tiene archivo para este documento.</span>}
                  </div>
                  {d && <FiltroPill estado={d.estado} />}
                </li>
              );
            })}
          </ul>
          <button className="btn btn-yellow btn-sm" disabled={f.corriendo} onClick={f.verificar}>
            {f.corriendo ? 'Verificando… (≈1 min la primera vez)' : 'Verificar documentos'}
          </button>
          {f.error && <p className="notice notice-red small">{f.error}</p>}
        </>
      )}
    </Card>
  );
}

function FiltroDocPill({ caseId, tipo }) {
  const d = useFiltro(caseId).docDe(tipo);
  return d ? <FiltroPill estado={d.estado} /> : null;
}

export default function CaseDetail({ caseId, onBack }) {
  const { state, dispatch } = useStore();
  const c = state.cases.find((x) => x.id === caseId);
  const ds = docsOf(state.docs, caseId);
  const status = caseStatus(c, ds);
  const [openDoc, setOpenDoc] = useState(null);
  const [decision, setDecision] = useState(null); // 'aceptada' | 'rechazada'
  const userName = (id) => (state.users.find((u) => u.id === id) || {}).name || '—';

  const open = (d) => {
    if (d.completitud === 100) dispatch({ type: 'OPEN_DOC', id: d.id });
    setOpenDoc(d.id);
  };

  const hasRejected = ds.some((d) => d.review.status === 'rechazado');
  const closed = status === 'aceptada' || (c.decision && c.decision.value === 'rechazada');
  const canAccept = canAcceptCase(ds) && !hasRejected && !closed;

  return (
    <div className="stack-col">
      <button className="btn btn-ghost btn-sm back" onClick={onBack}>← Volver</button>

      <Card className="case-head">
        <div className="row between wrap">
          <div>
            <h1>{c.name}</h1>
            <p className="muted">{c.address} · {c.owner}</p>
          </div>
          <Pill status={status} />
        </div>
        <Steps label="Avance de revisión (documentos aprobados)" done={approvedCount(ds)} total={TOTAL_DOCS} />
      </Card>

      <div className="grid">
        <Card className="span-8" title="Documentación">
          <div className="doc-list">
            {DOC_TYPES.map((t) => {
              const d = ds.find((x) => x.type === t.key);
              if (!d || d.completitud < 100) return null; // los documentos faltantes no se muestran
              const st = docState(d);
              return (
                <div key={d.id} className={`doc-row ${st === 'rechazado' ? 'locked' : ''}`}>
                  <div className="doc-main">
                    <strong>{t.label} <FiltroDocPill caseId={caseId} tipo={t.key} /></strong>
                    <span className="muted small">{d.file} · v{d.versions[d.versions.length - 1].v}</span>
                    {d.vigencia && (
                      <span className={`vig ${vigenciaVencida(d.vigencia) ? 'vig-off' : 'vig-on'}`}>
                        Vigencia: {fmtVigencia(d.vigencia)} · {vigenciaVencida(d.vigencia) ? 'Vencida' : 'Vigente'}
                      </span>
                    )}
                  </div>
                  <div className="doc-sem" title={CHECKS.map((k) => `${k.label}: ${d.checks[k.key]}`).join('\n')}>
                    {CHECKS.map((k) => <Dot key={k.key} level={d.checks[k.key]} />)}
                    <span className={`sem-label sem-${docSemaphore(d)}`}>
                      {docSemaphore(d) === 'ok' ? 'Sin diferencias' : 'Revisar'}
                    </span>
                  </div>
                  <Pill status={st} />
                  <button className="btn btn-red btn-sm" onClick={() => open(d)}>
                    {st === 'aprobado' || st === 'rechazado' ? 'Ver' : 'Revisar'}
                  </button>
                  {d.review.by && <span className="muted tiny doc-by">{userName(d.review.by)} · {fmtDate(d.review.at)}</span>}
                </div>
              );
            })}
          </div>
        </Card>

        <div className="span-4 stack-col">
          <FiltroCard caseId={caseId} />
          <Card title="Decisión de prefactibilidad">
            {c.decision ? (
              <div className={`decision decision-${c.decision.value}`}>
                <strong>{c.decision.value === 'aceptada' ? 'Prefactibilidad aceptada' : 'Prefactibilidad rechazada'}</strong>
                <p>{c.decision.text}</p>
                <span className="muted tiny">{userName(c.decision.by)} · {fmtDate(c.decision.at)}</span>
              </div>
            ) : hasRejected ? (
              <p className="muted">Hay documentos rechazados: el caso no puede aceptarse. Puedes rechazarlo formalmente.</p>
            ) : canAccept ? (
              <p className="muted">Toda la documentación está aprobada. Puedes aceptar la prefactibilidad.</p>
            ) : (
              <p className="muted">Aprueba los 5 documentos (al 100%) para habilitar la aceptación del caso.</p>
            )}
            {!closed && (
              <div className="row">
                <button className="btn btn-green" disabled={!canAccept} onClick={() => setDecision('aceptada')}>Aceptar caso</button>
                <button className="btn btn-ghost" onClick={() => setDecision('rechazada')}>Rechazar caso</button>
              </div>
            )}
          </Card>
          <MapCard item={c} title={status === 'aceptada' ? 'Caso aceptado · ubicación' : 'Caso en evaluación · ubicación'} />
        </div>
      </div>

      {openDoc && <DocModal docId={openDoc} onClose={() => setOpenDoc(null)} />}
      {decision && (
        <ReasonModal
          title={decision === 'aceptada' ? 'Aceptar prefactibilidad del caso' : 'Rechazar prefactibilidad del caso'}
          label={decision === 'aceptada' ? 'Conclusiones' : 'Motivo del rechazo'}
          confirmLabel={decision === 'aceptada' ? 'Aceptar caso' : 'Rechazar caso'}
          tone={decision === 'aceptada' ? 'green' : 'red'}
          onClose={() => setDecision(null)}
          onConfirm={(text) => { dispatch({ type: 'DECIDE_CASE', caseId, value: decision, text }); setDecision(null); }}
        />
      )}
    </div>
  );
}
