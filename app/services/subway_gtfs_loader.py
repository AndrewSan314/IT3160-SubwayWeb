from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from app.domain.models import Line
from app.domain.models import Segment
from app.domain.models import Station
from app.domain.models import StationLine
from app.domain.models import Stop
from app.domain.models import SubwayNetwork
from app.domain.models import WalkTransfer
from app.services.subway_loader import NetworkBuildOptions
from app.services.subway_loader import build_station_transfers
from app.services.subway_loader import build_walk_transfers
from app.services.subway_loader import dedupe_walk_transfers


def load_network_from_gtfs(
    gtfs_dir: str | Path,
    options: NetworkBuildOptions | None = None,
) -> SubwayNetwork:
    options = options or NetworkBuildOptions()
    base_path = Path(gtfs_dir)

    stop_rows = list(_read_csv_rows(base_path / "stops.txt"))
    route_rows = list(_read_csv_rows(base_path / "routes.txt"))
    trip_rows = list(_read_csv_rows(base_path / "trips.txt"))
    stop_time_rows = list(_read_csv_rows(base_path / "stop_times.txt"))
    transfer_rows = list(_read_csv_rows(base_path / "transfers.txt")) if (base_path / "transfers.txt").exists() else []

    stop_definitions = {row["stop_id"]: row for row in stop_rows}
    stations = _build_stations(stop_rows, options.station_positions)
    stops = _build_stops(stop_rows, stop_definitions)
    lines = _build_lines(route_rows)
    trip_to_line = {
        row["trip_id"]: row["route_id"]
        for row in trip_rows
        if row["route_id"] in lines
    }

    grouped_stop_times: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in stop_time_rows:
        if row["trip_id"] not in trip_to_line or row["stop_id"] not in stops:
            continue
        grouped_stop_times[row["trip_id"]].append(row)

    segment_durations: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    line_station_order: dict[str, list[str]] = defaultdict(list)

    for trip_id, rows in grouped_stop_times.items():
        ordered_rows = sorted(rows, key=lambda item: int(item["stop_sequence"]))
        normalized_stops = _normalize_trip_stops(ordered_rows, stops)
        if len(normalized_stops) < 2:
            continue

        line_id = trip_to_line[trip_id]
        _merge_station_order(line_station_order[line_id], normalized_stops)

        for current, next_stop in zip(normalized_stops, normalized_stops[1:], strict=False):
            duration_sec = max(1, next_stop["arrival_sec"] - current["departure_sec"])
            segment_durations[(line_id, current["station_id"], next_stop["station_id"])].append(duration_sec)

    station_lines = [
        StationLine(station_id=station_id, line_id=line_id, seq=index)
        for line_id, station_ids in sorted(line_station_order.items())
        for index, station_id in enumerate(station_ids, start=1)
    ]
    station_to_lines: dict[str, set[str]] = defaultdict(set)
    for station_line in station_lines:
        station_to_lines[station_line.station_id].add(station_line.line_id)

    segments = [
        Segment(
            line_id=line_id,
            from_station_id=from_station_id,
            to_station_id=to_station_id,
            travel_sec=int(round(sum(durations) / len(durations))),
        )
        for (line_id, from_station_id, to_station_id), durations in sorted(segment_durations.items())
    ]

    transfers = build_station_transfers(
        station_to_lines,
        explicit_transfers=[],
        default_transfer_sec=options.default_transfer_sec,
    )
    walk_transfers = _build_gtfs_walk_transfers(transfer_rows, stops)
    walk_transfers = build_walk_transfers(
        stations,
        station_to_lines,
        walk_transfers,
        options.auto_walk_transfer_radius,
        options.auto_walk_seconds_per_unit,
    )

    return SubwayNetwork(
        stations=stations,
        lines=lines,
        station_lines=station_lines,
        segments=segments,
        transfers=transfers,
        stops=stops,
        walk_transfers=walk_transfers,
        station_to_lines=dict(station_to_lines),
        metadata={"source_kind": "gtfs", "gtfs_dir": str(base_path)},
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _build_stations(
    stop_rows: list[dict[str, str]],
    station_positions: dict[str, tuple[float, float]],
) -> dict[str, Station]:
    stations: dict[str, Station] = {}

    for row in stop_rows:
        station_id = row.get("parent_station") or row["stop_id"]
        if station_id in stations:
            continue

        x, y = station_positions.get(
            station_id,
            (float(row["stop_lon"]), float(row["stop_lat"])),
        )
        stations[station_id] = Station(
            id=station_id,
            name=row["stop_name"],
            x=x,
            y=y,
        )

    return stations


def _build_stops(
    stop_rows: list[dict[str, str]],
    stop_definitions: dict[str, dict[str, str]],
) -> dict[str, Stop]:
    stops: dict[str, Stop] = {}

    for row in stop_rows:
        station_id = row.get("parent_station") or row["stop_id"]
        parent_row = stop_definitions.get(station_id, row)
        stops[row["stop_id"]] = Stop(
            id=row["stop_id"],
            station_id=station_id,
            name=row["stop_name"],
            latitude=float(parent_row["stop_lat"]),
            longitude=float(parent_row["stop_lon"]),
        )

    return stops


def _build_lines(route_rows: list[dict[str, str]]) -> dict[str, Line]:
    lines: dict[str, Line] = {}

    for row in route_rows:
        color = row.get("route_color", "").strip()
        lines[row["route_id"]] = Line(
            id=row["route_id"],
            name=row.get("route_long_name") or row.get("route_short_name") or row["route_id"],
            color=f"#{color.lower()}" if color else "#6aa7ff",
        )

    return lines


def _normalize_trip_stops(
    ordered_rows: list[dict[str, str]],
    stops: dict[str, Stop],
) -> list[dict[str, int | str]]:
    normalized: list[dict[str, int | str]] = []

    for row in ordered_rows:
        stop = stops[row["stop_id"]]
        entry = {
            "station_id": stop.station_id,
            "arrival_sec": _parse_gtfs_time(row["arrival_time"]),
            "departure_sec": _parse_gtfs_time(row["departure_time"]),
        }
        if normalized and normalized[-1]["station_id"] == entry["station_id"]:
            normalized[-1] = entry
            continue
        normalized.append(entry)

    return normalized


def _merge_station_order(line_station_order: list[str], normalized_stops: list[dict[str, int | str]]) -> None:
    for stop in normalized_stops:
        station_id = str(stop["station_id"])
        if station_id not in line_station_order:
            line_station_order.append(station_id)


def _build_gtfs_walk_transfers(
    transfer_rows: list[dict[str, str]],
    stops: dict[str, Stop],
) -> list[WalkTransfer]:
    walk_transfers: list[WalkTransfer] = []

    for row in transfer_rows:
        from_stop = stops.get(row.get("from_stop_id", ""))
        to_stop = stops.get(row.get("to_stop_id", ""))
        if from_stop is None or to_stop is None:
            continue
        if from_stop.station_id == to_stop.station_id:
            continue

        min_transfer_time = row.get("min_transfer_time", "").strip()
        duration_sec = int(min_transfer_time) if min_transfer_time else 180
        walk_transfers.append(
            WalkTransfer(
                from_station_id=from_stop.station_id,
                to_station_id=to_stop.station_id,
                duration_sec=duration_sec,
            )
        )

    return dedupe_walk_transfers(walk_transfers)


def _parse_gtfs_time(raw_time: str) -> int:
    hours, minutes, seconds = (int(part) for part in raw_time.split(":"))
    return hours * 3600 + minutes * 60 + seconds
