# Hackaton 3B · Prefactibilidad (frontend)

Frontend en React + Vite para evaluar la prefactibilidad de casos de expansión. Sin backend: los datos de demostración viven en `src/lib/seed.js` y el estado se guarda en `localStorage`.

## Correr

```bash
npm install
npm run dev
```

## Cuentas de demostración (contraseña `3b123`)

| Rol | Correo |
|---|---|
| Gestor de expansión | gestor@3b.mx |
| Gestor de expansión | gestor2@3b.mx |
| Administrador | admin@3b.mx |

## Reglas implementadas

- Cada caso tiene 5 documentos: escrituras, uso de suelo, predial, alineamiento y número oficial.
- Cada documento tiene 5 validaciones en semáforo: dirección, propietario, superficies, número oficial e identificación del predio.
- El gestor puede abrir cualquier documento completo (100%), aunque no tenga fallas.
- Aceptar un documento exige conclusiones; denegarlo exige un motivo.
- Un solo rechazo bloquea el documento (ya no se puede aceptar) y el caso queda como rechazado.
- La prefactibilidad del caso solo se acepta con los 5 documentos aprobados al 100%.
- Estados de caso: sin revisar, en revisión, aceptado, rechazado.
- El mapa (Google Maps) muestra la ubicación del caso y permite abrirla en Google Maps.
- El administrador ve historial (hora, usuario, cambio), las 5 tablas de documentos con versiones y métricas por gestor.
