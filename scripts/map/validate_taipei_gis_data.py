from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


Coordinate = tuple[float, float]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_feature_collection(payload: dict[str, Any] | None) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    )


def iter_line_strings(geometry: dict[str, Any]) -> list[list[Coordinate]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "LineString" and isinstance(coordinates, list):
        line = normalize_line(coordinates)
        return [line] if len(line) >= 2 else []
    if geometry_type == "MultiLineString" and isinstance(coordinates, list):
        parsed: list[list[Coordinate]] = []
        for candidate in coordinates:
            if not isinstance(candidate, list):
                continue
            line = normalize_line(candidate)
            if len(line) >= 2:
                parsed.append(line)
        return parsed
    return []


def normalize_line(coordinates: list[Any]) -> list[Coordinate]:
    parsed: list[Coordinate] = []
    for point in coordinates:
        if not isinstance(point, list) or len(point) < 2:
            continue
        parsed.append((float(point[0]), float(point[1])))
    return parsed


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6_371_000.0
    rad_lat1 = math.radians(lat1)
    rad_lon1 = math.radians(lon1)
    rad_lat2 = math.radians(lat2)
    rad_lon2 = math.radians(lon2)
    delta_lat = rad_lat2 - rad_lat1
    delta_lon = rad_lon2 - rad_lon1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(rad_lat1) * math.cos(rad_lat2) * (math.sin(delta_lon / 2) ** 2)
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1 - a)))
    return earth_radius_m * c


def snap_distance_to_line_m(point: Coordinate, line: list[Coordinate]) -> float:
    best_distance_m = float("inf")
    point_lon, point_lat = point
    for start, end in zip(line, line[1:], strict=False):
        start_lon, start_lat = start
        end_lon, end_lat = end
        delta_lon = end_lon - start_lon
        delta_lat = end_lat - start_lat
        denominator = (delta_lon * delta_lon) + (delta_lat * delta_lat)
        if denominator <= 1e-12:
            snapped_lon, snapped_lat = start_lon, start_lat
        else:
            segment_offset = max(
                0.0,
                min(
                    1.0,
                    (((point_lon - start_lon) * delta_lon) + ((point_lat - start_lat) * delta_lat))
                    / denominator,
                ),
            )
            snapped_lon = start_lon + (segment_offset * delta_lon)
            snapped_lat = start_lat + (segment_offset * delta_lat)
        distance_m = haversine_distance_m(point_lat, point_lon, snapped_lat, snapped_lon)
        if distance_m < best_distance_m:
            best_distance_m = distance_m
    return best_distance_m


def distance_to_lines_m(point: Coordinate, lines: list[list[Coordinate]]) -> float:
    if not lines:
        return float("inf")
    return min(snap_distance_to_line_m(point, line) for line in lines)


def build_station_lookup(stations_geojson: dict[str, Any]) -> dict[str, Coordinate]:
    lookup: dict[str, Coordinate] = {}
    for feature in stations_geojson.get("features", []):
        station_id = feature.get("properties", {}).get("id")
        coordinates = feature.get("geometry", {}).get("coordinates")
        if (
            not station_id
            or not isinstance(coordinates, list)
            or len(coordinates) < 2
        ):
            continue
        lookup[str(station_id)] = (float(coordinates[0]), float(coordinates[1]))
    return lookup


def build_lines_by_id(lines_geojson: dict[str, Any]) -> dict[str, list[list[Coordinate]]]:
    grouped: dict[str, list[list[Coordinate]]] = {}
    for feature in lines_geojson.get("features", []):
        line_id = str(feature.get("properties", {}).get("line_id") or "")
        if not line_id:
            continue
        for line in iter_line_strings(feature.get("geometry", {}) or {}):
            grouped.setdefault(line_id, []).append(line)
    return grouped


