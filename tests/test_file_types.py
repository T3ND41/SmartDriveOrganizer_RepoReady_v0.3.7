from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.file_types import (
    FILE_TYPE_GROUPS, extension_filter_summary, extension_is_selected,
    load_extension_filters, normalize_extension_filters, save_extension_filters,
    supported_extensions,
)


class FileTypeSelectionTests(unittest.TestCase):
    def test_popular_document_formats_are_listed_first(self):
        extensions = supported_extensions("Documents")
        self.assertEqual(extensions[:5], [".pdf", ".docx", ".xlsx", ".xls", ".csv"])
        self.assertIn(".epub", extensions)
        self.assertIn(".eml", extensions)

    def test_normalization_deduplicates_and_rejects_unknown_extensions(self):
        actual = normalize_extension_filters({"Documents": ["pdf", ".PDF", ".docx", ".unknown"], "Not a category": [".pdf"]})
        self.assertEqual(actual, {"Documents": [".pdf", ".docx"]})

    def test_selecting_every_extension_normalizes_to_all_formats(self):
        self.assertEqual(normalize_extension_filters({"Documents": supported_extensions("Documents")}), {})

    def test_missing_category_filter_allows_every_supported_file_format(self):
        self.assertTrue(extension_is_selected(Path("record.pdf"), "Documents", {}))
        self.assertTrue(extension_is_selected(Path("record.xlsx"), "Documents", {}))

    def test_custom_document_filter_allows_only_selected_extensions(self):
        filters = {"Documents": [".pdf", ".docx"]}
        self.assertTrue(extension_is_selected(Path("statement.PDF"), "Documents", filters))
        self.assertTrue(extension_is_selected(Path("requisition.docx"), "Documents", filters))
        self.assertFalse(extension_is_selected(Path("workbook.xlsx"), "Documents", filters))

    def test_filters_are_saved_permanently_and_loaded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings" / "file_type_filters.json"
            filters = {"Documents": [".pdf", ".docx"], "Images": [".png"]}
            save_extension_filters(filters, path)
            self.assertEqual(load_extension_filters(path), filters)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), filters)

    def test_summary_reports_all_or_subset(self):
        summary = extension_filter_summary(["Documents", "Images"], {"Documents": [".pdf", ".docx"], "Images": []})
        self.assertIn("Documents: 2 selected", summary)
        self.assertIn("Images: all formats", summary)

    def test_catalog_extensions_are_not_duplicated_between_categories(self):
        ownership = {}
        duplicates = []
        for category in FILE_TYPE_GROUPS:
            for ext in supported_extensions(category):
                if ext in ownership and ownership[ext] != category:
                    duplicates.append((ext, ownership[ext], category))
                ownership[ext] = category
        self.assertEqual(duplicates, [])


if __name__ == "__main__":
    unittest.main()
