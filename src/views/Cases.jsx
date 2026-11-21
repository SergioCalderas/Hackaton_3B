import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, Pill } from '../components/ui.jsx';
import { DOC_TYPES } from '../lib/seed.js';
import { STATUS_LABEL, inDays, caseStatus, docState, docsOf } from '../lib/selectors.js';

const CELL_MARK = { aprobado: '✓', en_revision: '…', rechazado: '✕', sin_revisar: '·', faltante: '!' };

const FILTERS = [
  { key: 'todos', label: 'Todos' },
  { key: 'sin_revisar', label: 'Sin revisar' },
  { key: 'en_revision', label: 'En revisión' },
  { key: 'rechazada', label: 'Rechazados' },
  { key: 'aceptada', label: 'Aceptados' },
];

export default function Cases({ days, onOpenCase }) {
  const { state } = useStore();
  const [filter, setFilter] = useState('todos');
  const [q, setQ] = useState('');

  const rows = state.cases
    .map((c) => ({ c, ds: docsOf(state.docs, c.id) }))
    .map((r) => ({ ...r, status: caseStatus(r.c, r.ds) }))
    .filter((r) => inDays(r.c, days))
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

      <Card title="Estado de documentos por caso">
        <div className="table-wrap">
          <table className="matrix matrix-click">
            <thead>
              <tr><th>ID de caso</th>{DOC_TYPES.map((t) => <th key={t.key}>{t.label}</th>)}<th>Estado</th></tr>
            </thead>
            <tbody>
              {rows.map(({ c, ds, status }) => (
                <tr key={c.id} tabIndex={0} onClick={() => onOpenCase(c.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') onOpenCase(c.id); }}>
                  <td><span className="code">{c.code}</span></td>
                  {DOC_TYPES.map((t) => {
                    const st = docState(ds.find((d) => d.type === t.key));
                    return <td key={t.key}><span className={`cell cell-${st}`} title={STATUS_LABEL[st]}>{CELL_MARK[st]}</span></td>;
                  })}
                  <td><Pill status={status} /></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={DOC_TYPES.length + 2} className="muted">No hay casos con ese filtro.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="legend">
          {['aprobado', 'en_revision', 'sin_revisar', 'faltante', 'rechazado'].map((st) => (
            <span key={st}><i className={`cell cell-${st}`} style={{ width: 14, height: 14, lineHeight: '14px' }} /> {STATUS_LABEL[st]}</span>
          ))}
        </div>
      </Card>
    </div>
  );
}
