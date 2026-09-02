-- Esquema inicial del proyecto (se ejecuta solo en la primera
-- inicialización del volumen de datos de PostgreSQL).

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

CREATE SCHEMA IF NOT EXISTS monitoreo_vehiculos;

-- ── Reportes de telemetría de vehículos ──────────────────────
CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.vehicle_reports (
    id BIGSERIAL PRIMARY KEY,
    device_vehicle_id VARCHAR(50) NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    speed_kmh NUMERIC(6, 2) NOT NULL,
    fuel_level NUMERIC(6, 2) NOT NULL,

    CONSTRAINT chk_latitude CHECK (latitude BETWEEN 4.54568 AND 4.78418),
    CONSTRAINT chk_longitude CHECK (longitude BETWEEN -74.19391 AND -74.01404),
    CONSTRAINT chk_speed CHECK (speed_kmh >= 0),
    CONSTRAINT chk_fuel_level CHECK (fuel_level BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_vehicle_reports_device_vehicle_id
    ON monitoreo_vehiculos.vehicle_reports (device_vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_reports_vehicle_timestamp
    ON monitoreo_vehiculos.vehicle_reports (device_vehicle_id, reported_at);
CREATE INDEX IF NOT EXISTS idx_vehicle_reports_timestamp
    ON monitoreo_vehiculos.vehicle_reports (reported_at);

-- ── Geofences ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.geofences (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    geofence_type VARCHAR(50) NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mode VARCHAR(20) NOT NULL DEFAULT 'manual',
    monitor_variable NUMERIC(6, 2) NOT NULL DEFAULT 0,

    CONSTRAINT chk_geofences_type
        CHECK (geofence_type IN ('fuel', 'urban', 'high_accident', 'restricted', 'other')),
    CONSTRAINT chk_geofences_mode
        CHECK (mode IN ('manual', 'random')),
    CONSTRAINT chk_geofences_monitor_variable
        CHECK (monitor_variable >= 0)
);

CREATE INDEX IF NOT EXISTS idx_geofences_geom
    ON monitoreo_vehiculos.geofences USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_geofences_active
    ON monitoreo_vehiculos.geofences (active);
CREATE INDEX IF NOT EXISTS idx_geofences_type_mode
    ON monitoreo_vehiculos.geofences (geofence_type, mode);

-- ── Alertas de exceso de velocidad ───────────────────────────
CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.high_speed_alerts (
    id BIGSERIAL PRIMARY KEY,
    vehicle_report_id BIGINT NOT NULL,
    geofence_id BIGINT NOT NULL,
    device_vehicle_id VARCHAR(50) NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    speed_kmh NUMERIC(6, 2) NOT NULL,
    speed_limit_kmh NUMERIC(6, 2) NOT NULL,
    excess_speed_kmh NUMERIC(6, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    geom geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_high_speed_alerts_geom
    ON monitoreo_vehiculos.high_speed_alerts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_high_speed_alerts_device
    ON monitoreo_vehiculos.high_speed_alerts (device_vehicle_id);

-- ── Geofences de ejemplo (modo manual) ───────────────────────
INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, monitor_variable)
VALUES
    ('Recarga Américas y Teusaquillo', 'Zona manual de recarga', 'fuel',
     ST_MakeEnvelope(-74.10483, 4.59424, -74.07254, 4.63757, 4326), 'manual', 1.50),
    ('Recarga Occidente', 'Zona manual adicional de recarga', 'fuel',
     ST_MakeEnvelope(-74.16000, 4.65000, -74.14000, 4.67000, 4326), 'manual', 2.00),
    ('Alta Accidentalidad Bosa-Soacha', 'Zona de alta accidentalidad', 'high_accident',
     ST_MakeEnvelope(-74.18465, 4.56888, -74.14283, 4.59657, 4326), 'manual', 50),
    ('Alta Accidentalidad Engativá', 'Zona de alta accidentalidad', 'high_accident',
     ST_MakeEnvelope(-74.14262, 4.68521, -74.08016, 4.73686, 4326), 'manual', 30);
