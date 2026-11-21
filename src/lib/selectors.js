import { DOC_TYPES } from './seed.js';

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
export const reviewProgress = (ds) => Math.round((approvedCount(ds) / (ds.length || 1)) * 100);
export const completeness = (ds) => Math.round(ds.reduce((a, d) => a + d.completitud, 0) / (ds.length || 1));

export const canAcceptCase = (ds) =>
  ds.length > 0 && ds.every((d) => d.completitud === 100 && d.review.status === 'aprobado');

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
