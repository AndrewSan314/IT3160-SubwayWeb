from __future__ import annotations

import argparse
import json
from pathlib import Path

import osmnx as ox
from shapely.geometry import mapping


DEFAULT_BBOX = (121.4374192, 24.9090092, 121.6987109, 25.2619815)
WATER_TAGS = {
    "natural": ["water"],
    "landuse": ["reservoir", "basin"],
    "waterway": ["riverbank"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download OSM water polygons used to keep route endpoints on land."
    )
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("LEFT", "BOTTOM", "RIGHT", "TOP"),
        default=DEFAULT_BBOX,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("app/data/gis/water_areas.geojson"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    output_path = args.output
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(repo_root / "cache" / "osmnx")
    ox.settings.requests_timeout = 180

    features = ox.features_from_bbox(tuple(args.bbox), tags=WATER_TAGS)
    water_features = []
    for geometry in features.geometry:
        if geometry is None or geometry.is_empty:
            continue
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        water_features.append(
            {
                "type": "Feature",
                "geometry": mapping(geometry),
                "properties": {},
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": water_features,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(water_features)} water polygons to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
