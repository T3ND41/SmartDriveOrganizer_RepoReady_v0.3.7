import unittest
from pathlib import Path

from smart_drive_organizer.drives import DriveInfo, format_bytes


class DriveDiscoveryModelTests(unittest.TestCase):
    def test_local_fixed_and_removable_drives_are_preselected(self):
        self.assertTrue(DriveInfo(Path("C:/"), "Fixed").default_selected)
        self.assertTrue(DriveInfo(Path("E:/"), "Removable").default_selected)
        self.assertTrue(DriveInfo(Path("/"), "Mounted volume").default_selected)

    def test_network_drives_are_visible_but_not_preselected(self):
        self.assertFalse(DriveInfo(Path("Z:/"), "Network").default_selected)

    def test_drive_display_includes_label_and_capacity(self):
        drive = DriveInfo(Path("D:/"), "Fixed", "DATA", 1024 ** 3, 512 * 1024 ** 2)
        self.assertIn("DATA", drive.display_name)
        self.assertIn("512.0 MB free", drive.display_name)

    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")


if __name__ == "__main__":
    unittest.main()
