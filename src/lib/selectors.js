import { DOC_TYPES, RECEIVED_DAYS_AGO } from './seed.js';

export const DOC_LABEL = Object.fromEntries(DOC_TYPES.map((t) => [t.key, t.label]));

export const docsOf = (docs, caseId) => docs.filter((d) => d.caseId === caseId);

// Estado visible de un documento: faltante si la documentación no está al 100%
export function docState(d) {
  if (d.review.status === 'rechazado') return 'rechazado';
  if (d.completitud < 100) return 'faltante';
  return d.review.status;
}

// Semáforo global del documento según sus 5 validaciones
export function docSemaphore(d) {
  const v = Object.values(d.checks);
  if (v.includes('fail')) return 'fail';
  if (v.includes('warn')) return 'warn';
  return 'ok';
}

export function caseStatus(c, ds) {
  if (c.decision && c.decision.value === 'aceptada') return 'aceptada';
  if ((c.decision && c.decision.value === 'rechazada') || ds.some((d) => d.review.status === 'rechazado')) return 'rechazada';
  if (ds.some((d) => d.review.status !== 'sin_revisar')) return 'en_revision';
  return 'sin_revisar';
}

export const approvedCount = (ds) => ds.filter((d) => d.review.status === 'aprobado').length;
export const TOTAL_DOCS = DOC_TYPES.length;
export const reviewProgress = (ds) => Math.round((approvedCount(ds) / TOTAL_DOCS) * 100);
export const completeness = (ds) => Math.round(ds.reduce((a, d) => a + d.completitud, 0) / (ds.length || 1));

export const canAcceptCase = (ds) =>
  ds.length === TOTAL_DOCS && ds.every((d) => d.completitud === 100 && d.review.status === 'aprobado');

export function docKpis(docs) {
  const k = { aprobado: 0, en_revision: 0, rechazado: 0, sin_revisar: 0, faltante: 0, total: docs.length };
  docs.forEach((d) => {
    const s = docState(d);
    k[s] += 1;
  });
  return k;
}

export function caseKpis(cases, docs) {
  const k = { aceptada: 0, en_revision: 0, rechazada: 0, sin_revisar: 0, total: cases.length };
  cases.forEach((c) => {
    k[caseStatus(c, docsOf(docs, c.id))] += 1;
  });
  return k;
}

export const STATUS_LABEL = {
  sin_revisar: 'Sin revisar',
  en_revision: 'En revisión',
  aprobado: 'Aprobado',
  rechazado: 'Rechazado',
  faltante: 'Faltante',
  aceptada: 'Aceptada',
  rechazada: 'Rechazada',
};

export const STATUS_TONE = {
  sin_revisar: 'gray',
  en_revision: 'amber',
  aprobado: 'green',
  rechazado: 'red',
  faltante: 'navy',
  aceptada: 'green',
  rechazada: 'red',
};

export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';

export const mapsLink = (c) => `https://www.google.com/maps/search/?api=1&query=${c.lat},${c.lng}`;
export const mapsEmbed = (c) => `https://maps.google.com/maps?q=${c.lat},${c.lng}&z=15&output=embed`;

export const fmtDay = (iso) => new Date(iso).toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });
export const fmtHour = (iso) => new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
export const fmtVigencia = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
export const vigenciaVencida = (iso) => new Date(`${iso}T23:59:59`) < new Date();

// Tipo de acción del historial (para color e icono)
export const KINDS = {
  aprobo: { label: 'Aprobó documento', icon: '✓', tone: 'green' },
  rechazo: { label: 'Rechazó documento', icon: '✕', tone: 'red' },
  abrio: { label: 'Abrió para revisión', icon: '👁', tone: 'amber' },
  caso_ok: { label: 'Aceptó caso', icon: '★', tone: 'navy' },
  caso_no: { label: 'Rechazó caso', icon: '⚑', tone: 'red' },
};
export function actionKind(action) {
  if (action.startsWith('Aceptó la prefactibilidad')) return 'caso_ok';
  if (action.startsWith('Rechazó la prefactibilidad')) return 'caso_no';
  if (action.startsWith('Aprobó')) return 'aprobo';
  if (action.startsWith('Rechazó')) return 'rechazo';
  return 'abrio';
}

// El sistema no muestra documentos faltantes/incompletos al gestor
export const visibleDocs = (ds) => ds.filter((d) => d.completitud === 100);
export const lastActivity = (c, ds) =>
  Math.max(0, c.decision ? Date.parse(c.decision.at) : 0, ...ds.map((d) => (d.review.at ? Date.parse(d.review.at) : 0)));

// Filtro por días desde la recepción del caso (days = 0 → todos)
export const DAY_OPTIONS = [{ v: 1, label: '1 día' }, { v: 3, label: '3 días' }, { v: 7, label: '7 días' }, { v: 15, label: '15 días' }, { v: 30, label: '30 días' }, { v: 0, label: 'Todos' }];
export const DEFAULT_DAYS = 3;
export const inDays = (c, days) => !days || (RECEIVED_DAYS_AGO[c.id] ?? 0) < days;
