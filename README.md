# IT3160 Subway Web

Minimal Python web app for subway routing using FastAPI and a custom Dijkstra engine on an expanded station-line graph.

The frontend now uses:
- `map/taipei-vector-map-2022.svg` for real-map point picking
- `map/taipei_mrt_interactive.svg` as the semantic subway diagram surface

The interactive subway SVG is generated from the MetroMapMaker export by:

```powershell
python IT3160-SubwayWeb\scripts\normalize_metromapmaker_svg.py `
  --source IT3160-SubwayWeb\map\metromapmaker-8S4w6aZ4.svg `
  --output IT3160-SubwayWeb\map\taipei_mrt_interactive.svg `
  --mapping IT3160-SubwayWeb\app\data\taipei_mrt_interactive_map.json
```

Calibration tool:

```powershell
http://127.0.0.1:8010/calibrate
```

Use it to click the exact station positions on the image and save them back into `app/data/station_positions_taipei_vector_map_2022.json`.

Graph builder:

```powershell
http://127.0.0.1:8010/builder
```

Use it to rebuild the subway graph directly on top of the semantic SVG diagram.

## Run

### Option 1: from repo root

```powershell
python -m uvicorn --app-dir IT3160-SubwayWeb app.main:app --host 127.0.0.1 --port 8010
```

### Option 2: from project folder

```powershell
cd IT3160-SubwayWeb
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Open `http://127.0.0.1:8010`.

If port `8010` is already in use, switch to another free port, for example `8011`.

Helper scripts:

```powershell
.\IT3160-SubwayWeb\start_web.ps1 8011
```

```cmd
IT3160-SubwayWeb\start_web.bat 8011
```

## Tests

```powershell
python -m unittest IT3160-SubwayWeb.tests.test_route_engine -v
python -m unittest IT3160-SubwayWeb.tests.test_api -v
```
