// Inicio de sesion con Google Identity Services.
// IMPORTANTE: el ID token debe verificarse tambien en el backend (firma, aud, exp). Aqui solo se valida en cliente.
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

// "correo:rol,correo:rol" -> { correo: rol }
const ALLOWED = Object.fromEntries(
  (import.meta.env.VITE_GOOGLE_ALLOWED || '')
    .split(',')
    .map((p) => p.trim().split(':'))
    .filter((p) => p[0] && ['admin', 'gestor'].includes(p[1]))
    .map(([mail, role]) => [mail.toLowerCase(), role])
);

function parseJwt(token) {
  const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

export const newNonce = () =>
  [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, '0')).join('');

export function userFromCredential(credential, nonce) {
  const p = parseJwt(credential);
  if (!['accounts.google.com', 'https://accounts.google.com'].includes(p.iss)) throw new Error('Emisor no valido.');
  if (p.aud !== GOOGLE_CLIENT_ID) throw new Error('Token para otra aplicacion.');
  if (p.exp * 1000 < Date.now()) throw new Error('La sesion de Google expiro.');
  if (p.nonce !== nonce) throw new Error('Token no valido (nonce).');
  if (!p.email_verified) throw new Error('Correo de Google no verificado.');
  const role = ALLOWED[String(p.email).toLowerCase()];
  if (!role) throw new Error('Tu cuenta de Google no tiene acceso a este sistema.');
  return { id: `g-${p.sub}`, name: p.name || p.email, email: p.email, role };
}

let loading;
export function loadGoogle() {
  if (window.google && window.google.accounts) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://accounts.google.com/gsi/client';
      s.async = true;
      s.onload = resolve;
      s.onerror = () => reject(new Error('No se pudo cargar Google.'));
      document.head.appendChild(s);
    });
  }
  return loading;
}
