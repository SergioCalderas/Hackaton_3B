import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, MapCard, Pill, Progress, StackBar } from '../components/ui.jsx';
import { DOC_LABEL, caseKpis, caseStatus, docKpis, docState, docsOf, reviewProgress } from '../lib/selectors.js';

export default function Dashboard({ user, onOpenCase, onNav }) {
  const { state } = useStore();
  const { cases, docs } = state;
  const dk = docKpis(docs);
  const ck = caseKpis(cases, docs);
  const pending = docs.filter((d) => ['sin_revisar', 'en_revision', 'faltante'].includes(docState(d)) && d.caseId);
  const accepted = cases.filter((c) => caseStatus(c, docsOf(docs, c.id)) === 'aceptada');
  const [mapId, setMapId] = useState(null);
  const mapCase = accepted.find((c) => c.id === mapId) || accepted[0];

  const tiles = [
    { k: 'aprobado', label: 'Aprobados', tone: 'green' },
    { k: 'en_revision', label: 'En revisión', tone: 'amber' },
    { k: 'sin_revisar', label: 'Sin revisar', tone: 'gray' },
    { k: 'rechazado', label: 'Rechazados', tone: 'red' },
  ];

  return (
    <div className="grid">
      <Card className="span-7 hero">
        <h1>Hola, {user.name.split(' ')[0]}</h1>
        <p className="muted">
          Tienes {dk.total - dk.aprobado} documentos por aprobar en {cases.length - ck.aceptada} casos.
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

      <Card className="span-5 promo" title="Prefactibilidad por caso" action={<button className="btn btn-yellow btn-sm" onClick={() => onNav('casos')}>Ver casos</button>}>
        <div className="promo-grid">
          <div><strong>{ck.aceptada}</strong><span>Aceptados</span></div>
          <div><strong>{ck.en_revision}</strong><span>En revisión</span></div>
          <div><strong>{ck.sin_revisar}</strong><span>Sin revisar</span></div>
          <div><strong>{ck.rechazada}</strong><span>Rechazados</span></div>
        </div>
      </Card>

      <Card className="span-6 navy-card" title="Documentos por aprobar">
        <ul className="pending">
          {pending.length === 0 && <li className="muted">No hay documentos pendientes 🎉</li>}
          {pending.slice(0, 8).map((d) => {
            const c = cases.find((x) => x.id === d.caseId);
            return (
              <li key={d.id}>
                <div>
                  <strong>{DOC_LABEL[d.type]}</strong>
                  <span>{c.name}</span>
                </div>
                <Pill status={docState(d)} />
                <button className="btn btn-light btn-sm" onClick={() => onOpenCase(c.id)}>Revisar</button>
              </li>
            );
          })}
        </ul>
        {pending.length > 8 && <p className="small muted-light">y {pending.length - 8} más…</p>}
      </Card>

      <div className="span-6 stack-col">
        <MapCard item={mapCase} title="Casos aceptados en el mapa" />
        {accepted.length > 1 && (
          <div className="row wrap">
            {accepted.map((c) => (
              <button key={c.id} className={`chip ${mapCase && mapCase.id === c.id ? 'chip-on' : ''}`} onClick={() => setMapId(c.id)}>
                {c.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <Card className="span-12" title="Avance por caso" action={<button className="btn btn-ghost btn-sm" onClick={() => onNav('casos')}>Todos los casos →</button>}>
        <div className="mini-cases">
          {cases.map((c) => {
            const ds = docsOf(docs, c.id);
            return (
              <button key={c.id} className="mini-case" onClick={() => onOpenCase(c.id)}>
                <div className="row between"><strong>{c.name}</strong><Pill status={caseStatus(c, ds)} /></div>
                <Progress value={reviewProgress(ds)} />
              </button>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
