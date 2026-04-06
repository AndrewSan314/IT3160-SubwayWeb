import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.astar_route_engine import AStarRouteEngine
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


def make_network():
    return load_network_from_dict(SAMPLE_NETWORK)


class AStarRouteEngineTests(unittest.TestCase):
    def test_astar_matches_dijkstra_simple_route(self):
        network = make_network()
        dijkstra_engine = RouteEngine(network)
        astar_engine = AStarRouteEngine(network)

        dijkstra_result = dijkstra_engine.find_route("R1", "R5")
        astar_result = astar_engine.find_route("R1", "R5")

        self.assertEqual(astar_result.station_ids, dijkstra_result.station_ids)
        self.assertEqual(astar_result.total_time_sec, dijkstra_result.total_time_sec)
        self.assertEqual(astar_result.line_sequence, dijkstra_result.line_sequence)

    def test_astar_matches_dijkstra_transfer_route(self):
        network = make_network()
        dijkstra_engine = RouteEngine(network)
        astar_engine = AStarRouteEngine(network)

        dijkstra_result = dijkstra_engine.find_route("B1", "G5")
        astar_result = astar_engine.find_route("B1", "G5")

        self.assertEqual(astar_result.station_ids, dijkstra_result.station_ids)
        self.assertEqual(astar_result.total_time_sec, dijkstra_result.total_time_sec)
        self.assertEqual(astar_result.transfer_count, dijkstra_result.transfer_count)

    def test_astar_matches_dijkstra_route_through_waypoints(self):
        network = make_network()
        dijkstra_engine = RouteEngine(network)
        astar_engine = AStarRouteEngine(network)

        dijkstra_result = dijkstra_engine.find_route_through_stations(["B1", "R5", "G5"])
        astar_result = astar_engine.find_route_through_stations(["B1", "R5", "G5"])

        self.assertEqual(astar_result.station_ids, dijkstra_result.station_ids)
        self.assertEqual(astar_result.total_time_sec, dijkstra_result.total_time_sec)


if __name__ == "__main__":
    unittest.main()
