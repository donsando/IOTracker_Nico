"""
Carga única del shapefile de la malla vial a PostGIS + pgRouting.

Flujo:
  1. Lee el .shp con GeoPandas y normaliza a EPSG:4326.
  2. Hace bulk-load (COPY) de las geometrías en WKT a una tabla staging.
  3. Recorta las aristas al bounding box de Bogotá (mismo rango de los
     CHECK de vehicle_reports) usando ST_Intersection.
  4. Construye la topología con pgr_createTopology (crea source/target y
     la tabla <tabla>_vertices_pgr).

Ejecutar una sola vez:
    python load_graph.py
"""

import sys

import geopandas as gpd
from psycopg import connect

from config import ConfigurationError, load_settings

SCHEMA = "monitoreo_vehiculos"
RAW_TABLE = f"{SCHEMA}.malla_vial_raw"
EDGES_TABLE = f"{SCHEMA}.road_edges"


def main() -> None:
    settings = load_settings()
    print(f"Leyendo shapefile: {settings.shapefile_path}")
    gdf = gpd.read_file(settings.shapefile_path)
    gdf = gdf.to_crs("EPSG:4326")
    print(f"Registros leídos: {len(gdf)}")

    # Solo geometrías (LineString / MultiLineString); el resto se descarta.
    wkts = [g.wkt for g in gdf.geometry if g is not None and not g.is_empty]

    print("Conectando a PostgreSQL...")
    conn = connect(settings.conninfo)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgrouting")

        print("Cargando geometrías (COPY)...")
        cur.execute(f"DROP TABLE IF EXISTS {RAW_TABLE}")
        cur.execute(
            f"CREATE TABLE {RAW_TABLE} (id bigserial PRIMARY KEY, wkt text)"
        )
        with cur.copy(f"COPY {RAW_TABLE} (wkt) FROM STDIN") as copy:
            for w in wkts:
                copy.write_row((w,))

        print("Recortando al bbox de Bogotá y creando aristas...")
        bbox = (
            settings.bbox_lon_min,
            settings.bbox_lat_min,
            settings.bbox_lon_max,
            settings.bbox_lat_max,
        )
        cur.execute(f"DROP TABLE IF EXISTS {EDGES_TABLE}")
        cur.execute(
            f"""
            CREATE TABLE {EDGES_TABLE} AS
            SELECT row_number() OVER () AS id, d.geom
            FROM (
                SELECT (ST_Dump(ST_Intersection(
                    ST_GeomFromText(wkt, 4326),
                    ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                ))).geom AS geom
                FROM {RAW_TABLE}
                WHERE ST_Intersects(
                    ST_GeomFromText(wkt, 4326),
                    ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                )
            ) d
            WHERE ST_GeometryType(d.geom) = 'ST_LineString'
              AND NOT ST_IsEmpty(d.geom)
              AND ST_Length(d.geom) > 0
            """,
            (*bbox, *bbox),
        )
        cur.execute(f"ALTER TABLE {EDGES_TABLE} ADD PRIMARY KEY (id)")
        cur.execute(
            f"ALTER TABLE {EDGES_TABLE} "
            "ADD COLUMN source bigint, ADD COLUMN target bigint"
        )

        print("Construyendo topología (pgr_createTopology)...")
        cur.execute(
            f"""SELECT pgr_createTopology(
                '{EDGES_TABLE}', %s, 'geom', 'id', 'source', 'target',
                'true', true
            )""",
            (settings.topology_tolerance,),
        )

        print("Creando índices...")
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS road_edges_source_idx "
            f"ON {EDGES_TABLE} (source)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS road_edges_target_idx "
            f"ON {EDGES_TABLE} (target)"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS road_edges_geom_idx "
            f"ON {EDGES_TABLE} USING gist (geom)"
        )

        cur.execute(f"SELECT count(*) FROM {EDGES_TABLE}")
        n_edges = cur.fetchone()[0]
        cur.execute(
            f"SELECT count(*) FROM {EDGES_TABLE} WHERE source IS NULL OR target IS NULL"
        )
        n_null = cur.fetchone()[0]

    conn.close()

    print(f"Arasitas creadas: {n_edges}")
    print(f"Arasitas sin nodo asignado (aisladas): {n_null}")
    print("Listo. La malla vial quedó disponible para la simulación.")


if __name__ == "__main__":
    try:
        main()
    except ConfigurationError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
