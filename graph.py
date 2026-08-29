"""
Acceso a la malla vial (topología pgRouting) en tiempo de ejecución.

No se carga el grafo completo en memoria: solo se consulta la vecindad
de un nodo bajo demanda, lo que escala sin problema a ~130k aristas.
"""

import math
import random

from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.ops import transform

EDGES_TABLE = "monitoreo_vehiculos.road_edges"

# Para interpolar distancias en metros, se proyecta a Web Mercator.
_to_metric = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_to_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


def _bearing(p1, p2) -> float:
    """Rumbo en grados [0, 360) desde p1 hacia p2 (coordenadas métricas x, y)."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def turn_angle(b1, b2) -> float:
    """Ángulo de giro en grados [0, 180] entre dos rumbos."""
    d = abs(b1 - b2) % 360.0
    return 180.0 - abs(d - 180.0)


class Edge:
    def __init__(self, edge_id: int, source: int, target: int, line):
        self.id = edge_id
        self.source = source
        self.target = target
        self.line = line  # LineString en EPSG:4326
        self.coords = list(line.coords)  # [(lon, lat), ...]
        self.line_metric = transform(_to_metric.transform, line)
        self.mcoords = list(self.line_metric.coords)  # [(x, y) en metros, ...]
        self.length_m = self.line_metric.length

    def endpoint_metric(self, node_id: int):
        """Coordenada (x, y) en metros del extremo que coincide con node_id."""
        if node_id == self.source:
            return self.mcoords[0]
        return self.mcoords[-1]

    def out_bearing(self, node_id: int):
        """Rumbo (grados) de salida del nodo a lo largo de la arista."""
        if len(self.mcoords) < 2:
            return None
        if node_id == self.source:
            return _bearing(self.mcoords[0], self.mcoords[1])
        return _bearing(self.mcoords[-1], self.mcoords[-2])


class RoadGraph:
    def __init__(self, pool):
        self.pool = pool

    @staticmethod
    def _edge_from_row(row) -> Edge:
        return Edge(row[0], row[1], row[2], shapely_wkt.loads(row[3]))

    async def random_edge(self) -> Edge:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                f"SELECT id, source, target, ST_AsText(geom) FROM {EDGES_TABLE} "
                "WHERE source IS NOT NULL AND target IS NOT NULL "
                "ORDER BY random() LIMIT 1"
            )
            row = await cur.fetchone()
        return self._edge_from_row(row)

    async def neighbors(self, node_id: int, exclude_edge_id: int | None = None) -> list[Edge]:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                f"SELECT id, source, target, ST_AsText(geom) FROM {EDGES_TABLE} "
                "WHERE source = %s OR target = %s",
                (node_id, node_id),
            )
            rows = await cur.fetchall()
        edges = [self._edge_from_row(r) for r in rows]
        if exclude_edge_id is not None and len(edges) > 1:
            edges = [e for e in edges if e.id != exclude_edge_id]
        return edges

    @staticmethod
    def pick_next(edges: list[Edge]) -> Edge:
        return random.choice(edges)
