import sys
import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeDependencyTests(unittest.TestCase):
    def test_pyproject_declares_water_mask_runtime_dependency(self):
        payload = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        dependencies = payload["project"]["dependencies"]

        self.assertTrue(
            any(item.lower().startswith("shapely") for item in dependencies),
            "app.services.water_mask imports shapely at runtime",
        )


if __name__ == "__main__":
    unittest.main()
