import React from 'react';
import { useStore } from '../store.jsx';
import { USERS } from '../lib/seed.js';

// Barra PROVISIONAL (solo en desarrollo) para cambiar de usuario sin contraseña. No existe en el build de producción.
export default function DevSwitch() {
  const { state, dispatch } = useStore();
  if (!import.meta.env.DEV) return null;
  return (
    <div className="devswitch">
      <b>DEV</b>
      <span>Cambiar a:</span>
      {USERS.map((u) => (
        <button key={u.id} type="button" className={String(state.session) === String(u.id) ? 'on' : ''}
          onClick={() => dispatch({ type: 'LOGIN', user: u })}>
          {u.role === 'admin' ? 'Admin' : 'Gestor'} · {u.name.split(' ')[0]}
        </button>
      ))}
      {state.session && <button type="button" onClick={() => dispatch({ type: 'LOGOUT' })}>Salir</button>}
    </div>
  );
}
