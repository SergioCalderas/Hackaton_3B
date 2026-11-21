// Filtro de calidad (Fase 1 del pipeline de documentos).
// Los documentos viven en la BD (operacion_realizada + escrituras/predial/suelo/aliniamiento);
// el backend los lee de ahí, el front solo consulta resultados y pide verificar.
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';

// Caso del front -> operación en la BD (los 8 casos se cargaron en el mismo orden).
export const operacionDeCaso = (caseId) => Number(String(caseId).replace(/\D/g, '')) || null;

// Tipo de documento del front -> tabla de la BD. La BD junta alineamiento y número oficial.
export const TABLA_DE_TIPO = {
  escrituras: 'escrituras',
  predial: 'predial',
  uso_suelo: 'suelo',
  alineamiento: 'aliniamiento',
  numero_oficial: 'aliniamiento',
};

export const FILTRO_LABEL = {
  APROBADO: 'Aprobado por filtro',
  REVISION_MANUAL: 'Revisión manual',
  VOLVER_A_SUBIR: 'Volver a subir',
  SIN_VERIFICAR: 'Sin verificar',
  SIN_ARCHIVO: 'Sin archivo',
};
export const FILTRO_TONE = {
  APROBADO: 'green', REVISION_MANUAL: 'amber', VOLVER_A_SUBIR: 'red', SIN_VERIFICAR: 'gray', SIN_ARCHIVO: 'navy',
};
export const EXPEDIENTE_LABEL = {
  EN_REVISION: 'Expediente completo · pasa a extracción',
  NO_VALIDADO: 'Expediente no validado',
  SIN_VERIFICAR: 'Aún no se ha verificado',
};

async function pedir(url, opts) {
  const r = await fetch(url, { headers: { Accept: 'application/json' }, ...opts });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.error || `Error ${r.status}`);
  return datos;
}

const Ctx = createContext(null);

export function FiltroProvider({ children }) {
  const [ops, setOps] = useState({});          // operacion_id -> resumen
  const [error, setError] = useState(null);
  const [corriendo, setCorriendo] = useState({}); // operacion_id -> true

  const cargar = useCallback(async () => {
    try {
      const lista = await pedir('/api/operaciones');
      setOps(Object.fromEntries(lista.map((o) => [o.operacion_id, o])));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const verificar = useCallback(async (operacionId) => {
    setCorriendo((c) => ({ ...c, [operacionId]: true }));
    try {
      await pedir(`/api/operaciones/${operacionId}/verificar?hasta=calidad`, { method: 'POST' });
      const o = await pedir(`/api/operaciones/${operacionId}`);
      setOps((prev) => ({ ...prev, [operacionId]: o }));
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setCorriendo((c) => ({ ...c, [operacionId]: false }));
    }
  }, []);

  return <Ctx.Provider value={{ ops, error, corriendo, verificar, recargar: cargar }}>{children}</Ctx.Provider>;
}

export function useFiltro(caseId) {
  const ctx = useContext(Ctx);
  const opId = operacionDeCaso(caseId);
  const op = ctx.ops[opId] || null;
  const docDe = (tipo) => {
    const d = op && op.documentos[TABLA_DE_TIPO[tipo]];
    if (!d) return null;
    const estado = !d.tiene_archivo ? 'SIN_ARCHIVO' : d.filtro ? d.filtro.estado : 'SIN_VERIFICAR';
    return { ...d, estado };
  };
  return {
    opId,
    op,
    docDe,
    error: ctx.error,
    corriendo: !!ctx.corriendo[opId],
    verificar: () => ctx.verificar(opId),
  };
}

export const FiltroPill = ({ estado }) => (
  <span className={`pill pill-${FILTRO_TONE[estado] || 'gray'}`}>{FILTRO_LABEL[estado] || estado}</span>
);
