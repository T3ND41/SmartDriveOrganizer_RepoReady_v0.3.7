from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.content_reader import MAX_TEXT_CHARS, read_document_text


class ContentReaderTests(unittest.TestCase):
    def test_plain_text_extraction_is_not_limited_to_old_twelve_thousand_character_window(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "long.txt"
            content = "supplier quotation pressure valve " * 1000
            path.write_text(content, encoding="utf-8")
            result = read_document_text(path)
            self.assertGreater(len(result), 12000)
            self.assertLessEqual(len(result), MAX_TEXT_CHARS)

    def test_eml_extracts_subject_sender_and_text_body(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "supplier.eml"
            path.write_text(
                "From: sales@example.test\nTo: buyer@example.test\nSubject: HDPE quotation\n"
                "Content-Type: text/plain; charset=utf-8\n\n"
                "Please find the pressure test certificate and supplier quotation attached.",
                encoding="utf-8",
            )
            text = read_document_text(path)
            self.assertIn("HDPE quotation", text)
            self.assertIn("sales@example.test", text)
            self.assertIn("pressure test certificate", text)

    def test_unsupported_or_corrupt_document_does_not_raise(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.pdf"
            path.write_bytes(b"not a real PDF")
            self.assertEqual(read_document_text(path), "")


    def test_legacy_word_file_routes_to_optional_windows_reader(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.doc"
            path.write_bytes(b"legacy Word placeholder")
            with patch("smart_drive_organizer.content_reader._legacy_office_text", return_value="legacy Word text") as reader:
                self.assertEqual(read_document_text(path), "legacy Word text")
                reader.assert_called_once_with(path, "word")

    def test_legacy_excel_file_routes_to_optional_windows_reader(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.xls"
            path.write_bytes(b"legacy Excel placeholder")
            with patch("smart_drive_organizer.content_reader._legacy_office_text", return_value="legacy Excel text") as reader:
                self.assertEqual(read_document_text(path), "legacy Excel text")
                reader.assert_called_once_with(path, "excel")

    def test_legacy_powerpoint_file_routes_to_optional_windows_reader(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.ppt"
            path.write_bytes(b"legacy PowerPoint placeholder")
            with patch("smart_drive_organizer.content_reader._legacy_office_text", return_value="legacy PowerPoint text") as reader:
                self.assertEqual(read_document_text(path), "legacy PowerPoint text")
                reader.assert_called_once_with(path, "powerpoint")


if __name__ == "__main__":
    unittest.main()
