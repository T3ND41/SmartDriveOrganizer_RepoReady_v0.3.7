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


    def test_topic_refresh_keeps_existing_extracted_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = root / "Quarterly Review.txt"
            item.write_text("retained body text for a later search", encoding="utf-8")
            index = SearchIndex(root / "index.sqlite3")
            index.upsert_file(item, "Documents", "retained body text for a later search", "Unclassified Documents", text_indexed=True)
            index.update_topic(item, "Quarterly Reports")
            rows = index.search(query="retained body", topic="Quarterly Reports")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["body"], "retained body text for a later search")
            self.assertTrue(rows[0]["text_indexed"])
            index.close()


    def test_topic_rules_can_refresh_without_reextracting_saved_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = root / "Supplier Offer.txt"
            body = "supplier quotation for industrial valve and pressure test"
            item.write_text(body, encoding="utf-8")
            index = SearchIndex(root / "index.sqlite3")
            index.upsert_file(item, "Documents", body, "Unclassified Documents", text_indexed=True)
            topic = index.refresh_classification(
                item, "Documents",
                [{"name": "Supplier Quotations", "keywords": ["supplier quotation"], "category": "Documents"}],
            )
            rows = index.search(query="pressure test", topic="Supplier Quotations")
            index.close()
            self.assertEqual(topic, "Supplier Quotations")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["body"], body)

    def test_invalid_date_and_size_ranges_raise_clear_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            index = SearchIndex(Path(temp) / "index.sqlite3")
            with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                index.search(date_from="30/10/2026")
            with self.assertRaisesRegex(ValueError, "Maximum size"):
                index.search(min_size_mb="20", max_size_mb="10")
            with self.assertRaisesRegex(ValueError, "finite non-negative"):
                index.search(min_size_mb="-1")
            index.close()


    def test_copy_operation_adds_destination_without_dropping_source_search_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Supplier Quotation.pdf"
            destination = root / "Organized" / "Supplier Quotation.pdf"
            source.write_bytes(b"quotation")
            destination.parent.mkdir()
            destination.write_bytes(b"quotation")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(source, "Documents", "supplier quotation pressure test", "Quotations", text_indexed=True)
            index.close()
            from smart_drive_organizer.search_index import sync_file_operation
            self.assertTrue(sync_file_operation(source, destination, "Documents", "Quotations", database=database))
            index = SearchIndex(database)
            rows = index.search(query="pressure test")
            index.close()
            self.assertEqual({row["path"] for row in rows}, {str(source.resolve()), str(destination.resolve())})

    def test_move_operation_replaces_old_search_path_with_new_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Supplier Invoice.pdf"
            destination = root / "Organized" / "Supplier Invoice.pdf"
            source.write_bytes(b"invoice")
            destination.parent.mkdir()
            destination.write_bytes(b"invoice")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(source, "Documents", "supplier tax invoice", "Invoices", text_indexed=True)
            index.close()
            from smart_drive_organizer.search_index import sync_file_operation
            self.assertTrue(sync_file_operation(source, destination, "Documents", "Invoices", remove_source=True, database=database))
            index = SearchIndex(database)
            rows = index.search(query="supplier tax invoice")
            index.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], str(destination.resolve()))

    def test_build_index_refreshes_saved_topic_when_keyword_rules_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            item = source / "Unusual Name 2040.txt"
            item.write_text("special supplier quotation for this project", encoding="utf-8")
            app_data = root / "appdata"
            app_data.mkdir()
            database = root / "index.sqlite3"
            with patch.dict("os.environ", {"LOCALAPPDATA": str(app_data)}):
                build_index([source], ["Documents"], database=database)
                save_custom_rules(app_data / "SmartDriveOrganizer" / "keyword_rules.json", [
                    {"name": "Preferred Supplier Quotes", "keywords": ["supplier quotation"], "category": "Documents"}
                ])
                result = build_index([source], ["Documents"], database=database)
                index = SearchIndex(database)
                rows = index.search(query="special supplier", topic="Preferred Supplier Quotes")
                index.close()
            self.assertEqual(result["refreshed"], 0)
            self.assertEqual(len(rows), 1)



if __name__ == "__main__":
    unittest.main()
