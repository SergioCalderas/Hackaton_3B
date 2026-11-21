import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, Pill, Steps } from '../components/ui.jsx';
import { TOTAL_DOCS, approvedCount, caseStatus, docsOf } from '../lib/selectors.js';

const FILTERS = [
  { key: 'todos', label: 'Todos' },
  { key: 'sin_revisar', label: 'Sin revisar' },
  { key: 'en_revision', label: 'En revisión' },
  { key: 'rechazada', label: 'Rechazados' },
  { key: 'aceptada', label: 'Aceptados' },
];

export default function Cases({ onOpenCase }) {
  const { state } = useStore();
  const [filter, setFilter] = useState('todos');
  const [q, setQ] = useState('');

  const rows = state.cases
    .map((c) => ({ c, ds: docsOf(state.docs, c.id) }))
    .map((r) => ({ ...r, status: caseStatus(r.c, r.ds) }))
    .filter((r) => (filter === 'todos' || r.status === filter) && r.c.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="stack-col">
      <Card className="toolbar">
        <div className="row wrap">
          {FILTERS.map((f) => (
            <button key={f.key} className={`chip ${filter === f.key ? 'chip-on' : ''}`} onClick={() => setFilter(f.key)}>
              {f.label}
            </button>
          ))}
        </div>
        <input className="search" placeholder="Buscar caso…" value={q} onChange={(e) => setQ(e.target.value)} />
      </Card>

      <div className="cards-grid">
        {rows.map(({ c, ds, status }) => (
          <button key={c.id} className="card case-card" onClick={() => onOpenCase(c.id)}>
            <div className="row between">
              <h3>{c.name}</h3>
              <Pill status={status} />
            </div>
            <p className="muted small">{c.address}</p>
            <Steps label="Avance de revisión" done={approvedCount(ds)} total={TOTAL_DOCS} />
          </button>
        ))}
        {rows.length === 0 && <p className="muted">No hay casos con ese filtro.</p>}
      </div>
    </div>
  );
}
