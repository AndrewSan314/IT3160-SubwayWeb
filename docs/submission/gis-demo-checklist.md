# GIS Demo Checklist (Taipei Subway)

## 1) Data Readiness

- `app/data/gis/stations.geojson` and `app/data/gis/lines.geojson` exist.
- Run:
  - `python scripts/map/validate_taipei_gis_data.py`
- Confirm:
  - `missing_station_ids` is expected for Taipei-only subset, and documented in report
  - `missing_line_ids` = `[]`
  - `suspect_segment_count` is low and explainable.

## 2) Runtime

- Start app:
  - `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010`
- Open:
  - `http://127.0.0.1:8010`

## 3) Functional Demo Script

1. Pick start and end points directly on map (not station-only).
2. Show `Routing Strategy = Nearest Station Only`, run route.
3. Switch to `Routing Strategy = Best Route`, run same points again.
4. Compare `Total Journey` and `Line Sequence`.
5. Zoom in to verify station node labels appear.
6. Hide/show sidebar and show map resizing across full width.

## 4) Visual Quality Checks

- Highlighted route is continuous and follows rail geometry.
- Start/end markers are visible.
- Walk access/egress paths connect marker to snapped station.
- Sidebar never overlays map unexpectedly in desktop mode.

## 5) Performance Checks

- Pan/zoom response is smooth on standard laptop browser.
- Route recalculation latency is acceptable (< 1-2 seconds for normal queries).
- No browser console errors during demo.
