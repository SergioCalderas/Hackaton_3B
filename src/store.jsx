import React, { createContext, useContext, useEffect, useReducer } from 'react';
import { buildSeed } from './lib/seed.js';
import { DOC_LABEL, docsOf, canAcceptCase } from './lib/selectors.js';

const KEY = '3b-prefactibilidad-v2';
const Ctx = createContext(null);

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* sin almacenamiento */ }
  return buildSeed();
}

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
    case 'LOGIN': {
      const user = { ...a.user };
      delete user.password;
      const users = s.users.some((u) => String(u.id) === String(user.id))
        ? s.users.map((u) => (String(u.id) === String(user.id) ? user : u))
        : [...s.users, user];
      return { ...s, session: user.id, users };
    }
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

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, null, load);
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignorar */ }
  }, [state]);
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export const useStore = () => useContext(Ctx);
