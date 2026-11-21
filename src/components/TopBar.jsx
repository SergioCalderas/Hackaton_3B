import React from 'react';

export default function TopBar({ user, tabs, current, onNav, onLogout }) {
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('');
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">3B</span>
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
        <button className="btn btn-light btn-sm" onClick={onLogout}>Salir</button>
      </div>
    </header>
  );
}
