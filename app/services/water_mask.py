from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from shapely.geometry import Point
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.prepared import prep


@dataclass(frozen=True)
class WaterMask:
    geometry: Any
    _prepared_geometry: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_prepared_geometry", prep(self.geometry))

    def covers(self, lon: float, lat: float) -> bool:
        return bool(self._prepared_geometry.covers(Point(float(lon), float(lat))))


def build_water_mask(payload: dict[str, Any] | None) -> WaterMask | None:
    if not isinstance(payload, dict):
        return None

    geometries = []
    if payload.get("type") == "FeatureCollection":
        items = [
            feature.get("geometry")
            for feature in payload.get("features", [])
            if isinstance(feature, dict)
        ]
    elif payload.get("type") == "Feature":
        items = [payload.get("geometry")]
    else:
        items = [payload]

    for item in items:
        if not isinstance(item, dict):
            continue
        geometry = shape(item)
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        geometries.append(geometry)

    if not geometries:
        return None
    return WaterMask(unary_union(geometries))


def load_water_mask(path: str | Path) -> WaterMask | None:
    water_path = Path(path)
    if not water_path.exists():
        return None
    stat = water_path.stat()
    return _load_water_mask_cached(
        str(water_path),
        stat.st_size,
        stat.st_mtime_ns,
    )


@lru_cache(maxsize=4)
def _load_water_mask_cached(
    path_str: str,
    file_size: int,
    modified_time_ns: int,
) -> WaterMask | None:
    del file_size, modified_time_ns
    try:
        payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return build_water_mask(payload)
