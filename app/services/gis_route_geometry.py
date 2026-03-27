from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.walk_network import haversine_distance_m


Coordinate = tuple[float, float]
LINE_MATCH_THRESHOLD_M = 350.0
STEP_SNAP_THRESHOLD_M = 600.0
RUN_AVERAGE_SNAP_THRESHOLD_M = 450.0


@dataclass(frozen=True)
class SnapPoint:
    point: Coordinate
    distance_m: float
    segment_index: int
    segment_offset: float


def build_ride_path_features(
    route_steps: list[dict[str, Any]],
    station_coords_by_id: dict[str, Coordinate],
    stations_geojson: dict[str, Any] | None,
    lines_geojson: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    del stations_geojson
    if not _is_valid_geojson(lines_geojson):
        return []

    all_line_features = lines_geojson.get("features", [])
    ride_features: list[dict[str, Any]] = []

    for ride_group in _group_contiguous_ride_steps(route_steps):
        line_id = ride_group[0].get("line_id")
        station_sequence = _build_station_sequence_for_group(
            ride_group,
            station_coords_by_id,
        )
        if len(station_sequence) < 2:
            continue

        candidate_features = _match_line_features_to_station_sequence(
            station_sequence,
            all_line_features,
        )
        coordinates = _build_run_path_coordinates(
            station_sequence,
            candidate_features,
        )
        ride_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lon, lat in coordinates],
                },
                "properties": {
                    "kind": "ride",
                    "line_id": line_id,
                },
            }
        )

    return ride_features


