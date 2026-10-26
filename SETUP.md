# SETUP — IOTracker_Nico Movilidad Prueba Técnica
# Autor: Nicolas David Sandoval Bermudez

- **Opción A — Docker Compose (recomendada):** levanta la base de datos y
  la aplicación con un solo comando.
- **Opción B — Ejecución local:** útil para desarrollo sin Docker.

---

## 0. Prerrequisitos

- [Git](https://git-scm.com/)
- **Opción A (Docker):** [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  (incluye `docker compose`).
- **Opción B (local):**
  - Python 3.13 o superior
  - PostgreSQL 16 con las extensiones **PostGIS** y **pgRouting** instaladas
    (en macOS: `brew install postgresql@16 postgis pgrouting`).

## 1. Clonar el repositorio

```bash
git clone https://github.com/donsando/IOTracker_Nico.git
cd IOTracker_Nico
```

## 2. Obtener el shapefile de la malla vial (obligatorio)

El directorio `data/` está en `.gitignore`, por lo que **no se descarga con
el clon**. Debes conseguir el shapefile `Malla_Vial_Integral_Bogota_D_C`
(malla vial de Bogotá) y colocar **todos sus archivos** (`.shp`, `.shx`,
`.dbf`, `.prj`, `.cpg`) dentro de `data/`.

```bash
mkdir -p data
# Copia aquí los archivos del shapefile descargado, por ejemplo:
#   data/Malla_Vial_Integral_Bogota_D_C.shp
#   data/Malla_Vial_Integral_Bogota_D_C.shx
#   data/Malla_Vial_Integral_Bogota_D_C.dbf
#   data/Malla_Vial_Integral_Bogota_D_C.prj
#   data/Malla_Vial_Integral_Bogota_D_C.cpg
```

> Sin estos archivos, la carga del grafo vial (`load_graph.py`) fallará.

## 3. Configurar las variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y ajusta como mínimo:

| Variable      | Descripción                                            |
| ------------- | ------------------------------------------------------ |
| `DB_PASSWORD` | Contraseña de PostgreSQL (obligatoria en ejecución local) |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` (local)                  |
| `SHAPEFILE_PATH` | Ruta al `.shp` de la malla vial. Para Docker usa `/app/data/Malla_Vial_Integral_Bogota_D_C.shp`; para local usa la ruta absoluta en tu máquina. |
| `DB_MODE`     | `rollback` (no persiste), `commit` (persiste) o `dry_run` (sin BD) |

Los demás parámetros (simulación, geofences, velocidades, etc.) tienen
valores por defecto razonables; si falta alguno, la aplicación lo avisará al
arrancar y preguntará si deseas usar el valor por defecto.

## Opción A — Ejecutar con Docker Compose (recomendado)

```bash
docker compose up --build
```

Esto levanta:

- **db**: PostgreSQL 16 + PostGIS + pgRouting (puerto host `5433`).
- **app**: la aplicación (puerto `9000`), que al arrancar espera a la BD y
  **carga automáticamente el grafo vial desde `data/`** la primera vez.

Cuando veas en los logs `Simulación iniciada`, abre en el navegador:

```
http://127.0.0.1:9000
```

Para detener: `Ctrl+C` y luego `docker compose down`.

> Para empezar con una BD limpia (recrear el esquema): `docker compose down -v`.

## Opción B — Ejecutar localmente (sin Docker)

### B.1 Base de datos

1. Crea la base de datos y habilita las extensiones:

   ```bash
   createdb iotracker_nico_movilidad
   psql -d iotracker_nico_movilidad -c "CREATE EXTENSION postgis; CREATE EXTENSION pgrouting; CREATE SCHEMA monitoreo_vehiculos;"
   ```

2. Aplica el esquema inicial (tablas, índices y geofences de ejemplo):

   ```bash
   psql -d iotracker_nico_movilidad -f db/init/01_schema.sql
   ```

### B.2 Entorno de Python

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### B.3 Cargar el grafo vial (una sola vez)

```bash
python load_graph.py
```

Debe mostrar `Malla vial cargada`. Solo es necesario repetirlo si cambias el
shapefile o recreas la BD.

### B.4 Levantar el servidor

```bash
python main.py
```

Cuando veas `Simulación iniciada`, abre:

```
http://127.0.0.1:9000
```

---

## 4. Qué ver en el mapa

- **Vehículos** moviéndose en tiempo real sobre la malla vial (SSE en `/stream`).
- **Geofences** coloreadas por tipo (`fuel`, `urban`, `high_accident`,
  `restricted`, `other`).
- **Alertas de exceso de velocidad** en el endpoint `/high-speed-alerts`.
- Consulta de aristas por bounding box en `/edges/bbox`.
- Metadatos de configuración en `/meta`.

## 5. Solución de problemas

| Problema | Causa probable / solución |
| -------- | ------------------------- |
| `Error de configuración: ...` | Falta una variable en `.env` o su valor es inválido. Revísalo y reintenta. |
| Archivos del shapefile no encontrados | `data/` está vacío localmente (ver paso 2). |
| `connection refused` a PostgreSQL | En local, BD apagada o `DB_HOST`/`DB_PORT` incorrectos. En Docker, usa el healthcheck del compose. |
| La aplicación no carga geografía | Ejecuta `load_graph.py` (local) o revisa el log del contenedor `app`. |
| Puerto 9000 en uso | Cambia `WEB_PORT` en `.env`. |

## Estructura relevante

```
.
├── data/                 # Shapefile de la malla vial (NO versionado)
├── db/
│   ├── Dockerfile        # Imagen postgis + pgrouting
│   └── init/01_schema.sql# Esquema inicial + geofences de ejemplo
├── static/               # Mapa Leaflet (frontend)
├── app.py                # Servidor FastAPI (mapa + SSE)
├── main.py               # Punto de entrada para ejecución local
├── entrypoint.py         # Bootstrap del contenedor (wait-for-db + carga del grafo)
├── load_graph.py         # Carga del shapefile a PostGIS/pgRouting
├── simulation.py         # Loop de simulación de vehículos
├── graph.py / db.py      # Grafo vial en memoria / acceso a BD
├── config.py             # Carga y validación de .env
└── docker-compose.yml    # Orquestación de app + db
```
