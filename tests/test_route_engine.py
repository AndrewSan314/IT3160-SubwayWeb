import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.route_engine import RouteEngine
from app.services.runtime import get_network
from app.services.subway_loader import NetworkBuildOptions
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
    def test_orange_line_branches_connect_through_daqiaotou(self):
        engine = RouteEngine(get_network())

        result = engine.find_route("sanchong-elementary-school", "taipei-bridge")

        self.assertEqual(
            result.station_ids,
            ["sanchong-elementary-school", "daqiaotou", "taipei-bridge"],
        )

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

    def test_candidate_route_requires_real_trip_instead_of_looping_back_to_start(self):
        engine = make_engine()

        with self.assertRaisesRegex(ValueError, "No route found"):
            engine.find_route_between_candidates(
                start_options=[("start", "R1", (0, 0, 0, 0))],
                end_options=[("end", "R1", (0, 0, 0, 0))],
                require_ride=True,
            )

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

    def test_route_through_waypoints_enforces_stopover_station(self):
        engine = make_engine()

        result = engine.find_route_through_stations(["B1", "R5", "G5"])

        self.assertEqual(result.station_ids[0], "B1")
        self.assertEqual(result.station_ids[-1], "G5")
        self.assertIn("R5", result.station_ids)
        self.assertGreater(result.station_ids.index("R5"), 0)

    def test_route_through_via_charges_transfer_at_via_station(self):
        engine = make_engine()

        result = engine.find_route_through_stations(["R1", "X1", "B5"])

        self.assertEqual(result.station_ids, ["R1", "R2", "X1", "B4", "B5"])
        self.assertEqual(result.line_sequence, ["red", "blue"])
        self.assertEqual(result.transfer_count, 1)
        self.assertEqual(result.total_time_sec, 560)

    def test_point_route_respects_via_station_ids(self):
        engine = make_engine()

        result = engine.find_best_route_for_points(
            start_x=336,
            start_y=252,
            end_x=444,
            end_y=28,
            walking_seconds_per_pixel=1.0,
            via_station_ids=["R5"],
        )

        self.assertEqual(result["selected_start_station"]["id"], "B1")
        self.assertEqual(result["selected_end_station"]["id"], "G5")
        self.assertIn("R5", result["route"]["station_ids"])
        self.assertEqual([station["id"] for station in result["via_stations"]], ["R5"])

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

    def test_rain_penalty_applies_to_generated_walk_transfer(self):
        raw = {
            "stations": [
                {"id": "A", "name": "Alpha", "x": 121.5000, "y": 25.0000},
                {"id": "B", "name": "Beta", "x": 121.5002, "y": 25.0000},
            ],
            "lines": [
                {"id": "red", "name": "Red Line", "color": "#d94f4f"},
                {"id": "blue", "name": "Blue Line", "color": "#3d6df2"},
            ],
            "station_lines": [
                {"station_id": "A", "line_id": "red", "seq": 1},
                {"station_id": "B", "line_id": "blue", "seq": 1},
            ],
            "segments": [],
            "transfers": [],
        }
        network = load_network_from_dict(
            raw,
            options=NetworkBuildOptions(auto_walk_transfer_radius=100.0),
        )
        engine = RouteEngine(network)
        rain_zones = [
            {
                "id": "rain-1",
                "center": {"lon": 121.5001, "lat": 25.0},
                "radius_m": 100,
                "severity": "heavy",
            }
        ]

        dry_result = engine.find_route("A", "B")
        rainy_result = engine.find_route("A", "B", rain_zones=rain_zones)

        self.assertGreater(rainy_result.total_time_sec, dry_result.total_time_sec)
        self.assertGreater(rainy_result.walking_time_sec, dry_result.walking_time_sec)
        self.assertGreater(rainy_result.rain_penalty_sec, 0)
        self.assertEqual(rainy_result.steps[0].rain_penalty_sec, rainy_result.rain_penalty_sec)
        self.assertEqual(rainy_result.to_dict()["rain_penalty_sec"], rainy_result.rain_penalty_sec)

    def test_rain_penalty_does_not_apply_to_same_station_transfer(self):
        raw = {
            "stations": [
                {"id": "A", "name": "Alpha", "x": 121.5000, "y": 25.0000},
                {"id": "X", "name": "Exchange", "x": 121.5100, "y": 25.0000},
                {"id": "B", "name": "Beta", "x": 121.5200, "y": 25.0000},
            ],
            "lines": [
                {"id": "red", "name": "Red Line", "color": "#d94f4f"},
                {"id": "blue", "name": "Blue Line", "color": "#3d6df2"},
            ],
            "station_lines": [
                {"station_id": "A", "line_id": "red", "seq": 1},
                {"station_id": "X", "line_id": "red", "seq": 2},
                {"station_id": "X", "line_id": "blue", "seq": 1},
                {"station_id": "B", "line_id": "blue", "seq": 2},
            ],
            "segments": [
                {"line_id": "red", "from_station_id": "A", "to_station_id": "X", "travel_sec": 90},
                {"line_id": "blue", "from_station_id": "X", "to_station_id": "B", "travel_sec": 90},
            ],
            "transfers": [
                {"station_id": "X", "from_line_id": "red", "to_line_id": "blue", "transfer_sec": 90},
            ],
        }
        network = load_network_from_dict(
            raw,
            options=NetworkBuildOptions(auto_walk_transfer_radius=100.0),
        )
        engine = RouteEngine(network)
        rain_zones = [
            {
                "id": "rain-1",
                "center": {"lon": 121.51, "lat": 25.0},
                "radius_m": 100,
                "severity": "heavy",
            }
        ]

        dry_result = engine.find_route("A", "B")
        rainy_result = engine.find_route("A", "B", rain_zones=rain_zones)

        self.assertEqual(rainy_result.total_time_sec, dry_result.total_time_sec)
        self.assertEqual(rainy_result.rain_penalty_sec, 0)

    def test_grid_cell_uses_floor_for_negative_coordinates(self):
        self.assertEqual(RouteEngine._grid_cell((-0.1, -1.1), 1.0), (-1, -2))


if __name__ == "__main__":
    unittest.main()
