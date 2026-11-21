import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, Dot, Pill, Progress, StackBar } from '../components/ui.jsx';
import { DOC_TYPES } from '../lib/seed.js';
import { caseKpis, docKpis, docSemaphore, docState, fmtDate } from '../lib/selectors.js';

export function AdminSummary() {
  const { state } = useStore();
  const { docs, cases, history, users } = state;
  const dk = docKpis(docs);
  const ck = caseKpis(cases, docs);
  const gestores = users.filter((u) => u.role === 'gestor');

  const metrics = gestores.map((g) => {
    const mine = history.filter((h) => h.userId === g.id);
    const count = (w) => mine.filter((h) => h.action.startsWith(w)).length;
    const reviewedDocs = docs.filter((d) => d.review.by === g.id && ['aprobado', 'rechazado'].includes(d.review.status)).length;
    return { g, total: mine.length, aprobados: count('Aprobó'), rechazados: count('Rechazó'), casos: count('Aceptó la prefactibilidad'), reviewedDocs };
  });
  const max = Math.max(1, ...metrics.map((m) => m.total));

  const tiles = [
    { label: 'Documentos subidos', value: dk.total - dk.faltante, tone: 'navy' },
    { label: 'Aprobados', value: dk.aprobado, tone: 'green' },
    { label: 'Faltantes', value: dk.faltante, tone: 'amber' },
    { label: 'Rechazados', value: dk.rechazado, tone: 'red' },
  ];

  return (
    <div className="grid">
      <Card className="span-12 hero" title="Resumen de documentación">
        <div className="tiles">
          {tiles.map((t) => (
            <div key={t.label} className={`tile tile-${t.tone}`}><strong>{t.value}</strong><span>{t.label}</span></div>
          ))}
        </div>
        <StackBar
          segments={[
            { label: 'Aprobados', value: dk.aprobado, tone: 'green' },
            { label: 'En revisión', value: dk.en_revision, tone: 'amber' },
            { label: 'Sin revisar', value: dk.sin_revisar, tone: 'gray' },
            { label: 'Faltantes', value: dk.faltante, tone: 'navy' },
            { label: 'Rechazados', value: dk.rechazado, tone: 'red' },
          ]}
        />
        <p className="muted small">
          Casos: {ck.aceptada} aceptados · {ck.en_revision} en revisión · {ck.sin_revisar} sin revisar · {ck.rechazada} rechazados
        </p>
      </Card>

      <Card className="span-12" title="Métricas por gestor de expansión">
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Gestor</th><th>Acciones</th><th>Docs aprobados</th><th>Docs rechazados</th><th>Casos aceptados</th><th>Actividad</th></tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.g.id}>
                  <td><strong>{m.g.name}</strong></td>
                  <td>{m.total}</td>
                  <td>{m.aprobados}</td>
                  <td>{m.rechazados}</td>
                  <td>{m.casos}</td>
                  <td style={{ minWidth: 160 }}><Progress value={Math.round((m.total / max) * 100)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

export function AdminHistory() {
  const { state } = useStore();
  const [user, setUser] = useState('todos');
  const [q, setQ] = useState('');
  const name = (id) => (state.users.find((u) => u.id === id) || {}).name || '—';
  const rows = state.history.filter(
    (h) => (user === 'todos' || h.userId === user) && h.action.toLowerCase().includes(q.toLowerCase())
  );
  return (
    <Card title="Historial de cambios" action={<span className="muted small">{rows.length} registros</span>}>
      <div className="row wrap toolbar-inline">
        <select value={user} onChange={(e) => setUser(e.target.value)}>
          <option value="todos">Todos los usuarios</option>
          {state.users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <input className="search" placeholder="Buscar cambio…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Hora</th><th>Usuario</th><th>Cambio realizado</th></tr></thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.id}>
                <td className="nowrap">{fmtDate(h.at)}</td>
                <td className="nowrap">{name(h.userId)}</td>
                <td>{h.action}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={3} className="muted">Sin registros.</td></tr>}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// Una tabla por tipo de documento (5 tablas)
export function AdminDocs() {
  const { state } = useStore();
  const name = (id) => (state.users.find((u) => u.id === id) || {}).name || '—';
  return (
    <div className="stack-col">
      {DOC_TYPES.map((t) => {
        const rows = state.docs.filter((d) => d.type === t.key);
        return (
          <Card key={t.key} title={t.label} action={<span className="muted small">{rows.length} documentos</span>}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Caso</th><th>Archivo</th><th>Versiones</th><th>Completitud</th><th>Semáforo</th><th>Estado</th><th>Revisó</th></tr>
                </thead>
                <tbody>
                  {rows.map((d) => (
                    <tr key={d.id}>
                      <td><strong>{state.cases.find((c) => c.id === d.caseId).name}</strong></td>
                      <td>{d.file}</td>
                      <td>
                        <details>
                          <summary>v{d.versions[d.versions.length - 1].v}</summary>
                          <ul className="versions">
                            {[...d.versions].reverse().map((v) => <li key={v.v}>v{v.v} · {fmtDate(v.at)} · {v.by}</li>)}
                          </ul>
                        </details>
                      </td>
                      <td style={{ minWidth: 120 }}><Progress value={d.completitud} tone={d.completitud < 100 ? 'amber' : 'green'} /></td>
                      <td><Dot level={docSemaphore(d)} /></td>
                      <td><Pill status={docState(d)} /></td>
                      <td className="nowrap">{d.review.by ? `${name(d.review.by)} · ${fmtDate(d.review.at)}` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
