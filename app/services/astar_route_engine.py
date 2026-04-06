from __future__ import annotations

import heapq
import math

from app.domain.models import RouteResult
from app.domain.models import SubwayNetwork
from app.services.route_engine import Cost
from app.services.route_engine import Edge
from app.services.route_engine import RouteEngine
from app.services.route_engine import State


class AStarRouteEngine(RouteEngine):
    """A* variant that preserves the original RouteEngine graph/result logic."""

    def __init__(self, network: SubwayNetwork):
        super().__init__(network)
        self._min_seconds_per_unit = self._build_min_seconds_per_unit()

    def find_route(self, start_station_id: str, end_station_id: str) -> RouteResult:
        if start_station_id not in self.network.stations:
            raise ValueError(f"Unknown start station: {start_station_id}")
        if end_station_id not in self.network.stations:
            raise ValueError(f"Unknown end station: {end_station_id}")
        if start_station_id == end_station_id:
            return RouteResult(
                total_time_sec=0,
                walking_time_sec=0,
                transfer_count=0,
                stop_count=0,
                station_ids=[start_station_id],
                line_sequence=[],
                steps=[],
            )

        start_states = [
            (start_station_id, line_id)
            for line_id in sorted(self.network.station_to_lines[start_station_id])
        ]
        goal_states = {
            (end_station_id, line_id)
            for line_id in self.network.station_to_lines[end_station_id]
        }
        goal_coordinate = self._station_coordinate(end_station_id)

        open_heap: list[tuple[Cost, Cost, State]] = []
        distances: dict[State, Cost] = {}
        parents: dict[State, tuple[State | None, Edge | None]] = {}

        for state in start_states:
            g_cost: Cost = (0, 0, 0, 0)
            distances[state] = g_cost
            parents[state] = (None, None)
            heapq.heappush(
                open_heap,
                (self._priority(state, g_cost, goal_coordinate), g_cost, state),
            )

        best_goal: State | None = None

        while open_heap:
            _, current_cost, state = heapq.heappop(open_heap)
            if current_cost != distances.get(state):
                continue
            if state in goal_states:
                best_goal = state
                break

            for edge in self.graph.get(state, []):
                next_cost = self._add_cost(current_cost, edge.cost)
                known_cost = distances.get(edge.target)
                if known_cost is None or next_cost < known_cost:
                    distances[edge.target] = next_cost
                    parents[edge.target] = (state, edge)
                    heapq.heappush(
                        open_heap,
                        (
                            self._priority(edge.target, next_cost, goal_coordinate),
                            next_cost,
                            edge.target,
                        ),
                    )

        if best_goal is None:
            raise ValueError(f"No route found between {start_station_id} and {end_station_id}")

        return self._build_result(best_goal, distances[best_goal], parents)

    def _priority(self, state: State, g_cost: Cost, goal_coordinate: tuple[float, float]) -> Cost:
        heuristic_time_sec = self._heuristic_time_sec(state, goal_coordinate)
        return (
            g_cost[0] + heuristic_time_sec,
            g_cost[1],
            g_cost[2],
            g_cost[3],
        )

    def _heuristic_time_sec(self, state: State, goal_coordinate: tuple[float, float]) -> int:
        if self._min_seconds_per_unit <= 0:
            return 0

        state_coordinate = self._station_coordinate(state[0])
        direct_distance_units = math.hypot(
            goal_coordinate[0] - state_coordinate[0],
            goal_coordinate[1] - state_coordinate[1],
        )
        if direct_distance_units <= 0:
            return 0

        return max(0, int(math.floor(direct_distance_units * self._min_seconds_per_unit)))

    def _build_min_seconds_per_unit(self) -> float:
        ratios: list[float] = []

        for segment in self.network.segments:
            distance_units = self._station_distance_units(
                segment.from_station_id,
                segment.to_station_id,
            )
            if distance_units > 0 and segment.travel_sec > 0:
                ratios.append(segment.travel_sec / distance_units)

        for walk_transfer in self.network.walk_transfers:
            distance_units = self._station_distance_units(
                walk_transfer.from_station_id,
                walk_transfer.to_station_id,
            )
            if distance_units > 0 and walk_transfer.duration_sec > 0:
                ratios.append(walk_transfer.duration_sec / distance_units)

        if not ratios:
            return 0.0
        return min(ratios)

    def _station_distance_units(self, from_station_id: str, to_station_id: str) -> float:
        x1, y1 = self._station_coordinate(from_station_id)
        x2, y2 = self._station_coordinate(to_station_id)
        return math.hypot(x2 - x1, y2 - y1)

    def _station_coordinate(self, station_id: str) -> tuple[float, float]:
        station = self.network.stations[station_id]
        return float(station.x), float(station.y)
