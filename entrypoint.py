"""
Bootstrap del contenedor: espera a PostgreSQL, carga la malla vial si aún
no existe y arranca el servidor (mapa + simulación).

Solo se usa dentro del contenedor (docker compose). Para ejecución local
sigue usando main.py.
"""

import sys
import time

import psycopg
import uvicorn

from config import ConfigurationError, load_settings


def wait_for_db(settings, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with psycopg.connect(settings.conninfo):
                return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(2)


def ensure_road_graph(settings) -> None:
    with psycopg.connect(settings.conninfo) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('monitoreo_vehiculos.road_edges')")
        exists = cur.fetchone()[0] is not None
        count = 0
        if exists:
            cur.execute("SELECT count(*) FROM monitoreo_vehiculos.road_edges")
            count = cur.fetchone()[0]

    if count > 0:
        print(f"Malla vial ya cargada ({count} aristas).")
        return

    print("Malla vial vacía: cargando shapefile...")
    import load_graph

    load_graph.main()


def main() -> None:
    settings = load_settings()
    wait_for_db(settings)
    ensure_road_graph(settings)
    uvicorn.run(
        "app:app",
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
    )


if __name__ == "__main__":
    try:
        main()
    except ConfigurationError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        sys.exit(1)
