// Datos de demostración (sustituyen al backend, que aún no existe).
export const DOC_TYPES = [
  { key: 'escrituras', label: 'Escrituras' },
  { key: 'uso_suelo', label: 'Uso de suelo' },
  { key: 'predial', label: 'Predial' },
  { key: 'alineamiento', label: 'Alineamiento' },
  { key: 'numero_oficial', label: 'Número oficial' },
];

export const CHECKS = [
  { key: 'direccion', label: 'Dirección del inmueble' },
  { key: 'propietario', label: 'Propietario o titular' },
  { key: 'superficie', label: 'Superficies' },
  { key: 'numero_oficial', label: 'Número oficial' },
  { key: 'predio', label: 'Identificación del predio' },
];

export const USERS = [
  { id: 'u1', name: 'Mariana Torres', email: 'gestor@3b.mx', password: '3b123', role: 'gestor' },
  { id: 'u2', name: 'Luis Hernández', email: 'gestor2@3b.mx', password: '3b123', role: 'gestor' },
  { id: 'u3', name: 'Paola Ríos', email: 'admin@3b.mx', password: '3b123', role: 'admin' },
];

const ago = (h) => new Date(Date.now() - h * 3600e3).toISOString();

const FILES = {
  escrituras: 'Escritura',
  uso_suelo: 'Licencia de Uso de Suelo',
  predial: 'Predial 2025',
  alineamiento: 'Alineamiento',
  numero_oficial: 'Número Oficial',
};

// Por documento: c = completitud (0-100), fails/warns = {check: nota}, st = estado de revisión, text = conclusión o motivo
const CASES = [
  {
    id: 'c1', name: 'Melchor Ocampo III', address: 'Melchor Ocampo, Estado de México', owner: 'Inmobiliaria Ocampo S.A. de C.V.', lat: 19.7106, lng: -99.1389,
    decision: { value: 'aceptada', by: 'u1', at: ago(30), text: 'Documentación congruente. Uso comercial minisúper vigente.' },
    docs: {
      escrituras: { st: 'aprobado', text: 'Titularidad y superficie correctas.' },
      uso_suelo: { st: 'aprobado', text: 'Licencia vigente.' },
      predial: { st: 'aprobado', text: 'Pago 2025 al corriente.' },
      alineamiento: { st: 'aprobado', text: 'Sin afectaciones.' },
      numero_oficial: { st: 'aprobado', text: 'Coincide con escritura.' },
    },
  },
  {
    id: 'c2', name: 'Sor Juana', address: 'Av. Sor Juana Inés de la Cruz, Tecámac', owner: 'Desarrollos Sor Juana S.A.', lat: 19.7133, lng: -98.969,
    docs: {
      escrituras: { st: 'aprobado', text: 'Correcta.' },
      uso_suelo: { st: 'aprobado', text: 'Vigente.' },
      predial: { st: 'aprobado', text: 'Al corriente.' },
      alineamiento: { st: 'en_revision', fails: { superficie: 'Alineamiento indica 412 m², escritura indica 380 m².' } },
      numero_oficial: {},
    },
  },
  { id: 'c3', name: 'Tepeji del Río 5', address: 'Tepeji del Río de Ocampo, Hidalgo', owner: 'Grupo Tepeji S.A.', lat: 19.905, lng: -99.344, docs: {} },
  {
    id: 'c4', name: 'Tultepec Insurgentes', address: 'Av. Insurgentes, Tultepec', owner: 'Carlos Medina Ruiz', lat: 19.685, lng: -99.128,
    docs: {
      escrituras: { st: 'aprobado', text: 'Correcta.' },
      predial: { st: 'rechazado', fails: { propietario: 'Predial a nombre de Ana Medina; escritura a nombre de Carlos Medina.' }, text: 'Titular del predial distinto al de la escritura.' },
    },
  },
  {
    id: 'c5', name: 'Tultepec San Juan', address: 'San Juan, Tultepec', owner: 'Inmuebles San Juan S.C.', lat: 19.69, lng: -99.1,
    docs: {
      uso_suelo: { c: 0 },
      alineamiento: { c: 60, warns: { predio: 'Falta hoja 2 con la clave catastral.' } },
      escrituras: { st: 'en_revision' },
    },
  },
  {
    id: 'c6', name: 'Paseos de la Pradera', address: 'Paseos de la Pradera, Hidalgo', owner: 'Pradera Desarrollos S.A.', lat: 20.101, lng: -98.759,
    docs: {
      escrituras: { st: 'aprobado', text: 'Relotificación inscrita correctamente.' },
      uso_suelo: { st: 'aprobado', text: 'Antecedente vigente.' },
      predial: { st: 'aprobado', text: 'Sin adeudo.' },
      alineamiento: { st: 'aprobado', text: 'Sin afectaciones.' },
      numero_oficial: { st: 'aprobado', text: 'Coincide.' },
    },
  },
  {
    id: 'c7', name: 'QUMA', address: 'Zona QUMA, Estado de México', owner: 'QUMA Inmobiliaria S.A.', lat: 19.65, lng: -99.21,
    docs: {
      escrituras: { fails: { direccion: 'Calle Hidalgo 45 en escritura vs. Hidalgo 54 en predial.', numero_oficial: 'Escritura: 45, constancia: 54.' } },
      predial: { warns: { direccion: 'Dirección abreviada, confirmar.' } },
    },
  },
  {
    id: 'c8', name: 'Villa del Carbón 3', address: 'Villa del Carbón, Estado de México', owner: 'Carbón Retail S.A.', lat: 19.733, lng: -99.471,
    docs: {
      escrituras: { st: 'aprobado', text: 'Correcta.' },
      predial: { st: 'aprobado', text: 'Pago vigente.' },
    },
  },
];

