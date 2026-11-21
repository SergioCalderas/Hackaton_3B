import React, { useState } from 'react';
import logo from '../assets/images/logo-3b.png';
import { useStore } from '../store.jsx';
import { DAY_OPTIONS, TOTAL_DOCS, approvedCount, caseStatus, docKpis, docState, docsOf, inDays } from '../lib/selectors.js';

export default function TopBar({ user, tabs, current, days, onDays, onNav, onLogout }) {
  const [open, setOpen] = useState(false);
  const { state } = useStore();
  const okCases = new Set(state.cases.filter((c) => inDays(c, days)).map((c) => c.id));
  const docs = state.docs.filter((d) => okCases.has(d.caseId));
  const dk = docKpis(docs);
  // Estado de los CASOS: con un documento rechazado el caso es rechazado; aprobado = los 5 documentos aprobados
  const ck = { aprobado: 0, en_revision: 0, sin_revisar: 0, rechazado: 0 };
  state.cases.filter((c) => okCases.has(c.id)).forEach((c) => {
    const ds = docsOf(state.docs, c.id);
    const st = caseStatus(c, ds);
    if (st === 'rechazada') ck.rechazado += 1;
    else if (st === 'aceptada' || approvedCount(ds) === TOTAL_DOCS) ck.aprobado += 1;
    else ck[st] += 1;
  });
  const pending = docs.filter((d) => ['sin_revisar', 'en_revision'].includes(docState(d)));
  const pendingCases = new Set(pending.map((d) => d.caseId)).size;
  const stats = [
    { k: 'aprobado', label: 'Casos aprobados', tone: 'green' },
    { k: 'en_revision', label: 'En revisión', tone: 'amber' },
    { k: 'sin_revisar', label: 'Sin revisar', tone: 'gray' },
    { k: 'rechazado', label: 'Rechazados', tone: 'red' },
  ];
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('');
  const currentLabel = (tabs.find((t) => t.key === current) || tabs[0]).label;
  const go = (k) => { setOpen(false); onNav(k); };

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <img className="logo" src={logo} alt="3B" />
          <div className="brand-col">
            <span className="brand-text">Prefactibilidad</span>
            <label className="days-chip">
              <span>Casos de los últimos</span>
              <select value={days} onChange={(e) => onDays(Number(e.target.value))}>
                {DAY_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
              </select>
            </label>
          </div>
        </div>
        <nav className="tabs">
          {tabs.map((t) => (
            <button key={t.key} className={`tab ${current === t.key ? 'active' : ''}`} onClick={() => onNav(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="user">
          <div className="user-info">
            <strong>{user.name}</strong>
            <span>{user.role === 'admin' ? 'Administrador' : 'Gestor de expansión'}</span>
          </div>
          <span className="avatar">{initials}</span>
          <button className="btn btn-light btn-sm desk-only" onClick={onLogout}>Salir</button>
        </div>
      </header>

      <section className="stats-strip" aria-label="Resumen de documentos">
        <div className="tb-bar" role="img" aria-label="Documentos por estado">
          {stats.map((t) => <i key={t.k} className={`tb-${t.tone}`} style={{ flexGrow: ck[t.k] }} title={`${t.label}: ${ck[t.k]}`} />)}
        </div>
        <ul>
          {stats.map((t) => (
            <li key={t.k}><i className={`tb-dot tb-${t.tone}`} />{t.label} <b>{ck[t.k]}</b></li>
          ))}
        </ul>
        <small>{pending.length} documentos por aprobar en {pendingCases} casos · {dk.total - dk.faltante} recibidos</small>
      </section>

      {/* Menú desplegable inferior (solo celular) */}
      <div className={`bottom-menu ${open ? 'open' : ''}`}>
        {open && <div className="bm-backdrop" onClick={() => setOpen(false)} />}
        <div className="bm-sheet">
          {open && (
            <ul className="bm-list">
              {tabs.map((t) => (
                <li key={t.key}>
                  <button className={current === t.key ? 'on' : ''} onClick={() => go(t.key)}>{t.label}</button>
                </li>
              ))}
              <li><button className="out" onClick={onLogout}>Cerrar sesión</button></li>
            </ul>
          )}
          <button className="bm-bar" onClick={() => setOpen(!open)} aria-expanded={open}>
            <img src={logo} alt="" />
            <span>{currentLabel}</span>
            <i>{open ? '▾' : '▴'}</i>
          </button>
        </div>
      </div>
    </>
  );
}
