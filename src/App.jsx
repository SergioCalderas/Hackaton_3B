import React, { useEffect, useState } from 'react';
import { useStore } from './store.jsx';
import TopBar from './components/TopBar.jsx';
import DevSwitch from './components/DevSwitch.jsx';
import Login from './views/Login.jsx';
import Dashboard from './views/Dashboard.jsx';
import Cases from './views/Cases.jsx';
import CaseDetail from './views/CaseDetail.jsx';
import { DEFAULT_DAYS } from './lib/selectors.js';
import { AdminHistory, AdminSummary } from './views/Admin.jsx';
import Filtro from './views/Filtro.jsx';

const IDLE_MS = 10 * 60 * 1000;

const GESTOR_TABS = [
  { key: 'inicio', label: 'Dashboard' },
  { key: 'casos', label: 'Casos' },
  { key: 'filtro', label: 'Filtro de documentos' },
];
const ADMIN_TABS = [
  { key: 'resumen', label: 'Resumen' },
  { key: 'historial', label: 'Historial' },
  { key: 'filtro', label: 'Filtro de documentos' },
];

export default function App() {
  const { state, dispatch } = useStore();
  const user = state.users.find((u) => String(u.id) === String(state.session));
  const [tab, setTab] = useState('');
  const [caseId, setCaseId] = useState(null);
  const [days, setDays] = useState(DEFAULT_DAYS);

  useEffect(() => {
    if (user) { setTab(user.role === 'admin' ? 'resumen' : 'inicio'); setCaseId(null); }
  }, [user && user.id]);

  // Datos en uso: cierre de sesión automático tras 10 min sin actividad
  const uid = user && user.id;
  useEffect(() => {
    if (!uid) return undefined;
    let t;
    const reset = () => { clearTimeout(t); t = setTimeout(() => dispatch({ type: 'LOGOUT' }), IDLE_MS); };
    const evs = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    evs.forEach((e) => window.addEventListener(e, reset));
    reset();
    return () => { clearTimeout(t); evs.forEach((e) => window.removeEventListener(e, reset)); };
  }, [uid, dispatch]);

  if (!user) return <><DevSwitch /><Login /></>;

  const nav = (k) => { setTab(k); setCaseId(null); };
  const openCase = (id) => { setTab('casos'); setCaseId(id); };
  const isAdmin = user.role === 'admin';

  return (
    <div className="shell">
      <DevSwitch />
      <TopBar
        user={user}
        tabs={isAdmin ? ADMIN_TABS : GESTOR_TABS}
        current={tab}
        days={days}
        onDays={setDays}
        onNav={nav}
        onLogout={() => dispatch({ type: 'LOGOUT' })}
      />
      <main className="page">
        {isAdmin ? (
          <>
            {tab === 'resumen' && <AdminSummary />}
            {tab === 'historial' && <AdminHistory />}
            {tab === 'filtro' && <Filtro />}
          </>
        ) : (
          <>
            {tab === 'inicio' && <Dashboard user={user} days={days} onOpenCase={openCase} onNav={nav} />}
            {tab === 'casos' && (caseId ? <CaseDetail caseId={caseId} onBack={() => setCaseId(null)} /> : <Cases days={days} onOpenCase={setCaseId} />)}
            {tab === 'filtro' && <Filtro />}
          </>
        )}
      </main>
    </div>
  );
}
