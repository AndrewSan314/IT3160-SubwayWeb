from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.services.route_engine import RouteEngine
from app.services.subway_loader import NetworkBuildOptions
from app.services.subway_loader import load_network_from_file
from app.services.subway_loader import load_station_positions_file


def get_network():
    settings = get_settings()
    source_path = settings.data_file
    positions_path = settings.station_positions_file if settings.station_positions_file.exists() else None
    signature = _build_signature(source_path, positions_path)

    return _load_network_cached(
        str(source_path),
        str(positions_path) if positions_path else "",
        settings.default_transfer_sec,
        settings.auto_walk_transfer_radius,
        settings.auto_walk_seconds_per_unit,
        signature,
    )


@lru_cache(maxsize=4)
def _load_network_cached(
    source_path: str,
    positions_path: str,
    default_transfer_sec: int,
    auto_walk_transfer_radius: float,
    auto_walk_seconds_per_unit: float,
    signature: str,
):
    del signature
    options = NetworkBuildOptions(
        station_positions=load_station_positions_file(positions_path or None),
        default_transfer_sec=default_transfer_sec,
        auto_walk_transfer_radius=auto_walk_transfer_radius,
        auto_walk_seconds_per_unit=auto_walk_seconds_per_unit,
    )
    return load_network_from_file(source_path, options=options)


@lru_cache(maxsize=1)
def get_route_engine() -> RouteEngine:
    return RouteEngine(get_network())


def refresh_runtime_caches() -> None:
    _load_network_cached.cache_clear()
    get_route_engine.cache_clear()


def _build_signature(source_path: Path, positions_path: Path | None) -> str:
    parts = [_path_signature(source_path)]
    if positions_path is not None:
        parts.append(_path_signature(positions_path))

    return "|".join(parts)


def _path_signature(path: Path) -> str:
    if not path.exists():
        return f"{path}:missing"
    stat = path.stat()
    return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
