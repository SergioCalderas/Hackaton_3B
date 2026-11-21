import React, { useEffect, useRef, useState } from 'react';
import { useStore } from '../store.jsx';
import logo from '../assets/images/logo-3b.png';
import { hashPassword } from '../lib/secure.js';
import { GOOGLE_CLIENT_ID, loadGoogle, newNonce, userFromCredential } from '../lib/auth.js';

function GoogleButton({ onError }) {
  const { dispatch } = useStore();
  const box = useRef(null);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return undefined;
    const nonce = newNonce();
    let cancelled = false;
    loadGoogle()
      .then(() => {
        if (cancelled) return;
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          nonce,
          callback: ({ credential }) => {
            try {
              dispatch({ type: 'LOGIN_GOOGLE', user: userFromCredential(credential, nonce) });
            } catch (e) {
              onError(e.message);
            }
          },
        });
        window.google.accounts.id.renderButton(box.current, { theme: 'outline', size: 'large', text: 'continue_with', shape: 'pill', width: 320, locale: 'es' });
      })
      .catch((e) => onError(e.message));
    return () => { cancelled = true; };
  }, [dispatch, onError]);

  if (!GOOGLE_CLIENT_ID) {
    return (
      <button type="button" className="btn btn-ghost" disabled title="Define VITE_GOOGLE_CLIENT_ID en .env.local">
        Continuar con Google (sin configurar)
      </button>
    );
  }
  return <div ref={box} className="google-box" />;
}

export default function Login() {
  const { state, dispatch } = useStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  // Solo en desarrollo y sin backend: cuentas demo locales (hash SHA-256 en seed.js). No existe en el build de producción.
  const localLogin = async () => {
    const h = await hashPassword(password);
    const u = state.users.find((x) => x.hash && x.email === email.trim().toLowerCase() && x.hash === h);
    if (u) dispatch({ type: 'LOGIN', user: u });
    else setError('Correo o contraseña incorrectos.');
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    let res;
    try {
      res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ correo: email.trim(), contrasena: password }),
      });
    } catch {
      res = null; // sin conexión
    }
    // Backend caído: sin respuesta o error 5xx (el proxy de Vite responde 500/502/504 si no hay servidor)
    const backendDown = !res || res.status >= 500;
    if (backendDown) {
      if (import.meta.env.DEV) return localLogin();
      return setError('No hay conexión con el servidor.');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return setError(data.error || 'Correo o contraseña incorrectos.');
    dispatch({ type: 'LOGIN', user: data.user });
  };

  return (
    <div className="login">
      <div className="login-side">
        <img className="logo-big" src={logo} alt="3B" />
        <h1>Prefactibilidad de expansión</h1>
        <p className="slogan">Bueno, bonito y barato.</p>
      </div>
      <form className="login-card card" onSubmit={submit}>
        <h2>Iniciar sesión</h2>
        <GoogleButton onError={setError} />
        <div className="or"><span>o con correo</span></div>
        <label className="field">
          <span><span className="req">*</span> Correo</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </label>
        <label className="field">
          <span><span className="req">*</span> Contraseña</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn btn-red" type="submit">Entrar</button>
      </form>
    </div>
  );
}
