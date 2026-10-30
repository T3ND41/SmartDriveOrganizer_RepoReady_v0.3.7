from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from smart_drive_organizer.search_index import SearchIndex, build_index
from smart_drive_organizer.classifier import save_custom_rules


class SearchIndexTests(unittest.TestCase):
    def test_search_finds_text_inside_a_file_and_applies_filters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Documents"
            source.mkdir()
            pdf = source / "unusual_name_001.txt"
            pdf.write_text("Supplier quotation for a HDPE pipe fitting and pressure test.", encoding="utf-8")
            index = SearchIndex(root / "index.sqlite3")
            index.upsert_file(pdf, "Documents", pdf.read_text(encoding="utf-8"), "Quotations")
            result = index.search(query="pressure test", category="Documents", extension=".txt", topic="Quotations")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], pdf.name)
            self.assertIn("pressure test", result[0]["body"])
            index.close()

    def test_index_skips_unchanged_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "Monthly Statement.txt").write_text("A statement", encoding="utf-8")
            database = root / "index.sqlite3"
            first = build_index([source], ["Documents"], database=database)
            second = build_index([source], ["Documents"], database=database)
            self.assertEqual(first["refreshed"], 1)
            self.assertEqual(second["refreshed"], 0)
            self.assertEqual(second["total"], 1)

    def test_index_excludes_protected_system_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "drive"
            (root / "Users" / "Person" / "Documents").mkdir(parents=True)
            (root / "Windows" / "System32").mkdir(parents=True)
            (root / "Program Files" / "Example").mkdir(parents=True)
            (root / "Users" / "Person" / "Documents" / "LPO.txt").write_text("personal", encoding="utf-8")
            (root / "Windows" / "System32" / "LPO.txt").write_text("system", encoding="utf-8")
            (root / "Program Files" / "Example" / "LPO.txt").write_text("program", encoding="utf-8")
            result = build_index([root], ["Documents"], database=Path(temp) / "index.sqlite3")
            index = SearchIndex(Path(temp) / "index.sqlite3")
            rows = index.search(query="LPO")
            index.close()
            self.assertEqual(result["indexed"], 1)
            self.assertEqual([row["name"] for row in rows], ["LPO.txt"])
            self.assertFalse("Windows" in rows[0]["path"])

    def test_full_text_query_can_search_filename_and_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / "Project_001.txt"
            file.write_text("The confidential supplier requires a replacement valve.", encoding="utf-8")
            index = SearchIndex(root / "index.sqlite3")
            index.upsert_file(file, "Documents", "The confidential supplier requires a replacement valve.")
            self.assertEqual(len(index.search(query="replacement valve")), 1)
            self.assertEqual(len(index.search(query="Project_001")), 1)
            index.close()


    def test_index_builder_saves_classifier_topic_for_dashboard_topic_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            item = source / "Supplier Quotation 2026.txt"
            item.write_text("supplier quotation", encoding="utf-8")
            app_data = root / "appdata"
            app_data.mkdir()
            with patch.dict("os.environ", {"LOCALAPPDATA": str(app_data)}):
                save_custom_rules(app_data / "SmartDriveOrganizer" / "keyword_rules.json", [
                    {"name": "Quotations", "keywords": ["quotation"], "category": "Documents"}
                ])
                database = root / "index.sqlite3"
                build_index([source], ["Documents"], database=database)
                index = SearchIndex(database)
                rows = index.search(query="supplier", topic="Quotations")
                index.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["topic"], "Quotations")


    def test_build_index_upgrades_metadata_only_record_to_full_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            item = source / "Unusual Filename.txt"
            item.write_text("contains unique calibration phrase for full text lookup", encoding="utf-8")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(item, "Documents", "", text_indexed=False)
            self.assertTrue(index.needs_refresh(item, require_text=True))
            index.close()
            result = build_index([source], ["Documents"], database=database, extract_text=True)
            index = SearchIndex(database)
            matches = index.search(query="calibration phrase")
            index.close()
            self.assertEqual(result["refreshed"], 1)
            self.assertEqual(len(matches), 1)
            self.assertTrue(matches[0]["body"])


if __name__ == "__main__":
    unittest.main()
