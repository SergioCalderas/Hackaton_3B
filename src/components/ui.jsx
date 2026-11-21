import React, { useState } from 'react';
import { STATUS_LABEL, STATUS_TONE, mapsEmbed, mapsLink } from '../lib/selectors.js';

export const Pill = ({ status }) => <span className={`pill pill-${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;

export const Dot = ({ level, title }) => <span className={`dot dot-${level}`} title={title} />;

export function Progress({ value, label, tone = 'red' }) {
  return (
    <div className="progress-wrap">
      {label && (
        <div className="progress-label">
          <span>{label}</span>
          <strong>{value}%</strong>
        </div>
      )}
      <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className={`progress-bar tone-${tone}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

// Avance por pasos: un segmento por documento aprobado
export function Steps({ done, total, label }) {
  return (
    <div className="progress-wrap">
      <div className="progress-label"><span>{label}</span><strong>{done} de {total}</strong></div>
      <div className="steps" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total}>
        {Array.from({ length: total }, (_, i) => <i key={i} className={i < done ? 'on' : ''} />)}
      </div>
    </div>
  );
}

// Barra apilada: segmentos [{value, tone, label}]
export function StackBar({ segments }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  return (
    <div className="stack">
      {segments.map((s) => (
        <div key={s.label} className={`tone-${s.tone}`} style={{ width: `${(s.value / total) * 100}%` }} title={`${s.label}: ${s.value}`} />
      ))}
    </div>
  );
}

export const Card = ({ className = '', title, action, children }) => (
  <section className={`card ${className}`}>
    {(title || action) && (
      <header className="card-head">
        <h2>{title}</h2>
        {action}
      </header>
    )}
    {children}
  </section>
);

export function MapCard({ item, title = 'Ubicación del caso' }) {
  if (!item) {
    return (
      <Card className="map-card" title={title}>
        <div className="map-empty">Aún no hay casos aceptados para mostrar en el mapa.</div>
      </Card>
    );
  }
  return (
    <Card
      className="map-card"
      title={title}
      action={
        <a className="btn btn-ghost btn-sm" href={mapsLink(item)} target="_blank" rel="noreferrer">
          Abrir en Google Maps ↗
        </a>
      }
    >
      <iframe key={item.id} title={`Mapa ${item.name}`} src={mapsEmbed(item)} loading="lazy" referrerPolicy="no-referrer-when-downgrade" />
      <p className="muted small">
        <strong>{item.name}</strong> · {item.address}
      </p>
    </Card>
  );
}

// Modal con texto obligatorio (conclusión al aceptar, motivo al rechazar)
export function ReasonModal({ title, label, confirmLabel, tone = 'red', onConfirm, onClose }) {
  const [text, setText] = useState('');
  const ok = text.trim().length >= 5;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal modal-sm" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <label className="field">
          <span>{label} <em>(obligatorio)</em></span>
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
        </label>
        <div className="row end">
          <button className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button className={`btn ${tone === 'green' ? 'btn-green' : 'btn-red'}`} disabled={!ok} onClick={() => onConfirm(text)}>
            {confirmLabel}
          </button>
        </div>
        {!ok && <p className="muted small">Escribe al menos 5 caracteres.</p>}
      </div>
    </div>
  );
}
