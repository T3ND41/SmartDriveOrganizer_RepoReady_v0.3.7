from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.duplicates import analyze_duplicates, recycle_exact_duplicates
from smart_drive_organizer.search_index import SearchIndex


class DuplicateDetectionTests(unittest.TestCase):
    def test_detects_exact_file_duplicates_by_sha256(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "Statement A.pdf", root / "Statement B.pdf"
            first.write_bytes(b"same bytes")
            second.write_bytes(b"same bytes")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents", "same content")
            index.upsert_file(second, "Documents", "same content")
            index.close()
            result = analyze_duplicates(database)
            self.assertEqual(len(result["exact"]), 1)
            self.assertEqual(result["exact"][0]["count"], 2)

    def test_detects_possible_versions_from_versioned_filenames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "Service Contract v1.pdf", root / "Service Contract v2.pdf"
            first.write_bytes(b"draft version one")
            second.write_bytes(b"revised version two")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents", "first")
            index.upsert_file(second, "Documents", "second")
            index.close()
            result = analyze_duplicates(database)
            self.assertEqual(len(result["versions"]), 1)
            self.assertEqual(result["versions"][0]["count"], 2)

    def test_detects_near_identical_document_text_without_changing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            text = ("supplier quotation contains a detailed description of the required industrial "
                    "valve assembly including pressure rating material specification delivery terms "
                    "inspection certificate packing requirements and warranty conditions for the "
                    "approved project procurement request")
            first, second = root / "Supplier Offer A.txt", root / "Supplier Offer B.txt"
            first.write_text(text, encoding="utf-8")
            second.write_text(text.replace("approved project", "specified project"), encoding="utf-8")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents", text)
            index.upsert_file(second, "Documents", second.read_text(encoding="utf-8"))
            index.close()
            result = analyze_duplicates(database, similarity_threshold=0.85)
            self.assertEqual(len(result["near"]), 1)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())


    def test_groups_plain_base_filename_with_explicit_version_variant(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "Service Contract.pdf", root / "Service Contract v2.pdf"
            first.write_bytes(b"base contract")
            second.write_bytes(b"revised contract")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents", "base contract")
            index.upsert_file(second, "Documents", "revised contract")
            index.close()
            result = analyze_duplicates(database)
            self.assertEqual(len(result["versions"]), 1)
            self.assertEqual(result["versions"][0]["count"], 2)
            self.assertEqual({item["name"] for item in result["versions"][0]["files"]},
                             {"Service Contract.pdf", "Service Contract v2.pdf"})


    def test_reports_when_duplicate_analysis_limit_excludes_indexed_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "A.pdf"
            second = root / "B.pdf"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents", "first")
            index.upsert_file(second, "Documents", "second")
            index.close()
            result = analyze_duplicates(database, max_records=1)
            self.assertEqual(result["records_checked"], 1)
            self.assertEqual(result["index_total"], 2)
            self.assertTrue(result["truncated"])


    def test_exact_duplicate_recycle_action_keeps_chosen_file_and_removes_other_index_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "Older.pdf", root / "Newer.pdf"
            first.write_bytes(b"identical approved content")
            second.write_bytes(b"identical approved content")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents", "shared body", "Statements", text_indexed=True)
            index.upsert_file(second, "Documents", "shared body", "Statements", text_indexed=True)
            index.close()
            group = analyze_duplicates(database)["exact"][0]
            recycled = []
            result = recycle_exact_duplicates(
                group, second, database=database, recycle=lambda path: recycled.append(path)
            )
            self.assertEqual(recycled, [str(first.resolve())])
            self.assertEqual(result["recycled_count"], 1)
            self.assertTrue(second.is_file())
            index = SearchIndex(database)
            rows = index.search(query="shared body")
            index.close()
            self.assertEqual([row["path"] for row in rows], [str(second.resolve())])

    def test_non_exact_duplicate_groups_are_never_eligible_for_recycling(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Contract v2.pdf"
            path.write_bytes(b"new contract")
            recycled = []
            with self.assertRaisesRegex(ValueError, "Only byte-for-byte exact"):
                recycle_exact_duplicates(
                    {"kind": "Possible document versions", "files": [{"path": str(path)}]},
                    path, recycle=lambda value: recycled.append(value),
                )
            self.assertEqual(recycled, [])
            self.assertTrue(path.is_file())

    def test_changed_copy_is_left_untouched_after_duplicate_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "A.pdf", root / "B.pdf"
            first.write_bytes(b"identical before review")
            second.write_bytes(b"identical before review")
            database = root / "index.sqlite3"
            index = SearchIndex(database)
            index.upsert_file(first, "Documents")
            index.upsert_file(second, "Documents")
            index.close()
            group = analyze_duplicates(database)["exact"][0]
            second.write_bytes(b"changed after review")
            recycled = []
            result = recycle_exact_duplicates(
                group, first, database=database, recycle=lambda value: recycled.append(value)
            )
            self.assertEqual(recycled, [])
            self.assertEqual(len(result["skipped"]), 1)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())



if __name__ == "__main__":
    unittest.main()
