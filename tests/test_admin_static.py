import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AdminStaticTests(unittest.TestCase):
    def test_admin_map_station_labels_are_visible_at_overview_zoom(self):
        script = (PROJECT_ROOT / "app/static/admin/admin.js").read_text(encoding="utf-8")

        self.assertIn("id: 'admin-stations-label'", script)
        self.assertIn("minzoom: 10.8", script)
        self.assertIn("'text-field': ['get', 'name']", script)

    def test_admin_html_cache_busts_station_label_script(self):
        html = (PROJECT_ROOT / "app/static/admin/index.html").read_text(encoding="utf-8")

        self.assertIn("/static/admin/admin.js?v=20260602-station-labels-2", html)


if __name__ == "__main__":
    unittest.main()
