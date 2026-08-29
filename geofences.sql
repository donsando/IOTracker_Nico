-- Referencia del esquema de geofences (debe coincidir con la tabla real).
-- La tabla existente usa la columna "monitor_variable" como valor numérico
-- genérico por geofence (tasa de recarga para fuel, peso para high_accident, etc.).

CREATE SCHEMA IF NOT EXISTS monitoreo_vehiculos;

CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.geofences (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    geofence_type VARCHAR(50) NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mode VARCHAR(20) NOT NULL DEFAULT 'manual',
    monitor_variable NUMERIC(10, 4) NOT NULL DEFAULT 0,

    CONSTRAINT chk_geofences_type
        CHECK (geofence_type IN ('fuel', 'urban', 'high_accident', 'restricted', 'other')),
    CONSTRAINT chk_geofences_mode
        CHECK (mode IN ('manual', 'random')),
    CONSTRAINT chk_geofences_monitor_variable
        CHECK (monitor_variable >= 0)
);

CREATE INDEX IF NOT EXISTS idx_geofences_geom
ON monitoreo_vehiculos.geofences
USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_geofences_active
ON monitoreo_vehiculos.geofences (active);

CREATE INDEX IF NOT EXISTS idx_geofences_type_mode
ON monitoreo_vehiculos.geofences (geofence_type, mode);

-- ── Ejemplos de inserción ──────────────────────────────────────
-- INSERT INTO monitoreo_vehiculos.geofences
--     (name, description, geofence_type, geom, mode, monitor_variable)
-- VALUES (
--     'Recarga Américas y Teusaquillo',
--     'Zona manual de recarga',
--     'fuel',
--     ST_MakeEnvelope(-74.10483, 4.59424, -74.07254, 4.63757, 4326),
--     'manual',
--     1.50
-- );
