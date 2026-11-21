import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, MapCard, Pill, StackBar, Steps } from '../components/ui.jsx';
import { DOC_LABEL, TOTAL_DOCS, approvedCount, caseStatus, docKpis, docState, docsOf, lastActivity } from '../lib/selectors.js';

export default function Dashboard({ user, onOpenCase, onNav }) {
  const { state } = useStore();
  const { cases, docs } = state;
  const dk = docKpis(docs);
  // Los documentos faltantes no se muestran: solo los completos, pendientes de aprobar
  const pending = docs.filter((d) => ['sin_revisar', 'en_revision'].includes(docState(d)));
  const [selId, setSelId] = useState(null);
  const selected = cases.find((c) => c.id === selId) || (pending[0] && cases.find((c) => c.id === pending[0].caseId)) || cases[0];

  // Últimos 8 casos con actividad más reciente
  const recent = cases
    .map((c) => ({ c, ds: docsOf(docs, c.id) }))
    .map((r) => ({ ...r, last: lastActivity(r.c, r.ds) }))
    .sort((a, b) => b.last - a.last)
    .slice(0, 8);

  const tiles = [
    { k: 'aprobado', label: 'Aprobados', tone: 'green' },
    { k: 'en_revision', label: 'En revisión', tone: 'amber' },
    { k: 'sin_revisar', label: 'Sin revisar', tone: 'gray' },
    { k: 'rechazado', label: 'Rechazados', tone: 'red' },
  ];

  return (
    <div className="grid">
      <Card className="span-12 hero">
        <h1>Hola, {user.name.split(' ')[0]}</h1>
        <p className="muted">
          Tienes {pending.length} documentos por aprobar en {new Set(pending.map((d) => d.caseId)).size} casos.
        </p>
        <div className="tiles">
          {tiles.map((t) => (
            <div key={t.k} className={`tile tile-${t.tone}`}>
              <strong>{dk[t.k]}</strong>
              <span>{t.label}</span>
            </div>
          ))}
        </div>
        <StackBar
          segments={[
            { label: 'Aprobados', value: dk.aprobado, tone: 'green' },
            { label: 'En revisión', value: dk.en_revision, tone: 'amber' },
            { label: 'Sin revisar', value: dk.sin_revisar, tone: 'gray' },
            { label: 'Rechazados', value: dk.rechazado, tone: 'red' },
          ]}
        />
        <p className="muted small">{dk.total - dk.faltante} documentos recibidos</p>
      </Card>

      <Card className="span-6 navy-card" title="Documentos por aprobar">
        <ul className="pending">
          {pending.length === 0 && <li className="muted-light">No hay documentos pendientes 🎉</li>}
          {pending.slice(0, 8).map((d) => {
            const c = cases.find((x) => x.id === d.caseId);
            return (
              <li key={d.id} className={`sel ${selected && selected.id === c.id ? 'sel-on' : ''}`} onClick={() => setSelId(c.id)}>
                <div>
                  <strong>{DOC_LABEL[d.type]}</strong>
                  <span>{c.name}</span>
                </div>
                <Pill status={docState(d)} />
              </li>
            );
          })}
        </ul>
        {pending.length > 8 && <p className="small muted-light">y {pending.length - 8} más…</p>}
      </Card>

      <div className="span-6">
        <MapCard item={selected} title={`Ubicación · ${selected ? selected.name : ''}`} />
      </div>

      <Card className="span-12" title="Avance por caso · últimos 8" action={<button className="btn btn-ghost btn-sm" onClick={() => onNav('casos')}>Todos los casos →</button>}>
        <div className="mini-cases">
          {recent.map(({ c, ds }) => (
            <button key={c.id} className="mini-case" onClick={() => onOpenCase(c.id)}>
              <div className="row between"><strong>{c.name}</strong><Pill status={caseStatus(c, ds)} /></div>
              <Steps label="Documentos aprobados" done={approvedCount(ds)} total={TOTAL_DOCS} />
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}
