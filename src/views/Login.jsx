import React, { useState } from 'react';
import { useStore } from '../store.jsx';

export default function Login() {
  const { state, dispatch } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const submit = (e) => {
    e.preventDefault();
    const u = state.users.find((x) => x.email === email.trim().toLowerCase() && x.password === password);
    if (!u) return setError('Correo o contraseña incorrectos.');
    dispatch({ type: 'LOGIN', userId: u.id });
  };

  const demo = (u) => { setEmail(u.email); setPassword(u.password); setError(''); };

  return (
    <div className="login">
      <div className="login-side">
        <span className="brand-mark big">3B</span>
        <h1>Prefactibilidad de expansión</h1>
        <p>Revisa la documentación de cada caso, valida su congruencia y decide la prefactibilidad.</p>
      </div>
      <form className="login-card card" onSubmit={submit}>
        <h2>Iniciar sesión</h2>
        <label className="field">
          <span>Correo</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span>Contraseña</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn btn-red" type="submit">Entrar</button>
        <div className="demo">
          <span className="muted small">Cuentas de demostración (contraseña 3b123):</span>
          <div className="row wrap">
            {state.users.map((u) => (
              <button type="button" key={u.id} className="chip" onClick={() => demo(u)}>
                {u.role === 'admin' ? 'Admin' : u.name.split(' ')[0]}
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  );
}
