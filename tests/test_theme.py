from __future__ import annotations

import unittest
from types import SimpleNamespace

from smart_drive_organizer.theme import DARK, LIGHT, REDLINE, palette_for


class ThemeTests(unittest.TestCase):
    def test_light_dark_and_redline_palettes_keep_brand_colors(self):
        for palette in (LIGHT, DARK, REDLINE):
            self.assertEqual(palette["red"], "#D71920")
            self.assertEqual(palette["white"], "#FFFFFF")
        self.assertEqual(LIGHT["black"], "#101010")
        self.assertEqual(REDLINE["bg"], "#101010")
        self.assertEqual(REDLINE["ink"], "#FFFFFF")

    def test_palette_for_selects_saved_theme(self):
        self.assertIs(palette_for(SimpleNamespace(theme_name="light")), LIGHT)
        self.assertIs(palette_for(SimpleNamespace(theme_name="dark")), DARK)
        self.assertIs(palette_for(SimpleNamespace(theme_name="redline")), REDLINE)
        self.assertIs(palette_for(SimpleNamespace(theme_name="unknown")), LIGHT)


if __name__ == "__main__":
    unittest.main()
