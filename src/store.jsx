import React, { createContext, useContext, useEffect, useReducer, useState } from 'react';
import { decryptJSON, encryptJSON } from './lib/secure.js';
import { buildSeed } from './lib/seed.js';
import { DOC_LABEL, docsOf, canAcceptCase } from './lib/selectors.js';

const KEY = '3b-prefactibilidad-v3';
const Ctx = createContext(null);

let seq = 0;
const logEntry = (s, caseId, action) => ({
  id: `h${Date.now()}-${seq++}`,
  at: new Date().toISOString(),
  userId: s.session,
  caseId,
  action,
});

const caseName = (s, id) => s.cases.find((c) => c.id === id).name;

function reducer(s, a) {
  const now = new Date().toISOString();
  switch (a.type) {
    case 'HYDRATE':
      return { ...a.data, session: null };
    case 'LOGIN':
      return { ...s, session: a.userId };
    case 'LOGIN_GOOGLE':
      return { ...s, users: s.users.some((u) => u.id === a.user.id) ? s.users : [...s.users, a.user], session: a.user.id };
    case 'LOGOUT':
      return { ...s, session: null };
    case 'RESET':
      return { ...buildSeed(), session: s.session };

    case 'OPEN_DOC': {
      const d = s.docs.find((x) => x.id === a.id);
      if (!d || d.review.status !== 'sin_revisar' || d.completitud < 100) return s;
      return {
        ...s,
        docs: s.docs.map((x) => (x.id === a.id ? { ...x, review: { ...x.review, status: 'en_revision', by: s.session, at: now } } : x)),
        history: [logEntry(s, d.caseId, `Abrió para revisión ${DOC_LABEL[d.type]} (${caseName(s, d.caseId)})`), ...s.history],
      };
    }

    case 'APPROVE_DOC': {
      const d = s.docs.find((x) => x.id === a.id);
      // Un solo rechazo bloquea el documento; la aceptación exige conclusiones.
      if (!d || d.review.status === 'rechazado' || d.completitud < 100 || !a.text.trim()) return s;
      return {
        ...s,
        docs: s.docs.map((x) => (x.id === a.id ? { ...x, review: { status: 'aprobado', by: s.session, at: now, reason: '', conclusion: a.text.trim() } } : x)),
        history: [logEntry(s, d.caseId, `Aprobó ${DOC_LABEL[d.type]} (${caseName(s, d.caseId)}). Conclusión: ${a.text.trim()}`), ...s.history],
      };
    }

    case 'REJECT_DOC': {
      const d = s.docs.find((x) => x.id === a.id);
      if (!d || d.review.status === 'rechazado' || !a.text.trim()) return s;
      return {
        ...s,
        docs: s.docs.map((x) => (x.id === a.id ? { ...x, review: { status: 'rechazado', by: s.session, at: now, reason: a.text.trim(), conclusion: '' } } : x)),
        history: [logEntry(s, d.caseId, `Rechazó ${DOC_LABEL[d.type]} (${caseName(s, d.caseId)}). Motivo: ${a.text.trim()}`), ...s.history],
      };
    }

    case 'DECIDE_CASE': {
      const ds = docsOf(s.docs, a.caseId);
      if (!a.text.trim()) return s;
      if (a.value === 'aceptada' && (!canAcceptCase(ds) || ds.some((d) => d.review.status === 'rechazado'))) return s;
      return {
        ...s,
        cases: s.cases.map((c) => (c.id === a.caseId ? { ...c, decision: { value: a.value, by: s.session, at: now, text: a.text.trim() } } : c)),
        history: [
          logEntry(s, a.caseId, `${a.value === 'aceptada' ? 'Aceptó' : 'Rechazó'} la prefactibilidad del caso ${caseName(s, a.caseId)}. ${a.value === 'aceptada' ? 'Conclusión' : 'Motivo'}: ${a.text.trim()}`),
          ...s.history,
        ],
      };
    }
    default:
      return s;
  }
}

const OLD_KEYS = ['3b-prefactibilidad-v1', '3b-prefactibilidad-v2']; // versiones antiguas guardaban contraseñas en claro

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, null, buildSeed);
  const [ready, setReady] = useState(false);

  // Carga: se descifra lo guardado (AES-GCM). La sesión nunca se persiste.
  useEffect(() => {
    (async () => {
      try {
        OLD_KEYS.forEach((k) => localStorage.removeItem(k));
        const raw = localStorage.getItem(KEY);
        if (raw) dispatch({ type: 'HYDRATE', data: await decryptJSON(raw) });
      } catch (e) { /* datos ilegibles: se parte del seed */ }
      setReady(true);
    })();
  }, []);

  // Guardado cifrado en reposo
  useEffect(() => {
    if (!ready) return;
    (async () => {
      try { localStorage.setItem(KEY, await encryptJSON({ ...state, session: null })); } catch (e) { /* ignorar */ }
    })();
  }, [state, ready]);

  if (!ready) return null;
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export const useStore = () => useContext(Ctx);
