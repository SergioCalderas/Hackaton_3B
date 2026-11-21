# Hackaton 3B · Prefactibilidad (frontend)

Sistema para evaluar la prefactibilidad de casos de expansión. Tiene tres piezas: el **frontend** (React + Vite, esta carpeta), el **backend** Flask (`server/app.py`, login y pipeline de documentos) y la **base de datos** Postgres en Supabase. Los casos y documentos del dashboard aún son datos de demostración (`src/lib/seed.js`), cuyo estado se guarda cifrado en el navegador; el inicio de sesión por correo ya consulta la tabla `usuarios`.

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
4. Arranca también el backend (el login por correo lo necesita; ver *Backend* más abajo).
5. Abre la dirección que imprime la terminal (normalmente https://localhost:5173 — solo HTTPS) e inicia sesión con un usuario de la tabla `usuarios`.

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

## Usuarios

El login por correo y contraseña lo valida el backend contra la tabla `usuarios` (contraseñas con bcrypt; `tipo_usuario` 1 = administrador, 2 = gestor). Pide las credenciales al equipo de base de datos. Las cuentas demo que antes vivían en `src/lib/seed.js` ya no se usan para entrar.

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

## Pipeline de documentos (filtro de calidad)

El backend (`server/app.py`) registra el pipeline de `procesamiento/`. Toma los documentos de la base
de datos (no del front) y responde si cada uno está `APROBADO`, en `REVISION_MANUAL` o hay que
`VOLVER_A_SUBIR`, con el motivo. Endpoints, variables de entorno y diseño en [`CLAUDE.md`](CLAUDE.md);
detalle del filtro en [`filtro_calidad/README.md`](filtro_calidad/README.md).

### Extracción y validación cruzada (Fase 2)

Los documentos `APROBADO` pasan a la **extracción de campos**: clave catastral, propietario, dirección,
número oficial, superficie, folio, fechas… Cada campo trae su página y el fragmento de texto de donde salió.
Después se hace la **validación cruzada** entre los documentos del expediente: si la clave catastral o el
propietario no coinciden, el semáforo queda en rojo; si difieren la superficie, el número oficial o la
dirección, en amarillo. El semáforo lo sigue decidiendo `procesamiento/dictamen.py` y el LLM solo redacta.
La lógica vive en [`ocr_pipeline/`](ocr_pipeline/README.md); `procesamiento/etapa_extraccion.py` y
`procesamiento/etapa_verificacion.py` son adaptadores delgados.

- **Requisito extra del backend:** Tesseract con `tessdata/` (instrucciones en `CLAUDE.md` §8).
- **En el front:** pestaña *Filtro de documentos* → *Verificar* (ahora corre Fase 1 + Fase 2) → *Usar en
  dictamen* en un documento de cada tipo → *Generar dictamen*. Las observaciones `VC-xx` muestran el valor
  de cada documento.
- **Pruebas:** `python -m pytest`, sin OCR ni BD.
- **Modo independiente** (batch, API FastAPI con `/docs` y la página de prueba `/demo`): ver
  [`ocr_pipeline/README.md`](ocr_pipeline/README.md).

## Backend

```bash
python -m venv .venv
.venv\Scriptsctivate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r server/requirements.txt
python server/app.py              # escucha en http://127.0.0.1:5000
```

Necesita un `.env` en la raíz con `DATABASE_URL` (y las demás variables de la sección *Base de datos*). En desarrollo, Vite reenvía `/api` a ese puerto (`vite.config.js`), así que el navegador siempre habla con un único origen HTTPS.

## Despliegue

### Arquitectura recomendada

```
Navegador ──HTTPS──> Servidor web / proxy (443)
                       ├─ /      -> archivos estáticos de dist/ (frontend)
                       └─ /api   -> backend Flask (127.0.0.1:5000)  ──> Supabase (Postgres)
```

Frontend y API deben servirse **bajo el mismo dominio**: la política de seguridad (CSP) solo permite `connect-src 'self'` y no hace falta configurar CORS.

### Pasos

1. **Variables del frontend** (se incrustan al compilar, no son secretas): crea `.env.production` con `VITE_GOOGLE_CLIENT_ID` y `VITE_GOOGLE_ALLOWED` (ver `.env.example`).
2. **Compilar el frontend:** `npm ci && npm run build`. El resultado queda en `dist/`; el build ya inyecta la CSP en `index.html` y copia `public/` (incluye `_headers`).
3. **Publicar `dist/`** en un hosting estático con HTTPS (Netlify, Cloudflare Pages, Nginx, etc.). Netlify y Cloudflare Pages leen `_headers`; en otro servidor replica esas cabeceras, **incluido HSTS** (`Strict-Transport-Security`). Redirige todo http a https.
4. **Backend:** instala las dependencias y corre Flask con un servidor de producción, no con `python server/app.py`: `gunicorn -w 2 -b 127.0.0.1:5000 server.app:app` en Linux o `waitress-serve --listen=127.0.0.1:5000 server.app:app` en Windows (instala el que uses). Colócalo detrás del proxy con HTTPS y enruta `/api` hacia él.
5. **Secretos:** `DATABASE_URL`, `DB_PASSWORD`, llaves de Supabase, etc., solo como variables de entorno del servidor (o `.env` fuera de git). Nunca en el frontend.
6. **Google Sign-In:** en Google Cloud Console agrega el dominio de producción (con `https://`) como *origen JS autorizado*. Google no acepta IPs. Verifica además el token en el backend.
7. **Comprobar:** abre el dominio, confirma el candado HTTPS, el login y que `/api/login` responde.

### Pendientes antes de producción

- Los **PDFs de `public/docs/` se sirven públicos** (cualquiera con la URL los descarga sin sesión). En producción deben salir del backend, con autenticación, o de un almacenamiento privado con URLs firmadas.
- Casos, documentos, aprobaciones e historial aún no se guardan en la base de datos: hoy viven en el navegador de cada persona y no se comparten.
- La ubicación del mapa debe leerse de `operacion_realizada.latitud/longitud`.
- Servir el backend con `debug` desactivado y limitar intentos de login.

### Demostración rápida sin desplegar

- **Misma red:** `npm run dev -- --host`, abrir el puerto 5173 en el firewall (PowerShell de administrador: `New-NetFirewallRule -DisplayName "Vite 3B" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow`) y entrar a `https://IP-DEL-PC:5173` (el navegador avisará del certificado).
- **Enlace público temporal:** `cloudflared tunnel --url https://localhost:5173 --no-tls-verify` da una dirección `https://….trycloudflare.com` válida. Cualquiera con el enlace puede verla (incluidos los PDFs); ciérralo al terminar.
