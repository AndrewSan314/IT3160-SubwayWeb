import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.gis_route_geometry import build_ride_path_features


def _feature_collection(features):
    return {"type": "FeatureCollection", "features": features}


class GisRideGeometryTests(unittest.TestCase):
    def test_build_ride_path_features_follows_gis_line_shape(self):
        stations_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "properties": {"id": "station-a", "line_ids": ["c2"]},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.0, 1.0]},
                    "properties": {"id": "station-b", "line_ids": ["c2"]},
                },
            ]
        )
        lines_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]],
                    },
                    "properties": {"line_name": "Red Line", "line_color": "#ff0000"},
                }
            ]
        )

        features = build_ride_path_features(
            route_steps=[
                {
                    "kind": "ride",
                    "station_id": "station-a",
                    "line_id": "c2",
                    "next_station_id": "station-b",
                    "duration_sec": 60,
                }
            ],
            station_coords_by_id={
                "station-a": (0.0, 0.0),
                "station-b": (1.0, 1.0),
            },
            stations_geojson=stations_geojson,
            lines_geojson=lines_geojson,
        )

        self.assertEqual(len(features), 1)
        self.assertEqual(
            features[0]["geometry"]["coordinates"],
            [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        )

    def test_build_ride_path_features_merges_consecutive_steps_on_same_line(self):
        stations_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "properties": {"id": "station-a", "line_ids": ["c2"]},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.0, 1.0]},
                    "properties": {"id": "station-b", "line_ids": ["c2"]},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [2.0, 1.0]},
                    "properties": {"id": "station-c", "line_ids": ["c2"]},
                },
            ]
        )
        lines_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[0.0, 0.0], [1.0, 1.0], [2.0, 1.0]]],
                    },
                    "properties": {"line_name": "Red Line", "line_color": "#ff0000"},
                }
            ]
        )

        features = build_ride_path_features(
            route_steps=[
                {
                    "kind": "ride",
                    "station_id": "station-a",
                    "line_id": "c2",
                    "next_station_id": "station-b",
                    "duration_sec": 60,
                },
                {
                    "kind": "ride",
                    "station_id": "station-b",
                    "line_id": "c2",
                    "next_station_id": "station-c",
                    "duration_sec": 60,
                },
            ],
            station_coords_by_id={
                "station-a": (0.0, 0.0),
                "station-b": (1.0, 1.0),
                "station-c": (2.0, 1.0),
            },
            stations_geojson=stations_geojson,
            lines_geojson=lines_geojson,
        )

        self.assertEqual(len(features), 1)
        self.assertEqual(
            features[0]["geometry"]["coordinates"],
            [[0.0, 0.0], [1.0, 1.0], [2.0, 1.0]],
        )

    def test_build_ride_path_features_anchors_group_endpoints_to_station_coordinates(self):
        stations_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "properties": {"id": "station-a", "line_ids": ["c2"]},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.0, 1.0]},
                    "properties": {"id": "station-b", "line_ids": ["c2"]},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [2.0, 2.0]},
                    "properties": {"id": "station-c", "line_ids": ["c2"]},
                },
            ]
        )
        # Geometry is intentionally offset from station-a and station-c.
        lines_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[0.2, 0.0], [1.0, 1.0], [2.0, 2.2]]],
                    },
                    "properties": {"line_name": "Red Line", "line_color": "#ff0000"},
                }
            ]
        )

        features = build_ride_path_features(
            route_steps=[
                {
                    "kind": "ride",
                    "station_id": "station-a",
                    "line_id": "c2",
                    "next_station_id": "station-b",
                    "duration_sec": 60,
                },
                {
                    "kind": "ride",
                    "station_id": "station-b",
                    "line_id": "c2",
                    "next_station_id": "station-c",
                    "duration_sec": 60,
                },
            ],
            station_coords_by_id={
                "station-a": (0.0, 0.0),
                "station-b": (1.0, 1.0),
                "station-c": (2.0, 2.0),
            },
            stations_geojson=stations_geojson,
            lines_geojson=lines_geojson,
        )

        self.assertEqual(len(features), 1)
        coordinates = features[0]["geometry"]["coordinates"]
        self.assertEqual(coordinates[0], [0.0, 0.0])
        self.assertEqual(coordinates[-1], [2.0, 2.0])

    def test_build_ride_path_features_prefers_matching_line_id(self):
        stations_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "properties": {"id": "station-a", "line_ids": ["c2"]},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.0, 1.0]},
                    "properties": {"id": "station-b", "line_ids": ["c2"]},
                },
            ]
        )
        lines_geojson = _feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0]]],
                    },
                    "properties": {"line_id": "c2", "line_name": "Correct Line", "line_color": "#ff0000"},
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]],
                    },
                    "properties": {"line_id": "c9", "line_name": "Wrong Line", "line_color": "#00ff00"},
                },
            ]
        )

        features = build_ride_path_features(
            route_steps=[
                {
                    "kind": "ride",
                    "station_id": "station-a",
                    "line_id": "c2",
                    "next_station_id": "station-b",
                    "duration_sec": 60,
                }
            ],
            station_coords_by_id={
                "station-a": (0.0, 0.0),
                "station-b": (1.0, 1.0),
            },
            stations_geojson=stations_geojson,
            lines_geojson=lines_geojson,
        )

        self.assertEqual(len(features), 1)
        self.assertEqual(
            features[0]["geometry"]["coordinates"],
            [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        )


if __name__ == "__main__":
    unittest.main()
