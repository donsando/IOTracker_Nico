"""
Configuración de la aplicación.

Los valores se leen desde el archivo .env. Si una variable no está
definida, se avisa por consola y se pregunta si se desea usar el valor
por defecto o detener la ejecución para definirlo en .env.

No se usan valores por defecto silenciosos: cualquier ausencia o valor
inválido produce un aviso explícito o cancela el arranque.
"""

import os
import random
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv
from shapely.geometry import Point, Polygon, box, mapping

load_dotenv()


class ConfigurationError(Exception):
    """Error de configuración: variable faltante o valor inválido."""


# ── Área de trabajo (debe coincidir con los CHECK de vehicle_reports) ──
BBOX_LAT_MIN = 4.54568
BBOX_LAT_MAX = 4.78418
BBOX_LON_MIN = -74.19391
BBOX_LON_MAX = -74.01404

GEOFENCE_TYPES = ("fuel", "urban", "high_accident", "restricted", "other")

GEOFENCE_COLORS = {
    "fuel": "#1f77b4",           # azul
    "urban": "#2ca02c",          # verde
    "high_accident": "#d62728",  # rojo
    "restricted": "#9467bd",     # morado
    "other": "#7f7f7f",          # gris
}


@dataclass
class Geofence:
    id: int
    name: str
    description: str
    geofence_type: str
    mode: str
    active: bool
    monitor_variable: float
    polygon: Polygon

    def contains(self, lat: float, lon: float) -> bool:
        return self.polygon.contains(Point(lon, lat))

    @property
    def color(self) -> str:
        return GEOFENCE_COLORS.get(self.geofence_type, "#7f7f7f")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "geofence_type": self.geofence_type,
            "mode": self.mode,
            "active": self.active,
            "monitor_variable": self.monitor_variable,
            "color": self.color,
            "geometry": mapping(self.polygon),
        }


@dataclass
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_mode: str

    shapefile_path: str
    topology_tolerance: float

    num_vehicles: int
    tick_seconds: float
    speed_min_kmh: float
    speed_max_kmh: float
    speed_variable_ratio: float
    speed_change_interval_ticks: int
    speed_max_change_kmh_per_tick: float
    fuel_consumption: float

    nav_continuity_factor: float
    nav_max_continuity_gap_m: float
    log_transitions: bool

    geofences_mode: str
    random_geofence_count: int
    random_geofence_type: str
    random_geofence_min_size: float
    random_geofence_max_size: float
    random_geofence_refill_rate_min: float
    random_geofence_refill_rate_max: float

    web_host: str
    web_port: int

    bbox_lat_min: float = BBOX_LAT_MIN
    bbox_lat_max: float = BBOX_LAT_MAX
    bbox_lon_min: float = BBOX_LON_MIN
    bbox_lon_max: float = BBOX_LON_MAX

    geofences: list = field(default_factory=list)

    @property
    def conninfo(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} "
            f"dbname={self.db_name} user={self.db_user} "
            f"password={self.db_password}"
        )


