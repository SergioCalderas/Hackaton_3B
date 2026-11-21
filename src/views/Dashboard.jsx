import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, MapCard, Pill, Steps } from '../components/ui.jsx';
import { DOC_LABEL, inDays, TOTAL_DOCS, approvedCount, caseStatus, docKpis, docState, docsOf, lastActivity } from '../lib/selectors.js';

export default function Dashboard({ user, days, onOpenCase, onNav }) {
  const { state } = useStore();
  const { cases, docs } = state;
  const dk = docKpis(docs);
  // Los documentos faltantes no se muestran: solo los completos, pendientes de aprobar
  const okCases = new Set(cases.filter((c) => inDays(c, days)).map((c) => c.id));
  const pending = docs.filter((d) => okCases.has(d.caseId) && ['sin_revisar', 'en_revision'].includes(docState(d)));
  // Se selecciona un solo documento; el mapa muestra la ubicación (lat/lng) que trae la BD para su caso/propuesta de unidad
  const [selDocId, setSelDocId] = useState(null);
  const selDoc = pending.find((d) => d.id === selDocId) || pending[0];
  const selected = cases.find((c) => c.id === (selDoc && selDoc.caseId)) || cases[0];

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
      <Card className="span-6 navy-card" title="Documentos por aprobar">
        <ul className="pending">
          {pending.length === 0 && <li className="muted-light">No hay documentos pendientes 🎉</li>}
          {pending.slice(0, 8).map((d) => {
            const c = cases.find((x) => x.id === d.caseId);
            return (
              <li key={d.id} className={`sel ${selDoc && selDoc.id === d.id ? 'sel-on' : ''}`} onClick={() => setSelDocId(d.id)}>
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

    </div>
  );
}
