"""
Simulación de vehículos moviéndose aleatoriamente sobre la malla vial.

Cada vehículo avanza una distancia = velocidad × Δt interpolando sobre la
geometría de la arista actual. Al llegar a un cruce, elige una arista
vecina al azar (random walk). El combustible decrece levemente y se
recarga a ritmo constante dentro de las zonas de recarga.
"""

import asyncio
import logging
import math
import random
from datetime import datetime, timezone

from config import Settings
from db import insert_report
from graph import RoadGraph, _bearing, _to_4326, turn_angle

log = logging.getLogger("sim")


class Vehicle:
    def __init__(self, vehicle_id: str, edge, settings: Settings):
        self.id = vehicle_id
        self.edge = edge
        self.pos_m = 0.0
        self.speed_kmh = random.uniform(settings.speed_min_kmh, settings.speed_max_kmh)
        self.target_speed_kmh = self.speed_kmh
        self.speed_is_variable = random.random() < settings.speed_variable_ratio
        self.ticks_since_speed_change = 0
        self.fuel = random.uniform(40.0, 100.0)
        self.forward = random.choice([True, False])
        self.settings = settings

    @property
    def _back_node(self) -> int:
        return self.edge.source if self.forward else self.edge.target

    @property
    def _ahead_node(self) -> int:
        return self.edge.target if self.forward else self.edge.source

    def _in_bearing(self):
        """Rumbo de llegada al nodo según la dirección de avance actual."""
        m = self.edge.mcoords
        if len(m) < 2:
            return None
        if self.forward:
            return _bearing(m[-2], m[-1])
        return _bearing(m[1], m[0])

    def _endpoint_gap_m(self, edge, node: int) -> float:
        """Distancia (m) entre el extremo de la arista actual y la candidata en el nodo."""
        cur = self.edge.endpoint_metric(node)
        nxt = edge.endpoint_metric(node)
        return math.hypot(nxt[0] - cur[0], nxt[1] - cur[1])

    def _pick_next(self, candidates: list, node: int):
        """Elige la siguiente arista ponderando la continuidad de dirección."""
        incoming = self._in_bearing()
        if incoming is None or len(candidates) == 1:
            return random.choice(candidates)
        weights = []
        factor = self.settings.nav_continuity_factor
        for e in candidates:
            out = e.out_bearing(node)
            if out is None:
                weights.append(1.0)
                continue
            ang = turn_angle(incoming, out)
            weights.append(1.0 + factor * (1.0 - ang / 180.0))
        return random.choices(candidates, weights=weights, k=1)[0]

    async def step(self, graph: RoadGraph) -> dict:
        s = self.settings

        # Algunos vehículos cambian periódicamente su velocidad objetivo y
        # se aproximan a ella con una aceleración limitada.
        self.ticks_since_speed_change += 1
        if self.speed_is_variable and (
            self.ticks_since_speed_change >= s.speed_change_interval_ticks
        ):
            self.target_speed_kmh = random.uniform(s.speed_min_kmh, s.speed_max_kmh)
            self.ticks_since_speed_change = 0

        if self.speed_is_variable:
            max_change = s.speed_max_change_kmh_per_tick
            delta = self.target_speed_kmh - self.speed_kmh
            self.speed_kmh += max(-max_change, min(max_change, delta))
        else:
            self.speed_kmh += random.uniform(-0.5, 0.5)
        self.speed_kmh = max(s.speed_min_kmh, min(s.speed_max_kmh, self.speed_kmh))

        dist = self.speed_kmh / 3.6 * s.tick_seconds
        self.pos_m += dist

        # Avanza a través de los cruces mientras haya aristas vecinas.
        guard = 0
        while self.pos_m >= self.edge.length_m and guard < 20:
            guard += 1
            node = self._ahead_node
            neighbors = await graph.neighbors(node, exclude_edge_id=self.edge.id)
            if not neighbors:
                # Calle sin salida: da la vuelta.
                self.forward = not self.forward
                self.pos_m = 0.0
                if s.log_transitions:
                    log.info("%s: calle sin salida en nodo %s → invierte dirección", self.id, node)
                break

            # Descarta aristas con discontinuidad geométrica en el nodo.
            candidates = [
                e for e in neighbors
                if self._endpoint_gap_m(e, node) <= s.nav_max_continuity_gap_m
            ] or neighbors

            prev_edge_id = self.edge.id
            next_edge = self._pick_next(candidates, node)
            overshoot = self.pos_m - self.edge.length_m
            self.edge = next_edge
            # Viaja alejándose del nodo de llegada.
            self.forward = next_edge.source == node
            self.pos_m = overshoot
            if s.log_transitions:
                log.info("%s: arista %s → nodo %s → arista %s", self.id, prev_edge_id, node, next_edge.id)

        self.pos_m = min(self.pos_m, self.edge.length_m)
        point_metric = self.edge.line_metric.interpolate(self.pos_m)
        lon, lat = _to_4326.transform(point_metric.x, point_metric.y)

        # Combustible: consumo base + recarga dentro de geofences fuel.
        self.fuel -= s.fuel_consumption * s.tick_seconds
        for gf in s.geofences:
            if gf.geofence_type == "fuel" and gf.contains(lat, lon):
                self.fuel += gf.monitor_variable * s.tick_seconds
                break
        self.fuel = max(0.0, min(100.0, self.fuel))

        return {
            "device_vehicle_id": self.id,
            "reported_at": datetime.now(timezone.utc),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed_kmh": round(self.speed_kmh, 2),
            "fuel_level": round(self.fuel, 2),
        }


class Simulation:
    def __init__(self, settings: Settings, pool, graph: RoadGraph, broadcaster):
        self.settings = settings
        self.pool = pool
        self.graph = graph
        self.broadcaster = broadcaster
        self.vehicles: list[Vehicle] = []
        self.state: dict[str, dict] = {}

    async def setup(self) -> None:
        for i in range(self.settings.num_vehicles):
            edge = await self.graph.random_edge()
            vid = f"AVL-{i + 1:03d}"
            self.vehicles.append(Vehicle(vid, edge, self.settings))
            log.info("Vehículo %s creado en arista %s", vid, edge.id)

    async def tick(self) -> None:
        for v in self.vehicles:
            packet = await v.step(self.graph)
            self.state[v.id] = packet
            try:
                await insert_report(self.pool, packet, self.settings.db_mode)
            except Exception as exc:  # noqa: BLE001
                # Un CHECK/error en una fila no debe tumbar la simulación.
                log.warning("Error insertando %s: %s", v.id, exc)
        await self.broadcaster.publish({"type": "snapshot", "vehicles": self.state})

    async def run(self) -> None:
        await self.setup()
        while True:
            await self.tick()
            await asyncio.sleep(self.settings.tick_seconds)
