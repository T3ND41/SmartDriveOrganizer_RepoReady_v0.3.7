import tempfile
import unittest
from pathlib import Path

# Keep test output fixtures inside the checkout, not protected Windows AppData.
_TEST_TEMP_ROOT = Path(__file__).resolve().parents[1] / ".test-temp"
_TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_TEST_TEMP_ROOT)

from smart_drive_organizer.scanner import scan_directory, scan_directories


class ScannerTests(unittest.TestCase):
    def test_recursive_scan_builds_topic_then_extension_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            output = Path(temp) / "output"
            (root / "nested").mkdir(parents=True)
            (root / "nested" / "Monthly Statement 2026.pdf").write_bytes(b"sample")
            (root / "nested" / "Monthly Statement 2025.xlsx").write_bytes(b"sample")
            plan = scan_directory(root, output, ["Documents"], read_contents=False)
            self.assertEqual(len(plan.files), 2)
            destinations = {item.destination.relative_to(output).as_posix() for item in plan.files}
            self.assertIn("Documents/Monthly Statements/PDF/Monthly Statement 2026.pdf", destinations)
            self.assertIn("Documents/Monthly Statements/XLSX/Monthly Statement 2025.xlsx", destinations)

    def test_selective_scan_includes_only_selected_topics_and_leaves_others_unplanned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            output = Path(temp) / "output"
            root.mkdir()
            (root / "Monthly Statement.pdf").write_bytes(b"statement")
            (root / "Purchase Requisition.docx").write_bytes(b"requisition")
            (root / "Supplier Quotation.xlsx").write_bytes(b"quotation")
            (root / "Supplier Invoice.pdf").write_bytes(b"invoice")
            (root / "Monthly Statement.jpg").write_bytes(b"image")

            plan = scan_directory(
                root, output, ["Documents", "Images"], read_contents=False,
                topic_filter_enabled=True, selected_topics=["Statements", "Requisitions", "Quotations"],
            )

            self.assertEqual({item.source.name for item in plan.files}, {
                "Monthly Statement.pdf", "Purchase Requisition.docx", "Supplier Quotation.xlsx"
            })
            self.assertEqual({item.topic for item in plan.files}, {"Statements", "Requisitions", "Quotations"})
            self.assertTrue((root / "Supplier Invoice.pdf").exists())
            self.assertTrue((root / "Monthly Statement.jpg").exists())


    def test_custom_selective_topic_can_group_images_and_videos_by_user_keywords(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "Copperbelt Site Photo 001.jpg").write_bytes(b"image")
            (source / "Safety Induction Training Clip.mp4").write_bytes(b"video")
            (source / "Unrelated Holiday.jpg").write_bytes(b"other")
            topic_rules = [
                {"name": "Site Photographs", "keywords": ["site photo", "site photograph"], "categories": ["Images"]},
                {"name": "Safety Videos", "keywords": ["safety induction", "training clip"], "categories": ["Videos"]},
            ]
            plan = scan_directory(
                source, output, ["Images", "Videos"], read_contents=False,
                topic_filter_enabled=True,
                selected_topics=["Site Photographs", "Safety Videos"],
                topic_rules=topic_rules,
            )
            self.assertEqual({item.source.name for item in plan.files}, {
                "Copperbelt Site Photo 001.jpg", "Safety Induction Training Clip.mp4"
            })
            destinations = {item.destination.relative_to(output).as_posix() for item in plan.files}
            self.assertIn("Images/Site Photographs/JPG/Copperbelt Site Photo 001.jpg", destinations)
            self.assertIn("Videos/Safety Videos/MP4/Safety Induction Training Clip.mp4", destinations)
            self.assertTrue((source / "Unrelated Holiday.jpg").exists())


    def test_custom_keyword_routes_to_exact_user_selected_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Organized"
            custom_destination = root / "Company Records" / "Quotations"
            source.mkdir()
            quotation = source / "Quotation - S01610.pdf"
            quotation.write_bytes(b"quotation")
            other = source / "Monthly Statement.pdf"
            other.write_bytes(b"statement")
            topic_rules = [{
                "name": "My Quotations",
                "keywords": ["QUO"],
                "categories": ["Documents"],
                "match_mode": "contains",
                "destination": str(custom_destination),
            }]
            plan = scan_directory(
                source, output, ["Documents"], read_contents=False,
                topic_filter_enabled=True,
                selected_topics=["My Quotations"],
                topic_rules=topic_rules,
            )
            self.assertEqual(len(plan.files), 1)
            self.assertEqual(plan.files[0].source.name, quotation.name)
            self.assertEqual(plan.files[0].destination, custom_destination / quotation.name)
            self.assertTrue(other.exists())

    def test_custom_destination_inside_source_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Organized"
            custom_destination = source / "Company Records" / "Quotations"
            custom_destination.mkdir(parents=True)
            (source / "Quotation - S01610.pdf").write_bytes(b"quotation")
            (custom_destination / "Old Quotation.pdf").write_bytes(b"already sorted")
            topic_rules = [{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(custom_destination),
            }]
            plan = scan_directory(
                source, output, ["Documents"], read_contents=False,
                topic_filter_enabled=True, selected_topics=["My Quotations"], topic_rules=topic_rules,
            )
            self.assertEqual([item.source.name for item in plan.files], ["Quotation - S01610.pdf"])


    def test_partial_keyword_routes_to_exact_custom_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Output"
            destination = root / "Company Records" / "Quotations"
            source.mkdir()
            (source / "Quotation - S01610.pdf").write_bytes(b"quotation")
            (source / "Monthly Statement.pdf").write_bytes(b"statement")
            rules = [{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(destination),
            }]
            plan = scan_directory(
                source, output, ["Documents"], read_contents=False,
                topic_filter_enabled=True, selected_topics=["My Quotations"], topic_rules=rules,
            )
            self.assertEqual(len(plan.files), 1)
            self.assertEqual(plan.files[0].source.name, "Quotation - S01610.pdf")
            self.assertEqual(plan.files[0].destination, destination / "Quotation - S01610.pdf")
            self.assertTrue((source / "Monthly Statement.pdf").exists())

    def test_custom_destination_inside_monitored_source_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Output"
            destination = source / "Company Records" / "Quotations"
            destination.mkdir(parents=True)
            (source / "Quotation - S01610.pdf").write_bytes(b"new")
            (destination / "Older Quotation.pdf").write_bytes(b"old")
            rules = [{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(destination),
            }]
            plan = scan_directory(
                source, output, ["Documents"], read_contents=False,
                topic_filter_enabled=True, selected_topics=["My Quotations"], topic_rules=rules,
            )
            self.assertEqual([item.source.name for item in plan.files], ["Quotation - S01610.pdf"])

    def test_destination_equal_to_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            with self.assertRaises(ValueError):
                scan_directory(root, root, ["Documents"])

    def test_destination_inside_source_is_allowed_and_excluded_from_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            output = root / "Organized Output"
            output.mkdir(parents=True)
            (root / "Monthly Statement.pdf").write_bytes(b"source")
            (output / "Monthly Statement old.pdf").write_bytes(b"existing output")

            plan = scan_directory(root, output, ["Documents"], read_contents=False)

            self.assertEqual({item.source for item in plan.files}, {
                project / "Monthly Statement.pdf", root / "Monthly Statement.pdf"
            })
            self.assertTrue(any(".git" in item for item in plan.skipped_locations))
            self.assertTrue(any(".venv" in item for item in plan.skipped_locations))
            self.assertTrue(all(output not in item.source.parents for item in plan.files))

    def test_protected_system_folder_cannot_be_selected_as_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "Windows"
            source.mkdir()
            (source / "system32").mkdir()
            with self.assertRaises(ValueError):
                scan_directory(source, Path(temp) / "out", ["Documents"])

    def test_project_documents_are_scanned_but_git_and_venv_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            project = root / "sample_project"
            (project / ".git").mkdir(parents=True)
            (project / ".venv").mkdir()
            (project / "Monthly Statement.pdf").write_bytes(b"x")
            (project / ".venv" / "Monthly Statement.pdf").write_bytes(b"x")
            (root / "Monthly Statement.pdf").write_bytes(b"x")
            plan = scan_directory(root, Path(temp) / "out", ["Documents"], read_contents=False)
            self.assertEqual({item.source for item in plan.files}, {
                project / "Monthly Statement.pdf", root / "Monthly Statement.pdf"
            })
            self.assertTrue(any(".git" in item for item in plan.skipped_locations))
            self.assertTrue(any(".venv" in item for item in plan.skipped_locations))

    def test_multiple_sources_collect_into_one_output_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_a = root / "drive_a"
            source_b = root / "drive_b"
            output = root / "destination_drive" / "Organized"
            source_a.mkdir()
            source_b.mkdir()
            (source_a / "Monthly Statement.pdf").write_bytes(b"from drive a")
            (source_b / "Delivery Note.pdf").write_bytes(b"from drive b")

            plan = scan_directories([source_a, source_b], output, ["Documents"], read_contents=False)

            self.assertEqual(len(plan.source_roots), 2)
            self.assertEqual(plan.scanned_count, 2)
            self.assertEqual(len(plan.files), 2)
            self.assertEqual({item.source.parent for item in plan.files}, {source_a, source_b})
            self.assertTrue(all(item.destination.is_relative_to(output) for item in plan.files))

    def test_nested_sources_are_collapsed_to_prevent_duplicate_scans(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            nested = root / "nested"
            nested.mkdir(parents=True)
            output = Path(temp) / "output"
            (nested / "Monthly Statement.pdf").write_bytes(b"sample")

            plan = scan_directories([root, nested], output, ["Documents"], read_contents=False)

            self.assertEqual(len(plan.source_roots), 1)
            self.assertEqual(len(plan.files), 1)

    def test_multi_source_output_ancestor_is_rejected_before_scanning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_a = root / "source_a"
            source_b = root / "source_b"
            source_a.mkdir()
            source_b.mkdir()
            (source_a / "Monthly Statement.pdf").write_bytes(b"sample")

            with self.assertRaises(ValueError):
                scan_directories([source_a, source_b], source_b.parent, ["Documents"], read_contents=False)

    def test_output_path_that_is_a_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            output_file = Path(temp) / "not-a-folder"
            output_file.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                scan_directory(source, output_file, ["Documents"])


    def test_discovers_unselected_repeated_patterns_even_in_selective_topic_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            (root / "LPO_2024.pdf").write_bytes(b"one")
            (root / "LPO_2025.pdf").write_bytes(b"two")
            plan = scan_directory(
                root, Path(temp) / "output", ["Documents"], read_contents=False,
                topic_filter_enabled=True, selected_topics=["Statements"],
            )
            self.assertEqual(plan.files, [])
            self.assertTrue(any(group.phrase == "lpo" for group in plan.discovery_groups))

    def test_appdata_is_traversed_for_user_documents(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "drive"
            (root / "Users" / "Person" / "AppData" / "Local").mkdir(parents=True)
            (root / "Users" / "Person" / "AppData" / "Local" / "Statement.pdf").write_bytes(b"appdata user document")
            plan = scan_directory(root, Path(temp) / "output", ["Documents"], read_contents=False)
            self.assertEqual([item.source.name for item in plan.files], ["Statement.pdf"])

    def test_safe_deep_scan_skips_operating_system_and_application_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "drive"
            (root / "Users" / "Person" / "Documents").mkdir(parents=True)
            (root / "Windows" / "System32").mkdir(parents=True)
            (root / "Program Files" / "Sample App").mkdir(parents=True)
            (root / "ProgramData" / "Sample App").mkdir(parents=True)
            (root / "AppData" / "Local" / "Sample App").mkdir(parents=True)
            (root / "Boot").mkdir(parents=True)
            (root / "EFI" / "Microsoft" / "Boot").mkdir(parents=True)
            (root / "Users" / "Person" / "Documents" / "LPO_2024.pdf").write_bytes(b"user")
            (root / "Windows" / "System32" / "LPO_system.pdf").write_bytes(b"system")
            (root / "Program Files" / "Sample App" / "LPO_app.pdf").write_bytes(b"app")
            (root / "ProgramData" / "Sample App" / "LPO_data.pdf").write_bytes(b"data")
            (root / "AppData" / "Local" / "Sample App" / "LPO_cache.pdf").write_bytes(b"cache")
            (root / "Boot" / "BCD.ini").write_bytes(b"boot")
            (root / "EFI" / "Microsoft" / "Boot" / "boot.ini").write_bytes(b"efi")
            plan = scan_directory(root, Path(temp) / "output", ["Documents"], read_contents=False)
            self.assertEqual({item.source.name for item in plan.files}, {"LPO_2024.pdf", "LPO_cache.pdf"})
            self.assertEqual(len(plan.discovery_candidates), 2)


    def test_cancelled_scan_returns_partial_plan_without_applying_files(self):
        from smart_drive_organizer.operation_control import OperationControl

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            for index in range(5):
                (root / f"Monthly Statement {index}.pdf").write_bytes(b"statement")
            control = OperationControl()
            control.cancel()
            plan = scan_directory(
                root, Path(temp) / "output", ["Documents"],
                read_contents=False, control=control,
            )
            self.assertTrue(plan.cancelled)
            self.assertEqual(plan.files, [])
            self.assertTrue((root / "Monthly Statement 0.pdf").is_file())



if __name__ == "__main__":
    unittest.main()
