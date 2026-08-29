"""
Servidor web local (puerto 9000) que sirve el mapa Leaflet y transmite
la posición de los vehículos en tiempo real vía Server-Sent Events (SSE).
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
from db import cleanup_random_geofences, make_pool, prepare_geofences
from graph import RoadGraph
from simulation import Simulation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("web")

EDGES_TABLE = "monitoreo_vehiculos.road_edges"
ALERTS_TABLE = "monitoreo_vehiculos.high_speed_alerts"


class Broadcaster:
    def __init__(self):
        self._subs: set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    async def publish(self, msg: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


broadcaster = Broadcaster()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.load_settings()
    pool = await make_pool(settings)
    geofences = await prepare_geofences(pool, settings)
    settings.geofences = geofences
    graph = RoadGraph(pool)
    sim = Simulation(settings, pool, graph, broadcaster)
    app.state.pool = pool
    app.state.sim = sim
    app.state.settings = settings
    app.state.geofences = geofences
    task = asyncio.create_task(sim.run())
    log.info("Simulación iniciada. Abre http://%s:%s", settings.web_host, settings.web_port)
    log.info("Modo de geofences: %s", settings.geofences_mode)
    log.info("Geofences activas: %d", len(geofences))
    for gf in geofences:
        log.info(
            "  - %s [%s] (%s) monitor_variable=%s",
            gf.name,
            gf.geofence_type,
            gf.mode,
            gf.monitor_variable,
        )
    try:
        yield
    finally:
        task.cancel()
        try:
            await cleanup_random_geofences(pool, settings.db_mode)
        except Exception as exc:  # noqa: BLE001
            log.warning("No fue posible limpiar geofences random: %s", exc)
        await pool.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/meta")
async def meta():
    return {
        "geofences": [g.as_dict() for g in app.state.geofences],
        "tick_seconds": app.state.settings.tick_seconds,
    }


@app.get("/stream")
async def stream(request: Request):
    async def event_gen():
        q = await broadcaster.subscribe()
        try:
            # Snapshot inicial para pintar el mapa de inmediato.
            yield f"data: {json.dumps({'type': 'snapshot', 'vehicles': app.state.sim.state}, default=_json_default)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(msg, default=_json_default)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/high-speed-alerts")
async def high_speed_alerts(after_id: int = Query(0)):
    pool = app.state.pool
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT id, device_vehicle_id, ST_AsGeoJSON(geom),
                   speed_kmh, speed_limit_kmh, excess_speed_kmh, reported_at
            FROM {ALERTS_TABLE}
            WHERE geom IS NOT NULL AND id > %s
            ORDER BY id
            """,
            (after_id,),
        )
        rows = await cur.fetchall()
    alerts = []
    for r in rows:
        alerts.append(
            {
                "id": r[0],
                "device_vehicle_id": r[1],
                "geometry": json.loads(r[2]),
                "speed_kmh": float(r[3]) if r[3] is not None else None,
                "speed_limit_kmh": float(r[4]) if r[4] is not None else None,
                "excess_speed_kmh": float(r[5]) if r[5] is not None else None,
                "reported_at": r[6].isoformat() if r[6] is not None else None,
            }
        )
    return {"alerts": alerts}


@app.get("/edges/bbox")
async def edges_bbox(
    minx: float = Query(...),
    miny: float = Query(...),
    maxx: float = Query(...),
    maxy: float = Query(...),
    limit: int = Query(5000),
):
    pool = app.state.pool
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT ST_AsGeoJSON(geom) FROM {EDGES_TABLE} "
            "WHERE geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) LIMIT %s",
            (minx, miny, maxx, maxy, limit),
        )
        rows = await cur.fetchall()
    features = [
        {"type": "Feature", "geometry": json.loads(r[0]), "properties": {}}
        for r in rows
    ]
    return JSONResponse({"type": "FeatureCollection", "features": features})