def _match_line_features_to_station_sequence(
    station_sequence: list[Coordinate],
    line_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not station_sequence:
        return line_features

    scored_features: list[tuple[int, float, dict[str, Any]]] = []
    for feature in line_features:
        matched_distances = [
            _distance_to_geometry_m(point, feature.get("geometry", {}))
            for point in station_sequence
        ]
        nearby_distances = [
            distance_m
            for distance_m in matched_distances
            if distance_m <= LINE_MATCH_THRESHOLD_M
        ]
        if not nearby_distances:
            continue
        scored_features.append(
            (
                len(nearby_distances),
                sum(nearby_distances) / len(nearby_distances),
                feature,
            )
        )

    if not scored_features:
        return line_features

    scored_features.sort(key=lambda item: (-item[0], item[1]))
    best_match_count = scored_features[0][0]
    minimum_match_count = max(2, best_match_count - 1)
    matched_features = [
        feature
        for match_count, _, feature in scored_features
        if match_count >= minimum_match_count
    ]
    if not matched_features:
        matched_features = [scored_features[0][2]]
    return matched_features[:6]


def _group_contiguous_ride_steps(route_steps: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []
    current_line_id: str | None = None

    for step in route_steps:
        if step.get("kind") != "ride" or not step.get("next_station_id"):
            if current_group:
                groups.append(current_group)
                current_group = []
                current_line_id = None
            continue

        step_line_id = str(step.get("line_id"))
        if current_group and step_line_id != current_line_id:
            groups.append(current_group)
            current_group = []

        current_group.append(step)
        current_line_id = step_line_id

    if current_group:
        groups.append(current_group)
    return groups


def _build_station_sequence_for_group(
    ride_group: list[dict[str, Any]],
    station_coords_by_id: dict[str, Coordinate],
) -> list[Coordinate]:
    coordinates: list[Coordinate] = []
    for step in ride_group:
        start_coordinate = station_coords_by_id.get(step.get("station_id"))
        end_coordinate = station_coords_by_id.get(step.get("next_station_id"))
        if not start_coordinate or not end_coordinate:
            continue

        if not coordinates:
            coordinates.append(start_coordinate)
        coordinates.append(end_coordinate)

    deduped: list[Coordinate] = []
    for coordinate in coordinates:
        if deduped and _coordinates_equal(deduped[-1], coordinate):
            continue
        deduped.append(coordinate)
    return deduped


def _build_run_path_coordinates(
    station_sequence: list[Coordinate],
    line_features: list[dict[str, Any]],
) -> list[Coordinate]:
    if len(station_sequence) == 2:
        return _build_step_path_coordinates(
            station_sequence[0],
            station_sequence[1],
            line_features,
        )

    best_candidate: tuple[float, int, list[Coordinate]] | None = None
    for feature in line_features:
        for line in _iter_line_strings(feature.get("geometry", {})):
            snapped_points = [_snap_point_to_line(station_coordinate, line) for station_coordinate in station_sequence]
            if not _snaps_follow_single_direction(snapped_points):
                continue

            average_distance_m = sum(snap.distance_m for snap in snapped_points) / len(snapped_points)
            path_coordinates = _slice_line_between_snaps(line, snapped_points[0], snapped_points[-1])
            candidate = (average_distance_m, -len(path_coordinates), path_coordinates)
            if best_candidate is None or candidate < best_candidate:
                best_candidate = candidate

    if best_candidate is not None and best_candidate[0] <= RUN_AVERAGE_SNAP_THRESHOLD_M:
        return best_candidate[2]

    merged_coordinates: list[Coordinate] = []
    for start_coordinate, end_coordinate in zip(station_sequence, station_sequence[1:], strict=False):
        path_coordinates = _build_step_path_coordinates(
            start_coordinate,
            end_coordinate,
            line_features,
        )
        if not merged_coordinates:
            merged_coordinates.extend(path_coordinates)
            continue
        merged_coordinates.extend(path_coordinates[1:] if len(path_coordinates) > 1 else path_coordinates)

    return _dedupe_coordinates(merged_coordinates)


def _build_step_path_coordinates(
    start_coordinate: Coordinate,
    end_coordinate: Coordinate,
    line_features: list[dict[str, Any]],
) -> list[Coordinate]:
    best_candidate: tuple[float, int, list[Coordinate]] | None = None

    for feature in line_features:
        for line in _iter_line_strings(feature.get("geometry", {})):
            start_snap = _snap_point_to_line(start_coordinate, line)
            end_snap = _snap_point_to_line(end_coordinate, line)
            snapped_distance_m = start_snap.distance_m + end_snap.distance_m
            path_coordinates = _slice_line_between_snaps(line, start_snap, end_snap)
            candidate = (snapped_distance_m, -len(path_coordinates), path_coordinates)
            if best_candidate is None or candidate < best_candidate:
                best_candidate = candidate

    if best_candidate is None or best_candidate[0] > STEP_SNAP_THRESHOLD_M:
        return [start_coordinate, end_coordinate]
    return best_candidate[2]


def _distance_to_geometry_m(point: Coordinate, geometry: dict[str, Any]) -> float:
    best_distance_m = float("inf")
    for line in _iter_line_strings(geometry):
        snap = _snap_point_to_line(point, line)
        best_distance_m = min(best_distance_m, snap.distance_m)
    return best_distance_m


def _snap_point_to_line(point: Coordinate, line: list[Coordinate]) -> SnapPoint:
    best_snap: SnapPoint | None = None
    for segment_index, (start, end) in enumerate(zip(line, line[1:], strict=False)):
        candidate = _snap_point_to_segment(point, start, end, segment_index)
        if best_snap is None or candidate.distance_m < best_snap.distance_m:
            best_snap = candidate

    if best_snap is None:
        return SnapPoint(point=point, distance_m=float("inf"), segment_index=0, segment_offset=0.0)
    return best_snap


def _snap_point_to_segment(
    point: Coordinate,
    start: Coordinate,
    end: Coordinate,
    segment_index: int,
) -> SnapPoint:
    start_lon, start_lat = start
    end_lon, end_lat = end
    point_lon, point_lat = point
    delta_lon = end_lon - start_lon
    delta_lat = end_lat - start_lat
    denominator = (delta_lon * delta_lon) + (delta_lat * delta_lat)

    if denominator <= 1e-12:
        snapped_point = start
        segment_offset = 0.0
    else:
        segment_offset = max(
            0.0,
            min(
                1.0,
                (((point_lon - start_lon) * delta_lon) + ((point_lat - start_lat) * delta_lat)) / denominator,
            ),
        )
        snapped_point = (
            start_lon + (segment_offset * delta_lon),
            start_lat + (segment_offset * delta_lat),
        )

    return SnapPoint(
        point=snapped_point,
        distance_m=haversine_distance_m(point_lat, point_lon, snapped_point[1], snapped_point[0]),
        segment_index=segment_index,
        segment_offset=segment_offset,
    )


def _slice_line_between_snaps(
    line: list[Coordinate],
    start_snap: SnapPoint,
    end_snap: SnapPoint,
) -> list[Coordinate]:
    if (
        start_snap.segment_index < end_snap.segment_index
        or (
            start_snap.segment_index == end_snap.segment_index
            and start_snap.segment_offset <= end_snap.segment_offset
        )
    ):
        coordinates = [start_snap.point]
        coordinates.extend(line[start_snap.segment_index + 1 : end_snap.segment_index + 1])
        coordinates.append(end_snap.point)
        return _dedupe_coordinates(coordinates)

    coordinates = [start_snap.point]
    coordinates.extend(reversed(line[end_snap.segment_index + 1 : start_snap.segment_index + 1]))
    coordinates.append(end_snap.point)
    return _dedupe_coordinates(coordinates)


def _dedupe_coordinates(coordinates: list[Coordinate]) -> list[Coordinate]:
    deduped: list[Coordinate] = []
    for lon, lat in coordinates:
        if deduped and abs(deduped[-1][0] - lon) < 1e-12 and abs(deduped[-1][1] - lat) < 1e-12:
            continue
        deduped.append((float(lon), float(lat)))
    return deduped


def _snaps_follow_single_direction(snapped_points: list[SnapPoint]) -> bool:
    if len(snapped_points) < 2:
        return True

    positions = [_snap_position_key(snap) for snap in snapped_points]
    non_decreasing = all(left <= right for left, right in zip(positions, positions[1:], strict=False))
    non_increasing = all(left >= right for left, right in zip(positions, positions[1:], strict=False))
    return non_decreasing or non_increasing


def _snap_position_key(snap: SnapPoint) -> tuple[int, float]:
    return (snap.segment_index, snap.segment_offset)


def _coordinates_equal(left: Coordinate, right: Coordinate) -> bool:
    return abs(left[0] - right[0]) < 1e-12 and abs(left[1] - right[1]) < 1e-12


def _iter_line_strings(geometry: dict[str, Any]) -> list[list[Coordinate]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "LineString" and isinstance(coordinates, list):
        line = _normalize_line(coordinates)
        return [line] if len(line) >= 2 else []
    if geometry_type == "MultiLineString" and isinstance(coordinates, list):
        lines: list[list[Coordinate]] = []
        for candidate in coordinates:
            if not isinstance(candidate, list):
                continue
            line = _normalize_line(candidate)
            if len(line) >= 2:
                lines.append(line)
        return lines
    return []


def _normalize_line(coordinates: list[Any]) -> list[Coordinate]:
    return [
        (float(point[0]), float(point[1]))
        for point in coordinates
        if isinstance(point, list) and len(point) >= 2
    ]


def _is_valid_geojson(payload: dict[str, Any] | None) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    )
