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

  const submit = async (e) => {
    e.preventDefault();
    const h = await hashPassword(password);
    const u = state.users.find((x) => x.email === email.trim().toLowerCase() && x.hash === h);
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
        <GoogleButton onError={setError} />
        <div className="or"><span>o con correo</span></div>
        <label className="field">
          <span>Correo</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </label>
        <label className="field">
          <span>Contraseña</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn btn-red" type="submit">Entrar</button>
      </form>
    </div>
  );
}
