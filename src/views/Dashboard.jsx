import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, MapCard, Pill, Progress, StackBar } from '../components/ui.jsx';
import { DOC_LABEL, caseStatus, docKpis, docState, docsOf, reviewProgress } from '../lib/selectors.js';

export default function Dashboard({ user, onOpenCase, onNav }) {
  const { state } = useStore();
  const { cases, docs } = state;
  const dk = docKpis(docs);
  const pending = docs.filter((d) => ['sin_revisar', 'en_revision', 'faltante'].includes(docState(d)) && d.caseId);
  const [selId, setSelId] = useState(null);
  const selected = cases.find((c) => c.id === selId) || (pending[0] && cases.find((c) => c.id === pending[0].caseId)) || cases[0];

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
            { label: 'Sin revisar', value: dk.sin_revisar + dk.faltante, tone: 'gray' },
            { label: 'Rechazados', value: dk.rechazado, tone: 'red' },
          ]}
        />
        <p className="muted small">
          {dk.total} documentos en total{dk.faltante > 0 && ` · ${dk.faltante} aún incompletos (faltantes)`}
        </p>
      </Card>

      <Card className="span-6 navy-card" title="Documentos por aprobar">
        <ul className="pending">
          {pending.length === 0 && <li className="muted">No hay documentos pendientes 🎉</li>}
          {pending.slice(0, 8).map((d) => {
            const c = cases.find((x) => x.id === d.caseId);
            return (
              <li key={d.id} className={`sel ${selected && selected.id === c.id ? 'sel-on' : ''}`} onClick={() => setSelId(c.id)}>
                <div>
                  <strong>{DOC_LABEL[d.type]}</strong>
                  <span>{c.name}</span>
                </div>
                <Pill status={docState(d)} />
                <button className="btn btn-light btn-sm" onClick={(e) => { e.stopPropagation(); onOpenCase(c.id); }}>Revisar</button>
              </li>
            );
          })}
        </ul>
        {pending.length > 8 && <p className="small muted-light">y {pending.length - 8} más…</p>}
      </Card>

      <div className="span-6">
        <MapCard item={selected} title={`Ubicación · ${selected ? selected.name : ''}`} />
      </div>

      <Card className="span-12" title="Avance por caso" action={<button className="btn btn-ghost btn-sm" onClick={() => onNav('casos')}>Todos los casos →</button>}>
        <div className="mini-cases">
          {cases.map((c) => {
            const ds = docsOf(docs, c.id);
            return (
              <button key={c.id} className={`mini-case ${selected && selected.id === c.id ? 'mini-on' : ''}`} onClick={() => setSelId(c.id)}>
                <div className="row between"><strong>{c.name}</strong><Pill status={caseStatus(c, ds)} /></div>
                <Progress value={reviewProgress(ds)} />
                <span className="small muted">Clic para ver ubicación</span>
              </button>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
