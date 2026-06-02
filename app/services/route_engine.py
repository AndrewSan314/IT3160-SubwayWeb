from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, replace

from app.domain.models import RouteResult
from app.domain.models import RouteStep
from app.domain.models import SubwayNetwork
from app.services.geo_utils import haversine_distance_m, euclidean_distance
from app.services.rain_penalty import rain_penalty_for_path
from app.services.travel_defaults import DEFAULT_DIAGRAM_WALK_SECONDS_PER_UNIT
from app.services.travel_defaults import DEFAULT_WALKING_M_PER_SEC
from app.services.travel_defaults import SUBWAY_SPEED_M_PER_SEC

MAX_AUTO_WALK_DISTANCE_M = 1500.0
WALKING_SPEED_M_PER_SEC = DEFAULT_WALKING_M_PER_SEC
WALK_COST_PENALTY_FACTOR = 5.0
EXPLICIT_WALK_COST_PENALTY_FACTOR = 2.0


State = tuple[str, str]
SearchNode = tuple[str, str, int, bool]
Cost = tuple[int, int, int, int]


@dataclass(frozen=True)
class Edge:
    target: State
    cost: Cost
    kind: str
    duration_sec: int
    rain_penalty_sec: int = 0
    walk_cost_factor: float = 1.0


class RouteEngine:
    def __init__(self, network: SubwayNetwork):
        self.network = network
        self.graph: dict[State, list[Edge]] = {}
        
        # Determine if we are using geographic coordinates (lat/lon) or diagram units (pixels)
        # Prioritize stops (GPS) if they exist.
        self.is_geographic = len(self.network.stops) > 0
        
        # If stops are missing, fallback to checking station coordinates
        if not self.is_geographic:
            self.is_geographic = True
            for st in self.network.stations.values():
                if abs(st.y) > 90 or abs(st.x) > 180:
                    self.is_geographic = False
                    break
        
        # For diagram coordinates (Pixels), assume units are roughly proportional to meters/seconds
        self.units_per_meter = 1.0

        # 1. Coordinate Loading Logic
        # We need to support both Diagram (Pixels) and GIS (GPS) coordinates.
        self.station_positions: dict[str, tuple[float, float]] = {}
        
        # Priority 1: Raw station x, y (could be pixels OR lat/lon)
        for st in self.network.stations.values():
            self.station_positions[st.id] = (st.y, st.x)

        # Priority 2: In geographic mode, try to find better GPS coords from 'stops'
        if self.is_geographic:
            # Fuzzy match stations to stops to get high-precision GPS
            for st_id in self.network.stations:
                # Try to find a stop that belongs to this station
                match = None
                # First try direct station_id match
                for stop in self.network.stops.values():
                    if stop.station_id == st_id:
                        match = stop
                        break
                # Then try fuzzy ID/name match if no direct match found
                if not match:
                    st_obj = self.network.stations[st_id]
                    for stop in self.network.stops.values():
                        if (stop.id.lower() in st_id.lower() or 
                            st_id.lower() in stop.id.lower() or
                            (st_obj.name and stop.name and st_obj.name.lower() == stop.name.lower())):
                            match = stop
                            break
                
                if match:
                    self.station_positions[st_id] = (match.latitude, match.longitude)

        self._build_graph()
        self._min_cost_per_distance = self._compute_min_cost_per_distance()
        self._build_spatial_index()
        self.states = tuple(sorted(self.graph.keys()))
        self.state_to_index = {state: i for i, state in enumerate(self.states)}

    def _build_spatial_index(self) -> None:
        """Create a grid-based index for fast station spatial lookup."""
        # Diagram mode uses pixels (approx 100px grid), Geographic uses degrees (0.01 deg approx 1km)
        self.grid_size = 0.01 if self.is_geographic else 100.0
        self.grid: dict[tuple[int, int], list[str]] = {}
        
        for station_id, coords in self.station_positions.items():
            cell = self._grid_cell(coords, self.grid_size)
            self.grid.setdefault(cell, []).append(station_id)

    @staticmethod
    def _grid_cell(coords: tuple[float, float], grid_size: float) -> tuple[int, int]:
        return (
            math.floor(coords[0] / grid_size),
            math.floor(coords[1] / grid_size),
        )

    def _get_distance(self, s1_id: str, s2_id: str) -> float:
        c1 = self.station_positions.get(s1_id)
        c2 = self.station_positions.get(s2_id)
        if not c1 or not c2:
            return 0.0
        
        if self.is_geographic:
            return haversine_distance_m(c1[0], c1[1], c2[0], c2[1])
        else:
            # Diagram mode: Euclidean distance (y is 0, x is 1)
            return math.sqrt((c1[1] - c2[1])**2 + (c1[0] - c2[0])**2)


    def _build_graph(self) -> None:
        """Construct the routing graph with ride, transfer, and walking edges."""
        opts = self.network.metadata.get("options", {})
        line_switch_penalty = opts.get("line_switch_penalty") or 0.0
        
        # Ensure all states exist in the graph
        for station_line in self.network.station_lines:
            self.graph.setdefault((station_line.station_id, station_line.line_id), [])

        # 1. Ride Edges (Subway segments)
        ride_speed_m_per_s = SUBWAY_SPEED_M_PER_SEC if self.is_geographic else 1.0

        for segment in self.network.segments:
            s1, s2 = segment.from_station_id, segment.to_station_id
            if self.is_geographic:
                dist = self._get_distance(s1, s2)
                travel_sec = max(1, int(round(dist / ride_speed_m_per_s)))
            else:
                travel_sec = segment.travel_sec if segment.travel_sec > 0 else 1

            source = (s1, segment.line_id)
            target = (s2, segment.line_id)
            
            if source in self.graph and target in self.graph:
                ride_cost = (travel_sec, 0, 0, 1) # Cost, WalkTime, Transfers, Stops
                self.graph[source].append(Edge(target, ride_cost, "ride", travel_sec))
                self.graph[target].append(Edge(source, ride_cost, "ride", travel_sec))

        # 2. Transfer Edges
        # 2.1 Explicit Transfers from topology data
        for transfer in self.network.transfers:
            source = (transfer.station_id, transfer.from_line_id)
            target = (transfer.station_id, transfer.to_line_id)
            if source in self.graph and target in self.graph:
                # Add penalty if changing lines at the station
                cost_val = int(transfer.transfer_sec + line_switch_penalty)
                cost = (cost_val, 0, 1, 0) # Cost, WalkTime, Transfers, Stops
                self.graph[source].append(
                    Edge(target, cost, "transfer", transfer.transfer_sec)
                )

        # 2.2 Implicit Auto-Transfers (Connecting lines at the same station)
        default_transfer_sec = opts.get("default_transfer_sec") or 30
        for station_id, line_ids in self.network.station_to_lines.items():
            if len(line_ids) > 1:
                sorted_lines = sorted(line_ids)
                for i, l1 in enumerate(sorted_lines):
                    for j, l2 in enumerate(sorted_lines):
                        if i == j: continue
                        source = (station_id, l1)
                        target = (station_id, l2)
                        
                        if source in self.graph and target in self.graph:
                            # Only add if not already present from explicit data
                            exists = any(e.target == target and e.kind == "transfer" for e in self.graph[source])
                            if not exists:
                                # Every auto-transfer is a line switch
                                trans_cost = int(default_transfer_sec + line_switch_penalty)
                                cost = (trans_cost, 0, 1, 0)
                                self.graph[source].append(
                                    Edge(target, cost, "transfer", default_transfer_sec)
                                )

        # 3. Inter-State Walking (Proximity-based transfers)
        admin_walk_bypass_pairs = {
            tuple(pair)
            for pair in self.network.metadata.get("admin_effects", {}).get("walk_bypass_pairs", [])
            if isinstance(pair, list) and len(pair) == 2
        }
        for transfer in self.network.walk_transfers:
            if (transfer.from_station_id, transfer.to_station_id) not in admin_walk_bypass_pairs:
                continue
            from_lines = self.network.station_to_lines.get(transfer.from_station_id, set())
            to_lines = self.network.station_to_lines.get(transfer.to_station_id, set())
            for from_line_id in from_lines:
                for to_line_id in to_lines:
                    source = (transfer.from_station_id, from_line_id)
                    target = (transfer.to_station_id, to_line_id)
                    if source not in self.graph or target not in self.graph:
                        continue
                    penalty = line_switch_penalty if from_line_id != to_line_id else 0.0
                    cost = (
                        int(transfer.duration_sec * EXPLICIT_WALK_COST_PENALTY_FACTOR + penalty),
                        transfer.duration_sec,
                        0,
                        0,
                    )
                    self.graph[source].append(
                        Edge(
                            target,
                            cost,
                            "walk",
                            transfer.duration_sec,
                            walk_cost_factor=EXPLICIT_WALK_COST_PENALTY_FACTOR,
                        )
                    )

        if self.is_geographic:
            walk_speed_m_per_s = WALKING_SPEED_M_PER_SEC
            radius = opts.get("auto_walk_transfer_radius") or 1500.0
        else:
            sec_per_unit = opts.get("auto_walk_seconds_per_unit") or DEFAULT_DIAGRAM_WALK_SECONDS_PER_UNIT
            walk_speed_m_per_s = 1.0 / sec_per_unit
            radius = opts.get("auto_walk_transfer_radius") or 25.0
        
        # Build set of existing connections to avoid redundant walk edges
        existing_conns = set()
        for src, edges in self.graph.items():
            for e in edges: existing_conns.add((src, e.target))

        station_ids = sorted([sid for sid in self.station_positions if sid in self.network.station_to_lines])
        for s1_id, s2_id in self._nearby_station_pairs(station_ids, radius):
            s1_lines = self.network.station_to_lines[s1_id]
            s2_lines = self.network.station_to_lines[s2_id]
            dist = self._get_distance(s1_id, s2_id)
            if dist <= 0 or dist > radius:
                continue
            walk_sec = max(1, int(round(dist / walk_speed_m_per_s)))

            for l1 in s1_lines:
                for l2 in s2_lines:
                    src, tgt = (s1_id, l1), (s2_id, l2)
                    if src in self.graph and tgt in self.graph and (src, tgt) not in existing_conns:
                        # Apply line switch penalty if lines are different
                        penalty = line_switch_penalty if l1 != l2 else 0.0
                        walk_cost_val = int(walk_sec * WALK_COST_PENALTY_FACTOR + penalty)
                        walk_cost = (walk_cost_val, walk_sec, 0, 0)

                        self.graph[src].append(
                            Edge(tgt, walk_cost, "walk", walk_sec, walk_cost_factor=WALK_COST_PENALTY_FACTOR)
                        )
                        self.graph[tgt].append(
                            Edge(src, walk_cost, "walk", walk_sec, walk_cost_factor=WALK_COST_PENALTY_FACTOR)
                        )
                        existing_conns.add((src, tgt))
                        existing_conns.add((tgt, src))

        # Deterministic sorting for consistency
        for edges in self.graph.values():
            edges.sort(key=lambda e: (e.target[0], e.target[1], e.kind, e.duration_sec))

        # Keep deterministic traversal order, but sort once at build-time
        # instead of sorting on every routing query.
        for edges in self.graph.values():
            edges.sort(
                key=lambda item: (
                    item.target[0],
                    item.target[1],
                    item.kind,
                    item.duration_sec,
                )
            )

    def _nearby_station_pairs(
        self,
        station_ids: list[str],
        radius: float,
    ) -> list[tuple[str, str]]:
        if radius <= 0:
            return []

        if self.is_geographic:
            cell_size = max(radius / 111_000.0, 0.000001)
            neighbor_span = 2
        else:
            cell_size = max(radius, 0.000001)
            neighbor_span = 1

        buckets: dict[tuple[int, int], list[str]] = {}
        for station_id in station_ids:
            coords = self.station_positions.get(station_id)
            if coords is None:
                continue
            buckets.setdefault(self._grid_cell(coords, cell_size), []).append(station_id)

        pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for station_id in station_ids:
            coords = self.station_positions.get(station_id)
            if coords is None:
                continue
            cell_y, cell_x = self._grid_cell(coords, cell_size)
            for dy in range(-neighbor_span, neighbor_span + 1):
                for dx in range(-neighbor_span, neighbor_span + 1):
                    for other_id in buckets.get((cell_y + dy, cell_x + dx), []):
                        if other_id == station_id:
                            continue
                        pair = tuple(sorted((station_id, other_id)))
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)
                        pairs.append(pair)
        pairs.sort()
        return pairs

    def _compute_min_cost_per_distance(self) -> float:
        min_ratio: float | None = None
        for source, edges in self.graph.items():
            for edge in edges:
                distance = self._get_distance(source[0], edge.target[0])
                if distance <= 0 or edge.cost[0] <= 0:
                    continue
                ratio = edge.cost[0] / distance
                if min_ratio is None or ratio < min_ratio:
                    min_ratio = ratio
        return min_ratio or 0.0

    def _heuristic(self, state: State, goal_station_id: str) -> Cost:
        """Admissible lower-bound cost from state to goal station."""
        current_station_id = state[0]
        if current_station_id == goal_station_id:
            return (0, 0, 0, 0)
            
        c1 = self.station_positions.get(current_station_id)
        c2 = self.station_positions.get(goal_station_id)

        if c1 and c2:
            if self.is_geographic:
                dist_m = haversine_distance_m(c1[0], c1[1], c2[0], c2[1])
            else:
                dist_m = euclidean_distance(c1[1], c1[0], c2[1], c2[0])
            h_time = math.floor(dist_m * self._min_cost_per_distance)
            
            return (max(0, int(h_time)), 0, 0, 0)
        
        return (0, 0, 0, 0)

    def find_route(
        self,
        start_station_id: str,
        end_station_id: str,
        *,
        rain_zones: list[dict] | None = None,
    ) -> RouteResult:
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

        try:
            _, _, route, _ = self.find_route_between_candidates(
                [(start_station_id, start_station_id, (0, 0, 0, 0))],
                [(end_station_id, end_station_id, (0, 0, 0, 0))],
                rain_zones=rain_zones,
            )
        except ValueError as error:
            raise ValueError(f"No route found between {start_station_id} and {end_station_id}") from error
        return route

    def find_route_through_stations(
        self,
        station_ids: list[str],
        *,
        rain_zones: list[dict] | None = None,
    ) -> RouteResult:
        if len(station_ids) < 2:
            raise ValueError("At least two station ids are required")

        normalized_station_ids: list[str] = []
        for station_id in station_ids:
            if station_id not in self.network.stations:
                raise ValueError(f"Unknown station: {station_id}")
            if normalized_station_ids and station_id == normalized_station_ids[-1]:
                continue
            normalized_station_ids.append(station_id)

        if len(normalized_station_ids) == 1:
            station_id = normalized_station_ids[0]
            return RouteResult(
                total_time_sec=0,
                walking_time_sec=0,
                transfer_count=0,
                stop_count=0,
                station_ids=[station_id],
                line_sequence=[],
                steps=[],
            )

        _, _, route, _ = self.find_route_between_candidates(
            [(normalized_station_ids[0], normalized_station_ids[0], (0, 0, 0, 0))],
            [(normalized_station_ids[-1], normalized_station_ids[-1], (0, 0, 0, 0))],
            via_station_ids=normalized_station_ids[1:-1],
            rain_zones=rain_zones,
        )
        return route

    def find_best_route_for_points(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        walking_seconds_per_pixel: float = 1.0,
        candidate_limit: int | None = None,
        max_station_walk_sec: int | None = 60,
        start_preferred_line_ids: list[str] | None = None,
        end_preferred_line_ids: list[str] | None = None,
        via_station_ids: list[str] | None = None,
    ) -> dict:
        ordered_via_station_ids = list(via_station_ids or [])
        for via_station_id in ordered_via_station_ids:
            if via_station_id not in self.network.stations:
                raise ValueError(f"Unknown via station: {via_station_id}")

        start_candidates = self._candidate_stations(
            start_x,
            start_y,
            walking_seconds_per_pixel,
            candidate_limit or 3,
            max_station_walk_sec,
            prefer_nearest=False,
            preferred_line_ids=set(start_preferred_line_ids or []),
        )
        end_candidates = self._candidate_stations(
            end_x,
            end_y,
            walking_seconds_per_pixel,
            candidate_limit or 3,
            max_station_walk_sec,
            prefer_nearest=False,
            preferred_line_ids=set(end_preferred_line_ids or []),
        )

        start_options = []
        for item in start_candidates:
            station_id, distance = item
            access_time = int(round(distance * walking_seconds_per_pixel))
            start_options.append(
                (
                    item,
                    station_id,
                    (int(access_time * WALK_COST_PENALTY_FACTOR), 0, 0, 0),
                )
            )
        end_options = []
        for item in end_candidates:
            station_id, distance = item
            egress_time = int(round(distance * walking_seconds_per_pixel))
            end_options.append(
                (
                    item,
                    station_id,
                    (int(egress_time * WALK_COST_PENALTY_FACTOR), 0, 0, 0),
                )
            )

        try:
            selected_start, selected_end, route, _ = self.find_route_between_candidates(
                start_options,
                end_options,
                via_station_ids=ordered_via_station_ids,
                require_ride=True,
            )
        except ValueError as error:
            raise ValueError("No route found for the selected points") from error

        start_station_id, start_distance = selected_start
        end_station_id, end_distance = selected_end
        access_time_sec = int(round(start_distance * walking_seconds_per_pixel))
        egress_time_sec = int(round(end_distance * walking_seconds_per_pixel))
        point_walking_time_sec = access_time_sec + egress_time_sec
        best_result = {
            "start_point": {"x": start_x, "y": start_y},
            "end_point": {"x": end_x, "y": end_y},
            "selected_start_station": self._station_payload(start_station_id),
            "selected_end_station": self._station_payload(end_station_id),
            "via_stations": [
                self._station_payload(station_id)
                for station_id in ordered_via_station_ids
            ],
            "access_walk_distance_px": round(start_distance, 2),
            "egress_walk_distance_px": round(end_distance, 2),
            "access_walk_time_sec": access_time_sec,
            "egress_walk_time_sec": egress_time_sec,
            "total_journey_time_sec": route.total_time_sec + point_walking_time_sec,
            "route": route.to_dict(),
        }

        return best_result

    def find_route_between_candidates(
        self,
        start_options: list[tuple[object, str, Cost]],
        end_options: list[tuple[object, str, Cost]],
        via_station_ids: list[str] | None = None,
        *,
        require_ride: bool = False,
        rain_zones: list[dict] | None = None,
    ) -> tuple[object, object, RouteResult, Cost]:
        ordered_via_station_ids = list(via_station_ids or [])
        for _, station_id, _ in [*start_options, *end_options]:
            if station_id not in self.network.stations:
                raise ValueError(f"Unknown station: {station_id}")
        for station_id in ordered_via_station_ids:
            if station_id not in self.network.stations:
                raise ValueError(f"Unknown via station: {station_id}")
        if not start_options or not end_options:
            raise ValueError("At least one start and end candidate are required")

        terminals_by_station: dict[str, list[tuple[object, Cost]]] = {}
        end_station_ids: set[str] = set()
        for key, station_id, terminal_cost in end_options:
            terminals_by_station.setdefault(station_id, []).append((key, terminal_cost))
            end_station_ids.add(station_id)

        end_station_ids_tuple = tuple(sorted(end_station_ids))
        counter = 0
        pq: list[tuple[Cost, Cost, int, SearchNode]] = []
        distances: dict[SearchNode, Cost] = {}
        parents: dict[SearchNode, tuple[SearchNode | None, Edge | None]] = {}
        start_keys: dict[SearchNode, object] = {}
        start_station_ids: dict[SearchNode, str] = {}
        heuristic_cache: dict[tuple[State, int], Cost] = {}

        for key, station_id, initial_cost in start_options:
            via_index = self._advance_via_index(station_id, ordered_via_station_ids, 0)
            for line_id in sorted(self.network.station_to_lines.get(station_id, set())):
                node: SearchNode = (station_id, line_id, via_index, False)
                if node in distances and distances[node] <= initial_cost:
                    continue
                distances[node] = initial_cost
                parents[node] = (None, None)
                start_keys[node] = key
                start_station_ids[node] = station_id
                estimated = self._add_cost(
                    initial_cost,
                    self._search_heuristic(
                        node,
                        ordered_via_station_ids,
                        end_station_ids_tuple,
                        heuristic_cache,
                    ),
                )
                counter += 1
                heapq.heappush(pq, (estimated, initial_cost, counter, node))

        best_goal_node: SearchNode | None = None
        best_goal_cost: Cost | None = None
        best_end_key: object | None = None

        while pq:
            estimated, curr_cost, _, curr_node = heapq.heappop(pq)
            if best_goal_cost is not None and estimated >= best_goal_cost:
                break
            if curr_cost > distances.get(curr_node, (float("inf"), 0, 0, 0)):
                continue

            station_id, line_id, via_index, has_ride = curr_node
            is_unrequested_round_trip = (
                require_ride
                and not ordered_via_station_ids
                and start_station_ids[curr_node] == station_id
            )
            if (
                via_index == len(ordered_via_station_ids)
                and (has_ride or not require_ride)
                and not is_unrequested_round_trip
            ):
                for end_key, terminal_cost in terminals_by_station.get(station_id, []):
                    total_cost = self._add_cost(curr_cost, terminal_cost)
                    if best_goal_cost is None or total_cost < best_goal_cost:
                        best_goal_node = curr_node
                        best_goal_cost = total_cost
                        best_end_key = end_key

            for base_edge in self.graph.get((station_id, line_id), []):
                edge = self._edge_with_rain_penalty(
                    (station_id, line_id),
                    base_edge,
                    rain_zones or [],
                )
                next_station_id, next_line_id = edge.target
                next_via_index = self._advance_via_index(
                    next_station_id,
                    ordered_via_station_ids,
                    via_index,
                )
                next_node: SearchNode = (
                    next_station_id,
                    next_line_id,
                    next_via_index,
                    has_ride or edge.kind == "ride",
                )
                new_cost = self._add_cost(curr_cost, edge.cost)
                if next_node in distances and distances[next_node] <= new_cost:
                    continue
                distances[next_node] = new_cost
                parents[next_node] = (curr_node, edge)
                start_keys[next_node] = start_keys[curr_node]
                start_station_ids[next_node] = start_station_ids[curr_node]
                estimated_total = self._add_cost(
                    new_cost,
                    self._search_heuristic(
                        next_node,
                        ordered_via_station_ids,
                        end_station_ids_tuple,
                        heuristic_cache,
                    ),
                )
                counter += 1
                heapq.heappush(pq, (estimated_total, new_cost, counter, next_node))

        if best_goal_node is None or best_goal_cost is None:
            raise ValueError("No route found between candidate stations")

        route = self._build_result_from_search_node(best_goal_node, parents)
        return start_keys[best_goal_node], best_end_key, route, best_goal_cost

    def _edge_with_rain_penalty(
        self,
        source: State,
        edge: Edge,
        rain_zones: list[dict],
    ) -> Edge:
        if edge.kind != "walk" or not rain_zones or not self.is_geographic:
            return edge

        source_position = self.station_positions.get(source[0])
        target_position = self.station_positions.get(edge.target[0])
        if source_position is None or target_position is None:
            return edge

        rain_penalty_sec = rain_penalty_for_path(
            [
                (source_position[1], source_position[0]),
                (target_position[1], target_position[0]),
            ],
            rain_zones,
            WALKING_SPEED_M_PER_SEC,
        )["penalty_sec"]
        if rain_penalty_sec <= 0:
            return edge

        return replace(
            edge,
            cost=(
                edge.cost[0] + int(round(rain_penalty_sec * edge.walk_cost_factor)),
                edge.cost[1] + rain_penalty_sec,
                edge.cost[2],
                edge.cost[3],
            ),
            duration_sec=edge.duration_sec + rain_penalty_sec,
            rain_penalty_sec=rain_penalty_sec,
        )

    @staticmethod
    def _merge_leg_results(legs: list[RouteResult]) -> RouteResult:
        if not legs:
            raise ValueError("No route legs to merge")

        total_time_sec = 0
        walking_time_sec = 0
        rain_penalty_sec = 0
        transfer_count = 0
        stop_count = 0
        station_ids: list[str] = []
        line_sequence: list[str] = []
        steps: list[RouteStep] = []

        for index, leg in enumerate(legs):
            total_time_sec += leg.total_time_sec
            walking_time_sec += leg.walking_time_sec
            rain_penalty_sec += leg.rain_penalty_sec
            transfer_count += leg.transfer_count
            stop_count += leg.stop_count
            steps.extend(leg.steps)

            if index == 0:
                station_ids.extend(leg.station_ids)
            else:
                station_ids.extend(leg.station_ids[1:])

            for line_id in leg.line_sequence:
                if not line_sequence or line_sequence[-1] != line_id:
                    line_sequence.append(line_id)

        return RouteResult(
            total_time_sec=total_time_sec,
            walking_time_sec=walking_time_sec,
            transfer_count=transfer_count,
            stop_count=stop_count,
            station_ids=station_ids,
            line_sequence=line_sequence,
            steps=steps,
            rain_penalty_sec=rain_penalty_sec,
        )

    @staticmethod
    def _add_cost(left: Cost, right: Cost) -> Cost:
        return (
            left[0] + right[0],
            left[1] + right[1],
            left[2] + right[2],
            left[3] + right[3],
        )

    @staticmethod
    def _advance_via_index(
        station_id: str,
        via_station_ids: list[str],
        current_index: int,
    ) -> int:
        next_index = current_index
        while next_index < len(via_station_ids) and station_id == via_station_ids[next_index]:
            next_index += 1
        return next_index

    def _search_heuristic(
        self,
        node: SearchNode,
        via_station_ids: list[str],
        end_station_ids: tuple[str, ...],
        cache: dict[tuple[State, int], Cost],
    ) -> Cost:
        state = (node[0], node[1])
        via_index = node[2]
        if via_index < len(via_station_ids):
            targets = (via_station_ids[via_index],)
        else:
            targets = end_station_ids
        cache_key = (state, via_index)
        if cache_key not in cache:
            cache[cache_key] = min(
                (self._heuristic(state, target) for target in targets),
                default=(0, 0, 0, 0),
            )
        return cache[cache_key]


    def _candidate_stations(
        self,
        x: float,
        y: float,
        walking_seconds_per_pixel: float,
        candidate_limit: int | None,
        max_station_walk_sec: int | None,
        prefer_nearest: bool,
        preferred_line_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        # Use spatial grid for fast filtering
        target_lat, target_lon = (y, x) if self.is_geographic else (y, x) # Standardize
        # Wait, self.station_positions stores (latitude, longitude) or (y, x).
        # In diagram mode, station.x, station.y are pixels.
        
        # Grid lookup
        lat_grid, lon_grid = self._grid_cell((target_lat, target_lon), self.grid_size)
        
        candidate_ids = set()
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                cell = (lat_grid + dy, lon_grid + dx)
                candidate_ids.update(self.grid.get(cell, []))
        
        if not candidate_ids:
            # Fallback to all stations if grid lookup failed to find anything nearby
            candidate_ids = set(self.network.stations.keys())

        candidates = []
        for sid in candidate_ids:
            st = self.network.stations[sid]
            dist = euclidean_distance(x, y, st.x, st.y)
            
            # If preferred line requested, prioritize stations on those lines
            if preferred_line_ids and not (self.network.station_to_lines[sid] & preferred_line_ids):
                continue
            
            candidates.append((sid, dist))

        # Apply distance filter IF it doesn't empty the list (soft limit behavior)
        if max_station_walk_sec is not None:
            filtered = [
                c for c in candidates 
                if int(round(c[1] * walking_seconds_per_pixel)) <= max_station_walk_sec
            ]
            if filtered:
                candidates = filtered

        if not candidates and preferred_line_ids:
            # Fallback: ignore the grid and search all stations for the preferred line
            all_stations = self.network.stations.values()
            all_candidates = []
            for station in all_stations:
                if self.network.station_to_lines[station.id] & preferred_line_ids:
                    dist = euclidean_distance(x, y, station.x, station.y)
                    all_candidates.append((station.id, dist))
            
            if max_station_walk_sec is not None:
                filtered = [
                    c for c in all_candidates 
                    if int(round(c[1] * walking_seconds_per_pixel)) <= max_station_walk_sec
                ]
                if filtered:
                    all_candidates = filtered
            
            candidates = all_candidates
            
            # If still no candidates found, fallback to all stations ignoring line preference
            if not candidates:
                return self._candidate_stations(
                    x, y, walking_seconds_per_pixel, candidate_limit, 
                    max_station_walk_sec, prefer_nearest, preferred_line_ids=None
                )

        candidates.sort(key=lambda item: (item[1], item[0]))
        
        if prefer_nearest and candidates:
            return [candidates[0]]

        if candidate_limit is None or candidate_limit <= 0 or candidate_limit >= len(candidates):
            return candidates
        return candidates[:candidate_limit]

    def _station_payload(self, station_id: str) -> dict:
        station = self.network.stations[station_id]
        return {
            "id": station.id,
            "name": station.name,
            "x": station.x,
            "y": station.y,
            "line_ids": sorted(self.network.station_to_lines[station.id]),
        }


    def _build_result(
        self,
        goal_state: State,
        total_cost: Cost,
        parents: dict[State, tuple[State | None, Edge | None]],
    ) -> RouteResult:
        states: list[State] = []
        steps: list[RouteStep] = []
        current: State | None = goal_state

        while current is not None:
            previous, edge = parents[current]
            states.append(current)
            if previous is not None and edge is not None:
                steps.append(
                    RouteStep(
                        kind=edge.kind,
                        station_id=previous[0],
                        line_id=previous[1],
                        next_station_id=current[0],
                        duration_sec=edge.duration_sec,
                        rain_penalty_sec=edge.rain_penalty_sec,
                    )
                )
            current = previous

        states.reverse()
        steps.reverse()

        station_ids = [states[0][0]]
        for step in steps:
            if step.next_station_id and step.next_station_id != station_ids[-1]:
                station_ids.append(step.next_station_id)

        return RouteResult(
            total_time_sec=sum(step.duration_sec for step in steps),
            walking_time_sec=total_cost[1],
            transfer_count=total_cost[2],
            stop_count=total_cost[3],
            station_ids=station_ids,
            line_sequence=self._extract_line_sequence(states, steps),
            steps=steps,
            rain_penalty_sec=sum(step.rain_penalty_sec for step in steps),
        )

    def _build_result_from_search_node(
        self,
        goal_node: SearchNode,
        parents: dict[SearchNode, tuple[SearchNode | None, Edge | None]],
    ) -> RouteResult:
        nodes: list[SearchNode] = []
        edges: list[Edge] = []
        current: SearchNode | None = goal_node

        while current is not None:
            previous, edge = parents[current]
            nodes.append(current)
            if previous is not None and edge is not None:
                edges.append(edge)
            current = previous

        nodes.reverse()
        edges.reverse()
        states: list[State] = [(node[0], node[1]) for node in nodes]
        steps: list[RouteStep] = []
        total_cost = (0, 0, 0, 0)

        for previous_state, current_state, edge in zip(states, states[1:], edges, strict=False):
            total_cost = self._add_cost(total_cost, edge.cost)
            steps.append(
                RouteStep(
                    kind=edge.kind,
                    station_id=previous_state[0],
                    line_id=previous_state[1],
                    next_station_id=current_state[0],
                    duration_sec=edge.duration_sec,
                    rain_penalty_sec=edge.rain_penalty_sec,
                )
            )

        if not states:
            return RouteResult(0, 0, 0, 0, [], [], [])

        station_ids = [states[0][0]]
        for step in steps:
            if step.next_station_id and step.next_station_id != station_ids[-1]:
                station_ids.append(step.next_station_id)

        return RouteResult(
            total_time_sec=sum(step.duration_sec for step in steps),
            walking_time_sec=total_cost[1],
            transfer_count=total_cost[2],
            stop_count=total_cost[3],
            station_ids=station_ids,
            line_sequence=self._extract_line_sequence(states, steps),
            steps=steps,
            rain_penalty_sec=sum(step.rain_penalty_sec for step in steps),
        )


    def _find_edge(self, source: State, target: State) -> Edge | None:
        for edge in self.graph.get(source, []):
            if edge.target == target:
                return edge
        return None

    @staticmethod
    def _extract_line_sequence(states: list[State], steps: list[RouteStep]) -> list[str]:
        sequence: list[str] = []
        current_line: str | None = None

        for state, step in zip(states, steps, strict=False):
            if step.kind != "ride":
                continue
            if state[1] != current_line:
                sequence.append(state[1])
                current_line = state[1]

        if steps and steps[-1].kind == "ride":
            last_line = states[-1][1]
            if not sequence or sequence[-1] != last_line:
                sequence.append(last_line)

        return sequence
