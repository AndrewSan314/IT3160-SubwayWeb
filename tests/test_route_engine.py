import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.route_engine import RouteEngine
from app.services.subway_loader import load_network_from_dict


SAMPLE_NETWORK = {
    "stations": [
        {"id": "R1", "name": "Riverside", "x": 140, "y": 140},
        {"id": "R2", "name": "Museum", "x": 240, "y": 140},
        {"id": "X1", "name": "Central Hub", "x": 340, "y": 140},
        {"id": "X2", "name": "Civic Center", "x": 440, "y": 140},
        {"id": "R5", "name": "South Gate", "x": 540, "y": 140},
        {"id": "B1", "name": "West End", "x": 340, "y": 260},
        {"id": "B2", "name": "Market", "x": 340, "y": 200},
        {"id": "B4", "name": "Tech Park", "x": 340, "y": 80},
        {"id": "B5", "name": "East Lake", "x": 340, "y": 20},
        {"id": "G1", "name": "North Garden", "x": 440, "y": 260},
        {"id": "G2", "name": "Library", "x": 440, "y": 200},
        {"id": "G4", "name": "University", "x": 440, "y": 80},
        {"id": "G5", "name": "South Harbor", "x": 440, "y": 20},
    ],
    "lines": [
        {"id": "red", "name": "Red Line", "color": "#d94f4f"},
        {"id": "blue", "name": "Blue Line", "color": "#3d6df2"},
        {"id": "green", "name": "Green Line", "color": "#1f9d67"},
    ],
    "station_lines": [
        {"station_id": "R1", "line_id": "red", "seq": 1},
        {"station_id": "R2", "line_id": "red", "seq": 2},
        {"station_id": "X1", "line_id": "red", "seq": 3},
        {"station_id": "X2", "line_id": "red", "seq": 4},
        {"station_id": "R5", "line_id": "red", "seq": 5},
        {"station_id": "B1", "line_id": "blue", "seq": 1},
        {"station_id": "B2", "line_id": "blue", "seq": 2},
        {"station_id": "X1", "line_id": "blue", "seq": 3},
        {"station_id": "B4", "line_id": "blue", "seq": 4},
        {"station_id": "B5", "line_id": "blue", "seq": 5},
        {"station_id": "G1", "line_id": "green", "seq": 1},
        {"station_id": "G2", "line_id": "green", "seq": 2},
        {"station_id": "X2", "line_id": "green", "seq": 3},
        {"station_id": "G4", "line_id": "green", "seq": 4},
        {"station_id": "G5", "line_id": "green", "seq": 5},
    ],
    "segments": [
        {"line_id": "red", "from_station_id": "R1", "to_station_id": "R2", "travel_sec": 90},
        {"line_id": "red", "from_station_id": "R2", "to_station_id": "X1", "travel_sec": 110},
        {"line_id": "red", "from_station_id": "X1", "to_station_id": "X2", "travel_sec": 100},
        {"line_id": "red", "from_station_id": "X2", "to_station_id": "R5", "travel_sec": 120},
        {"line_id": "blue", "from_station_id": "B1", "to_station_id": "B2", "travel_sec": 80},
        {"line_id": "blue", "from_station_id": "B2", "to_station_id": "X1", "travel_sec": 90},
        {"line_id": "blue", "from_station_id": "X1", "to_station_id": "B4", "travel_sec": 95},
        {"line_id": "blue", "from_station_id": "B4", "to_station_id": "B5", "travel_sec": 85},
        {"line_id": "green", "from_station_id": "G1", "to_station_id": "G2", "travel_sec": 70},
        {"line_id": "green", "from_station_id": "G2", "to_station_id": "X2", "travel_sec": 85},
        {"line_id": "green", "from_station_id": "X2", "to_station_id": "G4", "travel_sec": 90},
        {"line_id": "green", "from_station_id": "G4", "to_station_id": "G5", "travel_sec": 100},
    ],
    "transfers": [
        {"station_id": "X1", "from_line_id": "red", "to_line_id": "blue", "transfer_sec": 180},
        {"station_id": "X1", "from_line_id": "blue", "to_line_id": "red", "transfer_sec": 180},
        {"station_id": "X2", "from_line_id": "red", "to_line_id": "green", "transfer_sec": 150},
        {"station_id": "X2", "from_line_id": "green", "to_line_id": "red", "transfer_sec": 150},
    ],
}


def make_engine() -> RouteEngine:
    network = load_network_from_dict(SAMPLE_NETWORK)
    return RouteEngine(network)


class RouteEngineTests(unittest.TestCase):
    def test_same_line_route_has_no_transfer(self):
        engine = make_engine()

        result = engine.find_route("R1", "R5")

        self.assertEqual(result.total_time_sec, 420)
        self.assertEqual(result.transfer_count, 0)
        self.assertEqual(result.station_ids, ["R1", "R2", "X1", "X2", "R5"])

    def test_route_with_transfer_chooses_fastest_transfer_path(self):
        engine = make_engine()

        result = engine.find_route("B1", "G5")

        self.assertEqual(result.total_time_sec, 790)
        self.assertEqual(result.transfer_count, 2)
        self.assertEqual(result.station_ids, ["B1", "B2", "X1", "X2", "G4", "G5"])
        self.assertEqual(result.line_sequence, ["blue", "red", "green"])

    def test_start_equals_end_returns_single_station_route(self):
        engine = make_engine()

        result = engine.find_route("X1", "X1")

        self.assertEqual(result.total_time_sec, 0)
        self.assertEqual(result.transfer_count, 0)
        self.assertEqual(result.station_ids, ["X1"])

    def test_point_route_snaps_start_and_end_to_nearest_station(self):
        engine = make_engine()

        result = engine.find_best_route_for_points(
            start_x=336,
            start_y=252,
            end_x=444,
            end_y=28,
            walking_seconds_per_pixel=1.0,
        )

        self.assertEqual(result["selected_start_station"]["id"], "B1")
        self.assertEqual(result["selected_end_station"]["id"], "G5")
        self.assertEqual(result["route"]["station_ids"], ["B1", "B2", "X1", "X2", "G4", "G5"])
        self.assertGreater(result["total_journey_time_sec"], result["route"]["total_time_sec"])

    def test_point_route_can_prefer_detected_line_hint(self):
        engine = make_engine()

        result = engine.find_best_route_for_points(
            start_x=340,
            start_y=208,
            end_x=540,
            end_y=140,
            walking_seconds_per_pixel=1.0,
            start_preferred_line_ids=["red"],
            end_preferred_line_ids=["red"],
        )

        self.assertIn("red", result["selected_start_station"]["line_ids"])
        self.assertNotEqual(result["selected_start_station"]["id"], "B2")
        self.assertEqual(result["selected_end_station"]["id"], "R5")
        self.assertEqual(result["route"]["line_sequence"], ["red"])


if __name__ == "__main__":
    unittest.main()
