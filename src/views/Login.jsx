import React, { useState } from 'react';
import { useStore } from '../store.jsx';
import logo from '../assets/images/logo-3b.png';

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

  return (
    <div className="login">
      <div className="login-side">
        <img className="logo-big" src={logo} alt="3B" />
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
      </form>
    </div>
  );
}
