create extension postgis;
create extension pg_routing;

--PgRouting lo utilizo para la construcción de la malla vial con nodos/aristas sobre la que los vehículos
--van a transitar

--Existe una zona geográfica sobre la que vamos a realizar el análisis espacial, en ella se recarga el
--comsbustible a un rate constante de ___, dentro de esta zona vamos a calcular
--el tiempo que pasan los vehículos allí dentro, si hay velocidad mayor a 40km/h y el nivel de combustible
--al entrar y al salir

set search_path to monitoreo_vehiculos, public;

--drop table monitoreo_vehiculos.vehicle_reports;
--select * from vehicle_reports_id_seq
--select setval(vehicle_reports_id_seq,1,false);

CREATE TABLE  monitoreo_vehiculos.vehicle_reports (
    id BIGSERIAL PRIMARY KEY,
    device_vehicle_id VARCHAR(50) NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    speed_kmh NUMERIC(6,2) NOT NULL,
    fuel_level NUMERIC(6,2) NOT NULL,

--Check para que la tabla colo acepte valores en el área urbana de bogotá
--El combustible está expresado en porcentaje
    CONSTRAINT chk_latitude CHECK (latitude BETWEEN 4.54568 AND 4.78418),
    CONSTRAINT chk_longitude CHECK (longitude BETWEEN -74.19391 AND -74.01404),
    CONSTRAINT chk_speed CHECK (speed_kmh >= 0),
    CONSTRAINT chk_fuel_level CHECK (fuel_level BETWEEN 0 AND 100)
);

-- Consultas por vehículo
CREATE INDEX idx_vehicle_reports_device_vehicle_id
ON vehicle_reports (device_vehicle_id);

-- Consultas por vehículo y rango de tiempo
CREATE INDEX idx_vehicle_reports_vehicle_timestamp
ON vehicle_reports (device_vehicle_id, reported_at);

-- Consultas generales por fecha/hora
CREATE INDEX idx_vehicle_reports_timestamp
ON vehicle_reports (reported_at);



CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.geofences (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    geofence_type VARCHAR(50) NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mode VARCHAR(20) NOT NULL DEFAULT 'manual',
    refill_rate NUMERIC(6, 2) NOT NULL DEFAULT 0,
    CONSTRAINT chk_geofences_type
        CHECK (geofence_type IN ('fuel', 'urban', 'high_accident', 'restricted', 'other')),
    CONSTRAINT chk_geofences_mode
        CHECK (mode IN ('manual', 'random')),
    CONSTRAINT chk_geofences_refill_rate
        CHECK (refill_rate >= 0)
);

CREATE INDEX IF NOT EXISTS idx_geofences_geom
ON monitoreo_vehiculos.geofences
USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_geofences_active
ON monitoreo_vehiculos.geofences (active);

CREATE INDEX IF NOT EXISTS idx_geofences_type_mode
ON monitoreo_vehiculos.geofences (geofence_type, mode);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, refill_rate)
VALUES (
    'Recarga Américas y Teusaquillo',
    'Zona manual de recarga',
    'fuel',
    ST_MakeEnvelope(
        -74.10483, 4.59424,
        -74.07254, 4.63757,
        4326
    ),
    'manual',
    1.50
);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, refill_rate)
VALUES (
    'Alta Accidentalidad Bosa-Soacha',
    'Zona manual de recarga',
    'high_accident',
    ST_MakeEnvelope(
        -74.18465, 4.59657,
        -74.14283, 4.56888,
        4326
    ),
    'manual',
    50
);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, refill_rate)
VALUES (
    'Alta Accidentalidad Engativá',
    'Zona manual de recarga',
    'high_accident',
    ST_MakeEnvelope(
        -74.14262, 4.73686,
        -74.08016, 4.68521,
        4326
    ),
    'manual',
    30
);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, monitor_variable)
VALUES (
    'Zona Urbana Chapinero',
    'Área urbana de monitoreo',
    'urban',
    ST_MakeEnvelope(
        -74.07500, 4.63500,
        -74.05000, 4.65500,
        4326
    ),
    'manual',
    0
);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, monitor_variable)
VALUES (
    'Zona Restringida Aeropuerto',
    'Área restringida cercana al aeropuerto',
    'restricted',
    ST_MakeEnvelope(
        -74.14500, 4.68000,
        -74.12000, 4.70500,
        4326
    ),
    'manual',
    0
);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, monitor_variable)
VALUES (
    'Recarga Occidente',
    'Zona manual adicional de recarga',
    'fuel',
    ST_MakeEnvelope(
        -74.16000, 4.65000,
        -74.14000, 4.67000,
        4326
    ),
    'manual',
    2.00
);

