from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from smart_drive_organizer.operations import run_plan
from smart_drive_organizer.scanner import scan_directory, scan_directories


class WorkflowTests(unittest.TestCase):
    def test_monthly_statements_are_grouped_by_topic_and_extension(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "organized"
            source.mkdir()
            examples = {
                "monthly statement January.pdf": b"pdf sample",
                "monthly statement February.docx": b"docx sample",
                "monthly statement March.xlsx": b"xlsx sample",
                "delivery note 001.pdf": b"delivery sample",
            }
            for filename, contents in examples.items():
                (source / filename).write_bytes(contents)

            plan = scan_directory(source, output, ["Documents"], read_contents=False)
            result = run_plan(plan, "copy")

            self.assertEqual(result["succeeded"], 4)
            self.assertEqual(result["failed"], 0)
            expected = [
                output / "Documents" / "Monthly Statements" / "PDF" / "monthly statement January.pdf",
                output / "Documents" / "Monthly Statements" / "DOCX" / "monthly statement February.docx",
                output / "Documents" / "Monthly Statements" / "XLSX" / "monthly statement March.xlsx",
                output / "Documents" / "Delivery Notes" / "PDF" / "delivery note 001.pdf",
            ]
            for destination in expected:
                self.assertTrue(destination.is_file(), str(destination))
            self.assertEqual(len(list(source.iterdir())), 4)

    def test_requisitions_reuse_existing_topic_and_extension_folders(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "organized"
            source.mkdir()
            (source / "Site Requisition October 2026.pdf").write_bytes(b"pdf sample")
            (source / "Office_Requisition_November.xlsx").write_bytes(b"xlsx sample")

            existing_pdf_folder = output / "Documents" / "Requisitions" / "PDF"
            existing_pdf_folder.mkdir(parents=True)
            existing_file = existing_pdf_folder / "Earlier Requisition.pdf"
            existing_file.write_bytes(b"keep existing")

            plan = scan_directory(source, output, ["Documents"], read_contents=False)
            self.assertEqual({item.topic for item in plan.files}, {"Requisitions"})
            result = run_plan(plan, "copy")

            self.assertEqual(result["succeeded"], 2)
            self.assertEqual(result["failed"], 0)
            self.assertTrue(existing_file.is_file())
            self.assertEqual(existing_file.read_bytes(), b"keep existing")
            self.assertTrue((existing_pdf_folder / "Site Requisition October 2026.pdf").is_file())
            self.assertTrue((output / "Documents" / "Requisitions" / "XLSX" / "Office_Requisition_November.xlsx").is_file())
            self.assertTrue((source / "Site Requisition October 2026.pdf").is_file())

    def test_multi_drive_copy_journal_records_all_sources_and_handles_name_collisions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_a = root / "drive_a"
            source_b = root / "drive_b"
            output = root / "destination" / "organized"
            source_a.mkdir()
            source_b.mkdir()
            (source_a / "Monthly Statement.pdf").write_bytes(b"first")
            (source_b / "Monthly Statement.pdf").write_bytes(b"second")

            plan = scan_directories([source_a, source_b], output, ["Documents"], read_contents=False)
            result = run_plan(plan, "copy")

            self.assertEqual(result["succeeded"], 2)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(len(result["journal"]["source_roots"]), 2)
            copies = list((output / "Documents" / "Monthly Statements" / "PDF").glob("*.pdf"))
            self.assertEqual(len(copies), 2)
            self.assertTrue((source_a / "Monthly Statement.pdf").exists())
            self.assertTrue((source_b / "Monthly Statement.pdf").exists())

    def test_copy_can_target_a_subfolder_of_a_scanned_drive(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "drive"
            output = source / "Organized Collection"
            source.mkdir()
            (source / "Monthly Statement.pdf").write_bytes(b"source document")
            output.mkdir()
            (output / "old file.pdf").write_bytes(b"must not be rescanned or changed")

            plan = scan_directory(source, output, ["Documents"], read_contents=False)
            result = run_plan(plan, "copy")

            self.assertEqual(len(plan.files), 1)
            self.assertEqual(result["succeeded"], 1)
            self.assertEqual((source / "Monthly Statement.pdf").read_bytes(), b"source document")
            self.assertEqual((output / "old file.pdf").read_bytes(), b"must not be rescanned or changed")
            self.assertTrue((output / "Documents" / "Monthly Statements" / "PDF" / "Monthly Statement.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