def _prompt(name: str, default, secret: bool = False):
    if secret:
        shown = "(vacío)" if not default else "(definido)"
    else:
        shown = str(default)
    print()
    print(f"[CONFIG] Falta definir la variable '{name}'.")
    print(f"         Valor por defecto disponible: {shown}")
    if not sys.stdin.isatty():
        print("         Entorno no interactivo: usando el valor por defecto.")
        return default
    try:
        ans = input("         ¿Usar el valor por defecto? [S/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "s"
    if ans in ("", "s", "y", "si", "sí", "yes"):
        return default
    raise ConfigurationError(
        f"Define '{name}' en el archivo .env y vuelve a ejecutar."
    )


def _get_env(*names):
    for n in names:
        v = os.getenv(n)
        if v is not None:
            return v
    return None


def _get(names, default, cast=str, validate=None, secret=False):
    if isinstance(names, str):
        names = [names]
    raw = _get_env(*names)
    if raw is None:
        value = _prompt(names[0], default, secret)
    else:
        value = raw
    try:
        parsed = cast(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Valor inválido para '{names[0]}': {value!r} ({exc})"
        )
    if validate is not None and not validate(parsed):
        raise ConfigurationError(f"Valor fuera de rango para '{names[0]}': {value!r}")
    return parsed


_settings: Settings | None = None


def load_settings() -> Settings:
    global _settings
    if _settings is not None:
        return _settings

    geofences_mode = _get(
        ("GEOFENCES_MODE", "FUEL_ZONES_MODE"), "manual"
    ).lower()
    if geofences_mode not in {"manual", "random"}:
        raise ConfigurationError("GEOFENCES_MODE debe ser 'manual' o 'random'")

    # Los parámetros aleatorios solo se solicitan en modo random.
    if geofences_mode == "random":
        random_count = _get(
            ("RANDOM_GEOFENCE_COUNT", "FUEL_ZONE_COUNT"), 3, int, lambda v: v >= 0
        )
        random_type = _get("RANDOM_GEOFENCE_TYPE", "fuel").lower()
        if random_type not in GEOFENCE_TYPES:
            raise ConfigurationError(
                f"RANDOM_GEOFENCE_TYPE debe ser uno de {GEOFENCE_TYPES}"
            )
        random_min_size = _get(
            ("RANDOM_GEOFENCE_MIN_SIZE_DEGREES", "FUEL_ZONE_MIN_SIZE_DEGREES"),
            0.005,
            float,
            lambda v: v > 0,
        )
        random_max_size = _get(
            ("RANDOM_GEOFENCE_MAX_SIZE_DEGREES", "FUEL_ZONE_MAX_SIZE_DEGREES"),
            0.015,
            float,
            lambda v: v > 0,
        )
        random_rate_min = _get(
            ("RANDOM_GEOFENCE_REFILL_RATE_MIN", "FUEL_ZONE_REFILL_RATE_MIN"),
            1.0,
            float,
            lambda v: v >= 0,
        )
        random_rate_max = _get(
            ("RANDOM_GEOFENCE_REFILL_RATE_MAX", "FUEL_ZONE_REFILL_RATE_MAX"),
            2.0,
            float,
            lambda v: v >= 0,
        )
        if random_max_size < random_min_size:
            raise ConfigurationError(
                "RANDOM_GEOFENCE_MAX_SIZE_DEGREES no puede ser menor que "
                "RANDOM_GEOFENCE_MIN_SIZE_DEGREES"
            )
    else:
        random_count = 3
        random_type = "fuel"
        random_min_size = 0.005
        random_max_size = 0.015
        random_rate_min = 1.0
        random_rate_max = 2.0

    s = Settings(
        db_host=_get("DB_HOST", "localhost"),
        db_port=_get("DB_PORT", 5432, int, lambda v: 1 <= v <= 65535),
        db_name=_get("DB_NAME", "iotracker_nico_movilidad"),
        db_user=_get("DB_USER", "postgres"),
        db_password=_get("DB_PASSWORD", "", secret=True),
        db_mode=_get("DB_MODE", "rollback"),
        shapefile_path=_get(
            "SHAPEFILE_PATH",
            "/Users/nicolas/Downloads/Malla_Vial_Integral_Bogota_D_C/Malla_Vial_Integral_Bogota_D_C.shp",
        ),
        topology_tolerance=_get(
            "TOPOLOGY_TOLERANCE", 0.00001, float, lambda v: v > 0
        ),
        num_vehicles=_get("NUM_VEHICLES", 5, int, lambda v: v >= 0),
        tick_seconds=_get("TICK_SECONDS", 5.0, float, lambda v: v > 0),
        speed_min_kmh=_get("SPEED_MIN_KMH", 20.0, float, lambda v: v >= 0),
        speed_max_kmh=_get("SPEED_MAX_KMH", 60.0, float, lambda v: v >= 0),
        speed_variable_ratio=_get(
            "SPEED_VARIABLE_RATIO", 0.6, float, lambda v: 0 <= v <= 1
        ),
        speed_change_interval_ticks=_get(
            "SPEED_CHANGE_INTERVAL_TICKS", 4, int, lambda v: v >= 1
        ),
        speed_max_change_kmh_per_tick=_get(
            "SPEED_MAX_CHANGE_KMH_PER_TICK", 5.0, float, lambda v: v >= 0
        ),
        fuel_consumption=_get(
            "FUEL_CONSUMPTION", 0.005, float, lambda v: v >= 0
        ),
        nav_continuity_factor=_get(
            "NAV_CONTINUITY_FACTOR", 3.0, float, lambda v: v >= 0
        ),
        nav_max_continuity_gap_m=_get(
            "NAV_MAX_CONTINUITY_GAP_M", 3.0, float, lambda v: v >= 0
        ),
        log_transitions=_get(
            "LOG_TRANSITIONS", False, lambda v: str(v).strip().lower() in {"1", "true", "yes", "s", "si", "sí"}
        ),
        geofences_mode=geofences_mode,
        random_geofence_count=random_count,
        random_geofence_type=random_type,
        random_geofence_min_size=random_min_size,
        random_geofence_max_size=random_max_size,
        random_geofence_refill_rate_min=random_rate_min,
        random_geofence_refill_rate_max=random_rate_max,
        web_host=_get("WEB_HOST", "127.0.0.1"),
        web_port=_get("WEB_PORT", 9000, int, lambda v: 1 <= v <= 65535),
    )

    # ── Validaciones cruzadas ────────────────────────────────────
    if s.db_mode not in {"dry_run", "rollback", "commit"}:
        raise ConfigurationError("DB_MODE debe ser 'dry_run', 'rollback' o 'commit'")
    if s.speed_max_kmh < s.speed_min_kmh:
        raise ConfigurationError("SPEED_MAX_KMH no puede ser menor que SPEED_MIN_KMH")

    _settings = s
    return s


def generate_random_geofences(s: Settings) -> list[Geofence]:
    """Genera geofences aleatorias dentro del bbox de Bogotá."""
    zones = []
    for i in range(s.random_geofence_count):
        height = random.uniform(
            s.random_geofence_min_size,
            min(s.random_geofence_max_size, BBOX_LAT_MAX - BBOX_LAT_MIN),
        )
        width = random.uniform(
            s.random_geofence_min_size,
            min(s.random_geofence_max_size, BBOX_LON_MAX - BBOX_LON_MIN),
        )
        min_lat = random.uniform(BBOX_LAT_MIN, BBOX_LAT_MAX - height)
        min_lon = random.uniform(BBOX_LON_MIN, BBOX_LON_MAX - width)
        if s.random_geofence_type == "fuel":
            refill = random.uniform(
                s.random_geofence_refill_rate_min,
                s.random_geofence_refill_rate_max,
            )
        else:
            refill = 0.0
        polygon = box(min_lon, min_lat, min_lon + width, min_lat + height)
        zones.append(
            Geofence(
                id=-(i + 1),
                name=f"AUTO-{s.random_geofence_type.upper()}-{i + 1:03d}",
                description="Generada automáticamente al iniciar el servidor",
                geofence_type=s.random_geofence_type,
                mode="random",
                active=True,
                monitor_variable=round(refill, 2),
                polygon=polygon,
            )
        )
    return zones