function buildDoc(c, type, i) {
  const s = c.docs[type] || {};
  const comp = s.c ?? 100;
  const checks = {};
  const notes = {};
  CHECKS.forEach((k) => {
    if (s.fails && s.fails[k.key]) { checks[k.key] = 'fail'; notes[k.key] = s.fails[k.key]; }
    else if (s.warns && s.warns[k.key]) { checks[k.key] = 'warn'; notes[k.key] = s.warns[k.key]; }
    else if (comp < 100) { checks[k.key] = 'warn'; notes[k.key] = 'No se pudo evaluar: documentación incompleta.'; }
    else { checks[k.key] = 'ok'; notes[k.key] = 'Coincide con el resto de la documentación.'; }
  });
  const st = s.st || 'sin_revisar';
  const reviewed = st !== 'sin_revisar';
  return {
    id: `${c.id}-${type}`,
    caseId: c.id,
    type,
    file: `${FILES[type]} ${c.name}.pdf`,
    completitud: comp,
    checks,
    notes,
    versions: [
      { v: 1, at: ago(200 + i * 5), by: 'Carga inicial' },
      ...(i % 2 === 0 ? [{ v: 2, at: ago(120 + i * 3), by: 'Corrección de datos' }] : []),
    ],
    review: {
      status: st,
      by: reviewed ? (i % 2 ? 'u2' : 'u1') : null,
      at: reviewed ? ago(10 + i * 4) : null,
      reason: st === 'rechazado' ? s.text || '' : '',
      conclusion: st === 'aprobado' ? s.text || '' : '',
    },
  };
}

export function buildSeed() {
  const cases = CASES.map(({ docs, ...c }) => ({ ...c, decision: c.decision || null }));
  const docs = CASES.flatMap((c) => DOC_TYPES.map((t, i) => buildDoc(c, t.key, i)));
  const dname = Object.fromEntries(DOC_TYPES.map((t) => [t.key, t.label]));
  const history = [];
  let n = 0;
  docs.forEach((d) => {
    if (d.review.status === 'sin_revisar') return;
    const cname = CASES.find((c) => c.id === d.caseId).name;
    const label = { aprobado: 'Aprobó', rechazado: 'Rechazó', en_revision: 'Abrió para revisión' }[d.review.status];
    history.push({ id: `h${n++}`, at: d.review.at, userId: d.review.by, caseId: d.caseId, action: `${label} ${dname[d.type]} (${cname})` });
  });
  cases.filter((c) => c.decision).forEach((c) =>
    history.push({ id: `h${n++}`, at: c.decision.at, userId: c.decision.by, caseId: c.id, action: `Aceptó la prefactibilidad del caso ${c.name}` })
  );
  history.sort((a, b) => b.at.localeCompare(a.at));
  return { users: USERS, cases, docs, history, session: null };
}
