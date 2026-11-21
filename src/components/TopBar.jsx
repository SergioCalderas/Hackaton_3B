import React, { useState } from 'react';
import logo from '../assets/images/logo-3b.png';

export default function TopBar({ user, tabs, current, onNav, onLogout }) {
  const [open, setOpen] = useState(false);
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('');
  const currentLabel = (tabs.find((t) => t.key === current) || tabs[0]).label;
  const go = (k) => { setOpen(false); onNav(k); };

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <img className="logo" src={logo} alt="3B" />
          <span className="brand-text">Prefactibilidad</span>
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
