from __future__ import annotations

from app.services.geo_utils import haversine_distance_m


RAIN_SEVERITY_RULES = {
    "light": {
        "label": "Light",
        "walking_multiplier": 1.5,
        "station_access_penalty_sec": 45,
    },
    "moderate": {
        "label": "Moderate",
        "walking_multiplier": 2.5,
        "station_access_penalty_sec": 120,
    },
    "heavy": {
        "label": "Heavy",
        "walking_multiplier": 4.0,
        "station_access_penalty_sec": 240,
    },
}


def _rain_severity_rule(zone: dict) -> dict:
    severity = str(zone.get("severity") or "moderate").lower()
    return RAIN_SEVERITY_RULES.get(severity, RAIN_SEVERITY_RULES["moderate"])


def _rain_zone_contains_point(point: tuple[float, float], zone: dict) -> bool:
    center = zone.get("center") or {}
    center_lon = center.get("lon")
    center_lat = center.get("lat")
    radius_m = zone.get("radius_m") or 0
    if center_lon is None or center_lat is None or radius_m <= 0:
        return False
    return haversine_distance_m(point[1], point[0], center_lat, center_lon) <= radius_m


def _strongest_rain_rule_for_points(
    points: list[tuple[float, float]],
    rain_zones: list[dict],
) -> tuple[str | None, dict | None]:
    strongest_severity = None
    strongest_rule = None
    strongest_multiplier = 1.0
    for zone in rain_zones:
        if not any(_rain_zone_contains_point(point, zone) for point in points):
            continue
        rule = _rain_severity_rule(zone)
        if rule["walking_multiplier"] > strongest_multiplier:
            strongest_severity = str(zone.get("severity") or "moderate").lower()
            strongest_rule = rule
            strongest_multiplier = rule["walking_multiplier"]
    return strongest_severity, strongest_rule


def rain_penalty_for_path(
    path_coordinates: list[tuple[float, float]],
    rain_zones: list[dict],
    walking_m_per_sec: float,
    *,
    access_point_coordinate: tuple[float, float] | None = None,
    include_station_access_penalty: bool = False,
) -> dict:
    if not rain_zones or walking_m_per_sec <= 0:
        return {
            "penalty_sec": 0,
            "affected_distance_m": 0.0,
            "severity": None,
            "walking_multiplier": 1.0,
            "station_access_penalty_sec": 0,
        }

    extra_time_sec = 0.0
    affected_distance_m = 0.0
    strongest_severity = None
    strongest_multiplier = 1.0

    # Overlapping rain zones do not stack. Each walking segment uses the
    # strongest zone touching that segment, then moves on to the next segment.
    for start, end in zip(path_coordinates, path_coordinates[1:], strict=False):
        midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        severity, rule = _strongest_rain_rule_for_points([start, midpoint, end], rain_zones)
        if rule is None:
            continue
        distance_m = haversine_distance_m(start[1], start[0], end[1], end[0])
        affected_distance_m += distance_m
        multiplier = rule["walking_multiplier"]
        extra_time_sec += (distance_m / walking_m_per_sec) * (multiplier - 1.0)
        if multiplier > strongest_multiplier:
            strongest_multiplier = multiplier
            strongest_severity = severity

    station_access_penalty_sec = 0
    access_rule = None
    if include_station_access_penalty and access_point_coordinate is not None:
        severity, access_rule = _strongest_rain_rule_for_points([access_point_coordinate], rain_zones)
    if access_rule is not None:
        station_access_penalty_sec = access_rule["station_access_penalty_sec"]
        if access_rule["walking_multiplier"] > strongest_multiplier:
            strongest_multiplier = access_rule["walking_multiplier"]
            strongest_severity = severity

    penalty_sec = int(round(extra_time_sec + station_access_penalty_sec))
    return {
        "penalty_sec": penalty_sec,
        "affected_distance_m": round(affected_distance_m, 1),
        "severity": strongest_severity,
        "walking_multiplier": strongest_multiplier,
        "station_access_penalty_sec": station_access_penalty_sec,
    }
