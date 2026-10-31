from __future__ import annotations

import unittest
from pathlib import Path


class BrandAssetTests(unittest.TestCase):
    def test_official_logo_and_both_feature_icon_atlases_are_bundled(self):
        assets = Path(__file__).resolve().parents[1] / "smart_drive_organizer" / "assets"
        for name in ("brand_master.png", "feature_icons_light.png", "feature_icons_dark.png"):
            with self.subTest(asset=name):
                path = assets / name
                self.assertTrue(path.is_file(), f"Missing bundled brand asset: {name}")
                self.assertGreater(path.stat().st_size, 500, f"Brand asset appears incomplete: {name}")


if __name__ == "__main__":
    unittest.main()
