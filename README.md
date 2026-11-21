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
4. Abre la dirección que imprime la terminal (normalmente https://localhost:5173 — solo HTTPS) e inicia sesión con una cuenta de demostración.

Para generar la versión de producción: `npm run build` (queda en `dist/`).

### Canal HTTPS de confianza (sin advertencias)

Una sola vez por equipo: instala [mkcert](https://github.com/FiloSottile/mkcert) (`winget install FiloSottile.mkcert`) y ejecuta `npm run https:setup`. Crea una autoridad local de confianza y un certificado para `localhost` en `certs/` (no se sube a git). Windows pedirá confirmar la instalación de la autoridad. Sin este paso, el servidor usa un certificado autofirmado y el navegador mostrará una advertencia.

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

## Base de datos

Postgres en el proyecto de Supabase **Hackaton**. La conexión de cada quien va en un `.env` local (no se sube a Git): `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `DB_PASSWORD` y `DATABASE_URL`.

`contrasena` y `direccion_memoria` guardan solo un hash bcrypt (`$2a$` o `$2b$`). No se puede volver a leer el valor original.

### usuarios

Inicio de sesión. `tipo_usuario`: `1` administrador, `2` gestor.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `bigint` | Clave primaria |
| `nombre` | `varchar(100)` | Obligatorio |
| `apellidos` | `varchar(150)` | Obligatorio |
| `correo` | `varchar(255)` | Obligatorio y único |
| `contrasena` | `text` | Hash bcrypt |
| `tipo_usuario` | `smallint` | `1` o `2` |

### escrituras, suelo, predial, aliniamiento

Las cuatro tablas tienen las mismas columnas. `estado`: `0` mal, `1` bien.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `bigint` | Clave primaria |
| `direccion_memoria` | `text` | Hash bcrypt del dato sensible |
| `direccion_real` | `varchar(255)` | Obligatorio |
| `propietario` | `varchar(200)` | Obligatorio |
| `numero_oficial` | `varchar(50)` | Obligatorio |
| `superficie` | `numeric(14,2)` | Obligatorio |
| `estado` | `smallint` | `0` o `1` |

### operacion_realizada

Una operación junta un documento de cada tabla. Cada documento solo puede usarse en una operación. `latitud` y `longitud` están en grados decimales (WGS84) para el mapa. `estado` es el semáforo: `1` rojo, `2` amarillo, `3` verde.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `bigint` | Clave primaria |
| `escritura_id` | `bigint` | Única. Referencia `escrituras(id)` |
| `predial_id` | `bigint` | Única. Referencia `predial(id)` |
| `suelo_id` | `bigint` | Única. Referencia `suelo(id)` |
| `alineamiento_id` | `bigint` | Única. Referencia `aliniamiento(id)` |
| `latitud` | `numeric(9,6)` | De `-90` a `90` |
| `longitud` | `numeric(9,6)` | De `-180` a `180` |
| `estado` | `smallint` | `1`, `2` o `3` |
