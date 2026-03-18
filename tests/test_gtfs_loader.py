import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.subway_loader import NetworkBuildOptions
from app.services.subway_loader import load_network_from_dict
from app.services.subway_gtfs_loader import load_network_from_gtfs
from app.services.route_engine import RouteEngine


def write_csv(path: Path, content: str) -> None:
    path.write_text(content.strip() + "\n", encoding="utf-8")


class GtfsLoaderTests(unittest.TestCase):
    def test_gtfs_loader_normalizes_child_stops_to_station_nodes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            gtfs_dir = Path(tmp_dir)

            write_csv(
                gtfs_dir / "stops.txt",
                """
stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station
STA,Station A,10.0000,20.0000,1,
STA_N,Station A Northbound,10.0001,20.0001,0,STA
STB,Station B,10.1000,20.1000,1,
STB_N,Station B Northbound,10.1001,20.1001,0,STB
STC,Station C,10.2000,20.2000,1,
STC_N,Station C Northbound,10.2001,20.2001,0,STC
                """,
            )
            write_csv(
                gtfs_dir / "routes.txt",
                """
route_id,route_short_name,route_long_name,route_color
red,Red,Red Line,D94F4F
                """,
            )
            write_csv(
                gtfs_dir / "trips.txt",
                """
route_id,service_id,trip_id
red,WKD,red_trip_1
                """,
            )
            write_csv(
                gtfs_dir / "stop_times.txt",
                """
trip_id,arrival_time,departure_time,stop_id,stop_sequence
red_trip_1,08:00:00,08:00:30,STA_N,1
red_trip_1,08:02:00,08:02:30,STB_N,2
red_trip_1,08:04:00,08:04:30,STC_N,3
                """,
            )

            network = load_network_from_gtfs(gtfs_dir)

        self.assertEqual(sorted(network.stations), ["STA", "STB", "STC"])
        self.assertIn("STA_N", network.stops)
        self.assertEqual(network.stops["STA_N"].station_id, "STA")
        self.assertEqual(
            [(segment.from_station_id, segment.to_station_id) for segment in network.segments],
            [("STA", "STB"), ("STB", "STC")],
        )
        self.assertEqual(network.lines["red"].name, "Red Line")

    def test_generated_walk_transfers_create_walk_steps_between_nearby_stations(self):
        raw = {
            "stations": [
                {"id": "A", "name": "Alpha", "x": 100, "y": 100},
                {"id": "B", "name": "Beta", "x": 118, "y": 100},
                {"id": "C", "name": "Gamma", "x": 220, "y": 100},
            ],
            "lines": [
                {"id": "red", "name": "Red Line", "color": "#d94f4f"},
                {"id": "blue", "name": "Blue Line", "color": "#3d6df2"},
            ],
            "station_lines": [
                {"station_id": "A", "line_id": "red", "seq": 1},
                {"station_id": "B", "line_id": "blue", "seq": 1},
                {"station_id": "C", "line_id": "blue", "seq": 2},
            ],
            "segments": [
                {"line_id": "blue", "from_station_id": "B", "to_station_id": "C", "travel_sec": 90},
            ],
            "transfers": [],
        }

        network = load_network_from_dict(
            raw,
            options=NetworkBuildOptions(
                auto_walk_transfer_radius=25.0,
                auto_walk_seconds_per_unit=2.0,
            ),
        )
        engine = RouteEngine(network)

        result = engine.find_route("A", "C")

        self.assertEqual(result.station_ids, ["A", "B", "C"])
        self.assertEqual([step.kind for step in result.steps], ["walk", "ride"])
        self.assertEqual(result.walking_time_sec, 36)
        self.assertEqual(result.total_time_sec, 126)


if __name__ == "__main__":
    unittest.main()
