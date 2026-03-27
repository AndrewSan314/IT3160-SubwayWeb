import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.gis_loader import get_cached_walk_graph


def _write_geojson(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class GisLoaderTests(unittest.TestCase):
    def test_get_cached_walk_graph_reuses_graph_for_unchanged_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            geojson_dir = Path(temp_dir)
            _write_geojson(
                geojson_dir / "walk_network.geojson",
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[121.5, 25.05], [121.5005, 25.0505]],
                            },
                            "properties": {},
                        }
                    ],
                },
            )

            with patch("app.services.gis_loader.build_walk_graph", wraps=get_cached_walk_graph.__globals__["build_walk_graph"]) as mocked_build:
                first = get_cached_walk_graph(geojson_dir)
                second = get_cached_walk_graph(geojson_dir)

            self.assertIs(first, second)
            self.assertEqual(mocked_build.call_count, 1)


if __name__ == "__main__":
    unittest.main()