INSERT INTO monitoreo_vehiculos.geofences
    (name, description, geofence_type, geom, mode, monitor_variable)
VALUES (
    'Zona Complementaria Sur',
    'Área adicional de monitoreo',
    'high_accident',
    ST_MakeEnvelope(
        -74.12000, 4.60000,
        -74.10000, 4.62000,
        4326
    ),
    'manual',
    35
);


ALTER TABLE monitoreo_vehiculos.geofences RENAME COLUMN speed_limit_kmh TO monitor_variable;

CREATE INDEX IF NOT EXISTS idx_geofences_high_accident_active_geom
ON monitoreo_vehiculos.geofences
USING GIST (geom)
WHERE active = TRUE
  AND geofence_type = 'high_accident';

CREATE INDEX IF NOT EXISTS idx_geofences_active_geom
ON monitoreo_vehiculos.geofences
USING GIST (geom)
WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.vehicles_in_geofence (
    id BIGSERIAL PRIMARY KEY,
    vehicle_report_id BIGINT NOT NULL,
    geofence_id BIGINT NOT NULL,
    device_vehicle_id VARCHAR(50) NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_vig_vehicle_report
        FOREIGN KEY (vehicle_report_id)
        REFERENCES monitoreo_vehiculos.vehicle_reports(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_vig_geofence
        FOREIGN KEY (geofence_id)
        REFERENCES monitoreo_vehiculos.geofences(id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_vig_report_geofence
        UNIQUE (vehicle_report_id, geofence_id)
);

CREATE INDEX IF NOT EXISTS idx_vig_vehicle
ON monitoreo_vehiculos.vehicles_in_geofence (device_vehicle_id);

CREATE INDEX IF NOT EXISTS idx_vig_geofence
ON monitoreo_vehiculos.vehicles_in_geofence (geofence_id);

CREATE INDEX IF NOT EXISTS idx_vig_reported_at
ON monitoreo_vehiculos.vehicles_in_geofence (reported_at);

CREATE INDEX IF NOT EXISTS idx_vig_vehicle_reported_at
ON monitoreo_vehiculos.vehicles_in_geofence (
    device_vehicle_id,
    reported_at
);


CREATE TABLE IF NOT EXISTS monitoreo_vehiculos.high_speed_alerts (
    id BIGSERIAL PRIMARY KEY,
    vehicle_report_id BIGINT NOT NULL,
    geofence_id BIGINT NOT NULL,
    device_vehicle_id VARCHAR(50) NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    speed_kmh NUMERIC(6,2) NOT NULL,
    speed_limit_kmh NUMERIC(6,2) NOT NULL,
    excess_speed_kmh NUMERIC(6,2)
        GENERATED ALWAYS AS (speed_kmh - speed_limit_kmh) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_hsa_vehicle_report
        FOREIGN KEY (vehicle_report_id)
        REFERENCES monitoreo_vehiculos.vehicle_reports(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_hsa_geofence
        FOREIGN KEY (geofence_id)
        REFERENCES monitoreo_vehiculos.geofences(id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_hsa_report_geofence
        UNIQUE (vehicle_report_id, geofence_id),
    CONSTRAINT chk_hsa_speed
        CHECK (speed_kmh >= 0),
    CONSTRAINT chk_hsa_speed_limit
        CHECK (speed_limit_kmh >= 0),
    CONSTRAINT chk_hsa_excess
        CHECK (speed_kmh > speed_limit_kmh)
);

CREATE INDEX IF NOT EXISTS idx_hsa_vehicle
ON monitoreo_vehiculos.high_speed_alerts (device_vehicle_id);

CREATE INDEX IF NOT EXISTS idx_hsa_geofence
ON monitoreo_vehiculos.high_speed_alerts (geofence_id);

CREATE INDEX IF NOT EXISTS idx_hsa_reported_at
ON monitoreo_vehiculos.high_speed_alerts (reported_at);

CREATE INDEX IF NOT EXISTS idx_hsa_vehicle_reported_at
ON monitoreo_vehiculos.high_speed_alerts (
    device_vehicle_id,
    reported_at
);


CREATE OR REPLACE FUNCTION monitoreo_vehiculos.evaluate_vehicle_report(
    p_vehicle_report_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN

    INSERT INTO monitoreo_vehiculos.vehicles_in_geofence (
        vehicle_report_id,
        geofence_id,
        device_vehicle_id,
        reported_at,
        latitude,
        longitude
    )
    SELECT
        vr.id,
        g.id,
        vr.device_vehicle_id,
        vr.reported_at,
        vr.latitude,
        vr.longitude
    FROM monitoreo_vehiculos.vehicle_reports vr
    JOIN monitoreo_vehiculos.geofences g
        ON g.active = TRUE
       AND ST_Covers(
            g.geom,
            ST_SetSRID(
                ST_MakePoint(
                    vr.longitude,
                    vr.latitude
                ),
                4326
            )
       )
    WHERE vr.id = p_vehicle_report_id
    ON CONFLICT (vehicle_report_id, geofence_id)
    DO NOTHING;


    INSERT INTO monitoreo_vehiculos.high_speed_alerts (
        vehicle_report_id,
        geofence_id,
        device_vehicle_id,
        reported_at,
        latitude,
        longitude,
        speed_kmh,
        speed_limit_kmh
    )
    SELECT
        vr.id,
        g.id,
        vr.device_vehicle_id,
        vr.reported_at,
        vr.latitude,
        vr.longitude,
        vr.speed_kmh,
        g.monitor_variable
    FROM monitoreo_vehiculos.vehicle_reports vr
    JOIN monitoreo_vehiculos.geofences g
        ON g.active = TRUE
       AND g.geofence_type = 'high_accident'
       AND ST_Covers(
            g.geom,
            ST_SetSRID(
                ST_MakePoint(
                    vr.longitude,
                    vr.latitude
                ),
                4326
            )
       )
    WHERE vr.id = p_vehicle_report_id
      AND vr.speed_kmh > g.monitor_variable
    ON CONFLICT (vehicle_report_id, geofence_id)
    DO NOTHING;

END;
$$;

CREATE OR REPLACE FUNCTION monitoreo_vehiculos.trg_evaluate_vehicle_report()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM monitoreo_vehiculos.evaluate_vehicle_report(NEW.id);

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_vehicle_report_geofence_analysis
ON monitoreo_vehiculos.vehicle_reports;

CREATE TRIGGER trg_vehicle_report_geofence_analysis
AFTER INSERT ON monitoreo_vehiculos.vehicle_reports
FOR EACH ROW
EXECUTE FUNCTION monitoreo_vehiculos.trg_evaluate_vehicle_report();

truncate table vehicle_reports cascade;

select * from vehicle_reports where device_vehicle_id ilike '%001%'

select id,name,description,geofence_type,'0' as geom, active, created_at, mode, monitor_variable from geofences

select * from high_speed_alerts

select * from vehicles_in_geofence


