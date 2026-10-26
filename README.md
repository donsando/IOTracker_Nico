# IOTracker_Nico — Monitoreo de movilidad

Aplicación de monitoreo de vehículos sobre la malla vial de Bogotá. Simula el
desplazamiento de vehículos y muestra sus posiciones en un mapa web, junto con
geocercas y alertas de exceso de velocidad.

## Funcionalidades

- Visualización en tiempo real de los vehículos y sus datos de ubicación,
  velocidad y combustible.
- Mapa interactivo con la malla vial y geocercas.
- Alertas de exceso de velocidad.
- API para consultar el flujo de vehículos, alertas, aristas de la malla vial y
  metadatos de configuración.

## Requisitos

- Docker Desktop con Docker Compose, o Python 3.13 o superior y PostgreSQL 16
  con PostGIS y pgRouting.
- Shapefile de la malla vial de Bogotá: `Malla_Vial_Integral_Bogota_D_C`, con
  sus archivos `.shp`, `.shx`, `.dbf`, `.prj` y `.cpg`.

El directorio `data/` no se versiona. Coloca allí los archivos del shapefile
antes de iniciar la aplicación.

## Inicio rápido con Docker

```bash
git clone https://github.com/donsando/IOTracker_Nico.git
cd IOTracker_Nico
touch .env
mkdir -p data
```

Docker Compose necesita que exista `.env`; la configuración de Docker está
definida en `docker-compose.yml`. Copia los archivos del shapefile a `data/` y
ejecuta:

```bash
docker compose up --build
```

Cuando la aplicación esté lista, abre <http://127.0.0.1:9000>.

Para detener los servicios, usa `Ctrl+C` y luego:

```bash
docker compose down
```

Docker Compose expone la aplicación en el puerto `9000` y PostgreSQL en el
puerto `5433` del equipo local.

## Ejecución local

Consulta [SETUP.md](SETUP.md) para ver los pasos de configuración de PostgreSQL,
el entorno de Python, la carga de la malla vial y el inicio del servidor.

## Endpoints principales

- `/stream`: flujo de posiciones en tiempo real (SSE).
- `/high-speed-alerts`: alertas de exceso de velocidad.
- `/edges/bbox`: aristas de la malla vial dentro de un área del mapa.
- `/meta`: metadatos de configuración.

## Componentes

- **FastAPI** sirve la aplicación web y la API.
- **Leaflet** muestra el mapa y las capas de datos.
- **PostgreSQL, PostGIS y pgRouting** almacenan y consultan la información
  geográfica y la red vial.
- `simulation.py` genera el movimiento de los vehículos y `load_graph.py`
  carga la malla vial en la base de datos.
