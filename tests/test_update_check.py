from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from smart_drive_organizer.update_check import check_latest_release


class UpdateCheckTests(unittest.TestCase):
    @patch("smart_drive_organizer.update_check.urlopen")
    def test_reports_newer_official_release(self, urlopen):
        payload = {
            "tag_name": "v0.8.0",
            "name": "Smart Drive Organizer 0.8.0",
            "html_url": "https://github.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/releases/tag/v0.8.0",
            "published_at": "2026-10-31T08:00:00Z",
        }
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(payload).encode("utf-8")

        result = check_latest_release("0.7.0")

        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "0.8.0")
        self.assertEqual(result["current_version"], "0.7.0")
        self.assertEqual(result["release_url"], payload["html_url"])

    @patch("smart_drive_organizer.update_check.urlopen")
    def test_reports_current_version_as_up_to_date(self, urlopen):
        payload = {
            "tag_name": "v0.7.0",
            "html_url": "https://github.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/releases/tag/v0.7.0",
        }
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()

        result = check_latest_release("0.7.0")

        self.assertFalse(result["update_available"])

    @patch("smart_drive_organizer.update_check.urlopen")
    def test_rejects_untrusted_release_url(self, urlopen):
        payload = {
            "tag_name": "v0.8.0",
            "html_url": "https://example.com/download",
        }
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()

        with self.assertRaises(ValueError):
            check_latest_release("0.7.0")

    @patch("smart_drive_organizer.update_check.urlopen")
    def test_rejects_invalid_release_tag(self, urlopen):
        payload = {
            "tag_name": "latest",
            "html_url": "https://github.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/releases/tag/latest",
        }
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()

        with self.assertRaises(ValueError):
            check_latest_release("0.7.0")


if __name__ == "__main__":
    unittest.main()
