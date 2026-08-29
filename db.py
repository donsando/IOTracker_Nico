"""
Escritura de paquetes de telemetría en vehicle_reports y gestión de
geofences en PostgreSQL.

Tres modos de escritura (DB_MODE en .env):
  - "dry_run"  : no se conecta a la BD, solo loguea.
  - "rollback" : inserta y hace ROLLBACK (no persiste).
  - "commit"   : inserta y hace COMMIT (persiste).
"""

import json
import logging

from psycopg_pool import AsyncConnectionPool
from shapely.geometry import mapping, shape

from config import Geofence, Settings, generate_random_geofences

log = logging.getLogger("sim")

INSERT_SQL = """
INSERT INTO monitoreo_vehiculos.vehicle_reports
    (device_vehicle_id, reported_at, latitude, longitude, speed_kmh, fuel_level)
VALUES (%s, %s, %s, %s, %s, %s)
"""

GEOFENCES_TABLE = "monitoreo_vehiculos.geofences"


async def make_pool(settings: Settings) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(settings.conninfo, min_size=1, max_size=5, open=False)
    await pool.open()
    return pool


async def load_geofences(pool: AsyncConnectionPool, mode: str | None = None) -> list[Geofence]:
    sql = f"""
        SELECT id, name, description, geofence_type, mode, active,
               monitor_variable, ST_AsGeoJSON(geom)
        FROM {GEOFENCES_TABLE}
        WHERE active = TRUE
    """
    params: list = []
    if mode is not None:
        sql += " AND mode = %s"
        params.append(mode)
    sql += " ORDER BY id"

    async with pool.connection() as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()

    geofences = []
    for r in rows:
        geofences.append(
            Geofence(
                id=r[0],
                name=r[1],
                description=r[2],
                geofence_type=r[3],
                mode=r[4],
                active=r[5],
                monitor_variable=float(r[6]),
                polygon=shape(json.loads(r[7])),
            )
        )
    return geofences


async def prepare_geofences(pool: AsyncConnectionPool, settings: Settings) -> list[Geofence]:
    """Carga las geofences activas. En modo random genera e inserta nuevas."""
    manual = await load_geofences(pool, "manual")

    if settings.geofences_mode != "random":
        return manual

    generated = generate_random_geofences(settings)
    if settings.db_mode != "dry_run":
        async with pool.connection() as conn:
            await conn.execute(f"DELETE FROM {GEOFENCES_TABLE} WHERE mode = 'random'")
            for gf in generated:
                await conn.execute(
                    f"""
                    INSERT INTO {GEOFENCES_TABLE}
                        (name, description, geofence_type, geom, mode, monitor_variable)
                    VALUES (%s, %s, %s,
                            ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                            'random', %s)
                    """,
                    (
                        gf.name,
                        gf.description,
                        gf.geofence_type,
                        json.dumps(mapping(gf.polygon)),
                        gf.monitor_variable,
                    ),
                )
            await conn.commit()

    return manual + generated


async def cleanup_random_geofences(pool: AsyncConnectionPool, db_mode: str) -> None:
    if db_mode == "dry_run":
        return
    async with pool.connection() as conn:
        await conn.execute(f"DELETE FROM {GEOFENCES_TABLE} WHERE mode = 'random'")
        await conn.commit()


async def insert_report(pool: AsyncConnectionPool, packet: dict, db_mode: str) -> None:
    if db_mode == "dry_run":
        log.info("[dry_run] %s", packet)
        return

    async with pool.connection() as conn:
        await conn.execute(
            INSERT_SQL,
            (
                packet["device_vehicle_id"],
                packet["reported_at"],
                packet["latitude"],
                packet["longitude"],
                packet["speed_kmh"],
                packet["fuel_level"],
            ),
        )

        # ══════════════════════════════════════════════════════════════
        #  CONTROL DE PERSISTENCIA
        #  ------------------------------------------------------------
        #  PRUEBAS     → descomenta la línea ROLLBACK (no guarda nada).
        #  PRODUCCIÓN  → descomenta la línea COMMIT (guarda los datos).
        #
        #  El comportamiento por defecto lo define DB_MODE en .env
        #  ("rollback" | "commit" | "dry_run").
        # ══════════════════════════════════════════════════════════════
        if db_mode == "rollback":
            await conn.rollback()  # PRUEBAS     → no persiste
        else:
            await conn.commit()  # PRODUCCIÓN → persiste

        #  ── Alternativa manual (sin depender de DB_MODE) ─────────────
        #  Descomenta una sola de las dos líneas siguientes y comenta el
        #  bloque if/else de arriba:
        #
        #  await conn.rollback()   # PRUEBAS: descarta la inserción
        #  await conn.commit()     # PRODUCCIÓN: guarda la inserción
        #  ──────────────────────────────────────────────────────────────