def validate(
    network: dict[str, Any],
    stations_geojson: dict[str, Any],
    lines_geojson: dict[str, Any],
    max_endpoint_offset_m: float,
) -> dict[str, Any]:
    if not is_feature_collection(stations_geojson):
        raise ValueError("stations.geojson is not a valid FeatureCollection")
    if not is_feature_collection(lines_geojson):
        raise ValueError("lines.geojson is not a valid FeatureCollection")

    network_station_ids = {str(station["id"]) for station in network.get("stations", [])}
    network_line_ids = {str(line["id"]) for line in network.get("lines", [])}
    gis_station_lookup = build_station_lookup(stations_geojson)
    gis_line_groups = build_lines_by_id(lines_geojson)

    missing_station_ids = sorted(network_station_ids - set(gis_station_lookup))
    extra_station_ids = sorted(set(gis_station_lookup) - network_station_ids)
    missing_line_ids = sorted(network_line_ids - set(gis_line_groups))
    extra_line_ids = sorted(set(gis_line_groups) - network_line_ids)

    suspect_segments: list[dict[str, Any]] = []
    checked_segment_count = 0
    for segment in network.get("segments", []):
        line_id = str(segment.get("line_id"))
        from_station_id = str(segment.get("from_station_id"))
        to_station_id = str(segment.get("to_station_id"))
        from_coordinate = gis_station_lookup.get(from_station_id)
        to_coordinate = gis_station_lookup.get(to_station_id)
        lines = gis_line_groups.get(line_id, [])
        if not from_coordinate or not to_coordinate or not lines:
            continue

        from_offset_m = distance_to_lines_m(from_coordinate, lines)
        to_offset_m = distance_to_lines_m(to_coordinate, lines)
        checked_segment_count += 1
        if max(from_offset_m, to_offset_m) > max_endpoint_offset_m:
            suspect_segments.append(
                {
                    "line_id": line_id,
                    "from_station_id": from_station_id,
                    "to_station_id": to_station_id,
                    "from_offset_m": round(from_offset_m, 1),
                    "to_offset_m": round(to_offset_m, 1),
                }
            )

    suspect_segments.sort(
        key=lambda item: max(item["from_offset_m"], item["to_offset_m"]),
        reverse=True,
    )

    return {
        "network_station_count": len(network_station_ids),
        "gis_station_count": len(gis_station_lookup),
        "network_line_count": len(network_line_ids),
        "gis_line_id_count": len(gis_line_groups),
        "missing_station_ids": missing_station_ids,
        "extra_station_ids": extra_station_ids,
        "missing_line_ids": missing_line_ids,
        "extra_line_ids": extra_line_ids,
        "checked_segment_count": checked_segment_count,
        "suspect_segment_count": len(suspect_segments),
        "suspect_segments_top20": suspect_segments[:20],
        "thresholds": {
            "max_endpoint_offset_m": max_endpoint_offset_m,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Taipei GIS station/line consistency.")
    parser.add_argument(
        "--network",
        default="app/data/subway_network.json",
        help="Path to subway network json",
    )
    parser.add_argument(
        "--stations",
        default="app/data/gis/stations.geojson",
        help="Path to stations.geojson",
    )
    parser.add_argument(
        "--lines",
        default="app/data/gis/lines.geojson",
        help="Path to lines.geojson",
    )
    parser.add_argument(
        "--max-endpoint-offset-m",
        type=float,
        default=450.0,
        help="Warn if station endpoint is farther than this threshold to the matched line geometry.",
    )
    parser.add_argument(
        "--strict-coverage",
        action="store_true",
        help="Return non-zero when any network station/line is missing in GIS data.",
    )
    args = parser.parse_args()

    report = validate(
        network=load_json(Path(args.network)),
        stations_geojson=load_json(Path(args.stations)),
        lines_geojson=load_json(Path(args.lines)),
        max_endpoint_offset_m=float(args.max_endpoint_offset_m),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    has_critical_issues = (
        args.strict_coverage
        and bool(report["missing_station_ids"] or report["missing_line_ids"])
    )
    if has_critical_issues:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
