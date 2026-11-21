# Hackaton 3B · Prefactibilidad (frontend)

Frontend en React + Vite para evaluar la prefactibilidad de casos de expansión. Sin backend: los datos de demostración viven en `src/lib/seed.js` y el estado se guarda en `localStorage`.

## Cómo abrir el frontend

1. Instala [Node.js LTS](https://nodejs.org) (incluye `npm`). En Windows: `winget install OpenJS.NodeJS.LTS` y reinicia la terminal.
2. Clona el repositorio y entra a la carpeta:
   ```bash
   git clone https://github.com/SergioCalderas/Hackaton_3B.git
   cd Hackaton_3B
   git checkout SabrinaMichaus   # o main, ambas tienen el frontend
   ```
3. Instala dependencias y arranca:
   ```bash
   npm install
   npm run dev
   ```
4. Abre la dirección que imprime la terminal (normalmente https://localhost:5173 — usa HTTPS con certificado local autofirmado: acepta la advertencia del navegador la primera vez) e inicia sesión con una cuenta de demostración.

Para generar la versión de producción: `npm run build` (queda en `dist/`).

## Inicio de sesión con Google

1. En Google Cloud Console crea un *ID de cliente de OAuth* (aplicación web) y agrega `https://localhost:5173` como origen JS autorizado.
2. Copia `.env.example` a `.env.local` y completa `VITE_GOOGLE_CLIENT_ID` y `VITE_GOOGLE_ALLOWED` (correo:rol, rol = `admin` o `gestor`).
3. Reinicia `npm run dev`. Solo entran las cuentas de la lista.

> El token de Google debe verificarse también en el backend (firma, `aud`, `exp`). En el frontend solo se valida emisor, audiencia, expiración, nonce y correo verificado.

## Seguridad

- **En tránsito:** HTTPS forzado (servidor de desarrollo solo HTTPS, redirección http→https fuera de localhost, `upgrade-insecure-requests` y CSP en el build, cabeceras de seguridad). En producción, configurar HSTS en el hosting (ver `public/_headers`).
- **En reposo:** los datos guardados en el navegador se cifran con AES-GCM (Web Crypto); la clave es no extraíble y vive en IndexedDB. Las contraseñas demo solo existen como hash. La base de datos ya guarda datos hasheados (fuera de este alcance).
- **En uso:** la sesión no se persiste, se cierra tras 10 min de inactividad, no hay contraseñas en memoria del estado y el contenido se renderiza escapado (React) con CSP restrictiva.

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
- El mapa (Google Maps) muestra la ubicación del caso seleccionado en el dashboard y permite abrirla en Google Maps.
- El administrador ve historial (hora, usuario, cambio), las 5 tablas de documentos con versiones y métricas por gestor.
