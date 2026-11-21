-- PROPUESTA (no se ha ejecutado). Revisar con quien administra la BD de Supabase "Hackaton".
--
-- 1) Columna con el archivo en cada tabla de documentos.
--    Opción recomendada: ruta/URL en Supabase Storage (la BD no crece con los PDFs).
--    El pipeline también acepta bytea o rutas relativas a public/ (p. ej. 'docs/predial/caso-001.pdf').
--    Si se usa otro nombre de columna, configurar FILTRO_COLUMNA_ARCHIVO en el .env del servidor.

ALTER TABLE escrituras   ADD COLUMN IF NOT EXISTS archivo text;
ALTER TABLE predial      ADD COLUMN IF NOT EXISTS archivo text;
ALTER TABLE suelo        ADD COLUMN IF NOT EXISTS archivo text;
ALTER TABLE aliniamiento ADD COLUMN IF NOT EXISTS archivo text;

-- 2) Resultados del filtro (se llenan si FILTRO_GUARDAR_RESULTADOS=1).
--    Una fila por ejecución: queda la bitácora (RNF-02 / RNF-05).

CREATE TABLE IF NOT EXISTS filtro_resultados (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tabla          varchar(20)  NOT NULL CHECK (tabla IN ('escrituras','predial','suelo','aliniamiento')),
    documento_id   bigint       NOT NULL,
    sha256         char(64),
    estado         varchar(20)  NOT NULL CHECK (estado IN ('APROBADO','REVISION_MANUAL','VOLVER_A_SUBIR')),
    motivo         text,
    mensaje        text,
    tipo_detectado varchar(20),
    detalle        jsonb,
    version_reglas varchar(40),
    creado_en      timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS filtro_resultados_doc ON filtro_resultados (tabla, documento_id, creado_en DESC);
