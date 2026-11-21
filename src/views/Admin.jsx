import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import { Card, Progress, StackBar } from '../components/ui.jsx';
import { DOC_TYPES } from '../lib/seed.js';
import { KINDS, STATUS_LABEL, actionKind, caseKpis, docKpis, docState, fmtDay, fmtHour } from '../lib/selectors.js';

const CELL_MARK = { aprobado: '✓', en_revision: '…', rechazado: '✕', sin_revisar: '·', faltante: '!' };

export function AdminSummary() {
  const { state } = useStore();
  const { docs, cases, history, users } = state;
  const dk = docKpis(docs);
  const ck = caseKpis(cases, docs);
  const gestores = users.filter((u) => u.role === 'gestor');

  const metrics = gestores.map((g) => {
    const mine = history.filter((h) => h.userId === g.id);
    const n = (k) => mine.filter((h) => actionKind(h.action) === k).length;
    return { g, total: mine.length, aprobados: n('aprobo'), rechazados: n('rechazo'), casos: n('caso_ok') };
  });
  const max = Math.max(1, ...metrics.map((m) => m.total));

  const tiles = [
    { label: 'Subidos', value: dk.total - dk.faltante, tone: 'navy' },
    { label: 'Aprobados', value: dk.aprobado, tone: 'green' },
    { label: 'Faltantes', value: dk.faltante, tone: 'amber' },
    { label: 'Rechazados', value: dk.rechazado, tone: 'red' },
  ];

  return (
    <div className="stack-col">
      <Card className="hero">
        <h1>Resumen</h1>
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
          {cases.length} casos: {ck.aceptada} aceptados · {ck.en_revision} en revisión · {ck.sin_revisar} sin revisar · {ck.rechazada} rechazados
        </p>
      </Card>

      <Card title="Estado de documentos por caso">
        <div className="table-wrap">
          <table className="matrix">
            <thead>
              <tr><th>ID de caso</th>{DOC_TYPES.map((t) => <th key={t.key}>{t.label}</th>)}</tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td><span className="code">{c.code}</span></td>
                  {DOC_TYPES.map((t) => {
                    const st = docState(docs.find((d) => d.caseId === c.id && d.type === t.key));
                    return <td key={t.key}><span className={`cell cell-${st}`} title={STATUS_LABEL[st]}>{CELL_MARK[st]}</span></td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="legend">
          {['aprobado', 'en_revision', 'sin_revisar', 'faltante', 'rechazado'].map((s) => (
            <span key={s}><i className={`cell cell-${s}`} style={{ width: 14, height: 14, lineHeight: '14px' }} /> {STATUS_LABEL[s]}</span>
          ))}
        </div>
      </Card>

      <Card title="Avance de cada gestor">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Gestor</th><th>Aprobados</th><th>Rechazados</th><th>Casos aceptados</th><th>Actividad</th></tr></thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.g.id}>
                  <td><strong>{m.g.name}</strong></td>
                  <td><span className="pill pill-green">{m.aprobados}</span></td>
                  <td><span className="pill pill-red">{m.rechazados}</span></td>
                  <td><span className="pill pill-navy">{m.casos}</span></td>
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
  const [kind, setKind] = useState('todos');
  const [user, setUser] = useState('todos');
  const name = (id) => (state.users.find((u) => u.id === id) || {}).name || '—';
  const code = (id) => (state.cases.find((c) => c.id === id) || {}).code || '';

  // Cambia nombres de caso por su ID y separa el detalle (conclusión / motivo)
  const parse = (h) => {
    let t = h.action;
    state.cases.forEach((c) => { t = t.split(c.name).join(c.code); });
    const m = t.match(/^(.*?)\.? (Conclusión|Motivo): (.*)$/);
    return m ? { title: m[1], detail: `${m[2]}: ${m[3]}` } : { title: t, detail: '' };
  };

  const rows = state.history
    .map((h) => ({ ...h, kind: actionKind(h.action) }))
    .filter((h) => (kind === 'todos' || h.kind === kind) && (user === 'todos' || h.userId === user));

  const days = [];
  rows.forEach((h) => {
    const d = fmtDay(h.at);
    const last = days[days.length - 1];
    if (last && last.day === d) last.items.push(h);
    else days.push({ day: d, items: [h] });
  });

  return (
    <Card title="Historial de cambios" action={<span className="muted small">{rows.length} registros</span>}>
      <div className="row wrap">
        <button className={`chip ${kind === 'todos' ? 'chip-on' : ''}`} onClick={() => setKind('todos')}>Todos</button>
        {Object.entries(KINDS).map(([k, v]) => (
          <button key={k} className={`chip ${kind === k ? 'chip-on' : ''}`} onClick={() => setKind(k)}>{v.icon} {v.label}</button>
        ))}
        <select value={user} onChange={(e) => setUser(e.target.value)}>
          <option value="todos">Todos los usuarios</option>
          {state.users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </div>

      {days.map((g) => (
        <div key={g.day}>
          <div className="day">{g.day}</div>
          <div className="tl">
            {g.items.map((h) => {
              const k = KINDS[h.kind];
              const p = parse(h);
              return (
                <div key={h.id} className={`tl-item k-${k.tone}`}>
                  <span className="tl-icon">{k.icon}</span>
                  <div className="tl-body">
                    <strong>{p.title}</strong>
                    <span>{name(h.userId)}{code(h.caseId) && ` · ${code(h.caseId)}`}{p.detail && ` · ${p.detail}`}</span>
                  </div>
                  <span className="tl-time">{fmtHour(h.at)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
      {rows.length === 0 && <p className="muted">Sin registros.</p>}
    </Card>
  );
}
