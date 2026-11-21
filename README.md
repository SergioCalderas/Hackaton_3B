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
