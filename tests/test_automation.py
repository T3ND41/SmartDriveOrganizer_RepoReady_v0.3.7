from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.automation import (
    AutomationConfig,
    AutomationEngine,
    load_settings,
    mark_undo_restored_sources,
    save_settings,
    validate_config,
)
from smart_drive_organizer.operations import latest_movable_journal, undo_move_journal
from smart_drive_organizer.classifier import save_topic_rules


class AutomationTests(unittest.TestCase):
    def _config(self, source: Path, output: Path, mode: str = "copy") -> AutomationConfig:
        return AutomationConfig(
            enabled=True,
            monitor_folders=[str(source)],
            output_folder=str(output),
            categories=["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Applications", "Fonts", "3D Models", "Others"],
            mode=mode,
            read_document_text=False,
            poll_interval_seconds=5,
            stable_observations=2,
        )

    def test_selective_automation_organizes_only_selected_document_topics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            config = self._config(source, output)
            config.categories = ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Applications", "Fonts", "3D Models", "Others"]
            config.topic_filter_enabled = True
            config.selected_topics = ["Statements", "Requisitions", "Quotations"]
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()  # baseline existing folder
                files = {
                    "Monthly Statement October 2026.pdf": b"statement",
                    "Purchase Requisition 004.docx": b"requisition",
                    "Supplier Quotation 008.xlsx": b"quotation",
                    "Supplier Invoice 010.pdf": b"invoice",
                    "Monthly Statement image.jpg": b"image",
                }
                for name, payload in files.items():
                    (source / name).write_bytes(payload)
                engine.scan_once()
                result = engine.scan_once()
                self.assertEqual(result["processed"], 3)
                self.assertTrue((output / "Documents" / "Statements" / "PDF" / "Monthly Statement October 2026.pdf").is_file())
                self.assertTrue((output / "Documents" / "Requisitions" / "DOCX" / "Purchase Requisition 004.docx").is_file())
                self.assertTrue((output / "Documents" / "Quotations" / "XLSX" / "Supplier Quotation 008.xlsx").is_file())
                self.assertTrue((source / "Supplier Invoice 010.pdf").is_file())
                self.assertTrue((source / "Monthly Statement image.jpg").is_file())
            finally:
                engine.close()

    def test_selective_automation_requires_topic_but_supports_non_document_categories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            source.mkdir()
            config = self._config(source, root / "Organized")
            config.topic_filter_enabled = True
            config.selected_topics = []
            with self.assertRaises(ValueError):
                validate_config(config)
            config.selected_topics = ["Site Photographs"]
            config.categories = ["Images"]
            self.assertEqual(validate_config(config), [source.resolve()])


    def test_custom_topic_automation_routes_images_and_ignores_unselected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            config = self._config(source, output)
            config.categories = ["Images"]
            config.topic_filter_enabled = True
            config.selected_topics = ["Site Photographs"]
            save_topic_rules(app_dir / "topic_rules.json", [{
                "name": "Site Photographs",
                "keywords": ["site photo", "worksite picture"],
                "categories": ["Images"],
            }])
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()
                photo = source / "Copperbelt Site Photo 001.jpg"
                unrelated = source / "Family Holiday.jpg"
                photo.write_bytes(b"site photo")
                unrelated.write_bytes(b"holiday")
                engine.scan_once()
                result = engine.scan_once()
                self.assertEqual(result["processed"], 1)
                self.assertTrue((output / "Images" / "Site Photographs" / "JPG" / photo.name).is_file())
                self.assertTrue(unrelated.is_file())
                self.assertTrue(photo.is_file())  # default action is Copy
            finally:
                engine.close()

    def test_first_scan_baselines_existing_files_without_moving_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            existing = source / "Old Monthly Statement.pdf"
            existing.write_bytes(b"existing")
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                result = engine.scan_once()
                self.assertEqual(result["processed"], 0)
                self.assertTrue(existing.exists())
                self.assertFalse(output.exists())
            finally:
                engine.close()

    def test_new_file_is_processed_after_stable_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                engine.scan_once()  # baseline existing folder
                incoming = source / "Site Requisition October 2026.pdf"
                incoming.write_bytes(b"new requisition")
                first = engine.scan_once()
                second = engine.scan_once()
                self.assertEqual(first["processed"], 0)
                self.assertEqual(second["processed"], 1)
                target = output / "Documents" / "Requisitions" / "PDF" / incoming.name
                self.assertTrue(target.is_file())
                self.assertTrue(incoming.is_file())
                self.assertEqual(target.read_bytes(), b"new requisition")
            finally:
                engine.close()

    def test_move_mode_relocates_new_file_to_shared_collection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "D-drive" / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            engine = AutomationEngine(self._config(source, output, mode="move"), app_dir=app_dir)
            try:
                engine.scan_once()
                incoming = source / "Delivery Note 101.pdf"
                incoming.write_bytes(b"delivery note")
                engine.scan_once()
                engine.scan_once()
                target = output / "Documents" / "Delivery Notes" / "PDF" / incoming.name
                self.assertTrue(target.is_file())
                self.assertFalse(incoming.exists())
                journal = latest_movable_journal(output, origin="automatic")
                self.assertIsNotNone(journal)
                self.assertEqual(mark_undo_restored_sources(journal, app_dir=app_dir, config=engine.config), 0)
            finally:
                engine.close()

    def test_automatic_move_can_be_undone_without_immediate_reprocessing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "D-drive" / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            config = self._config(source, output, mode="move")
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()
                incoming = source / "Delivery Note 101.pdf"
                incoming.write_bytes(b"delivery note")
                engine.scan_once()
                engine.scan_once()
                target = output / "Documents" / "Delivery Notes" / "PDF" / incoming.name
                self.assertTrue(target.is_file())
                self.assertFalse(incoming.exists())
                journal = latest_movable_journal(output, origin="automatic")
                self.assertIsNotNone(journal)
                result = undo_move_journal(journal)
                self.assertEqual(result["restored"], 1)
                self.assertTrue(incoming.is_file())
                self.assertFalse(target.exists())
                self.assertEqual(mark_undo_restored_sources(journal, app_dir=app_dir, config=config), 1)
                for _ in range(4):
                    engine.scan_once()
                self.assertTrue(incoming.is_file())
                self.assertFalse(target.exists())
            finally:
                engine.close()

    def test_output_cannot_be_ancestor_of_monitored_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads" / "Work"
            output = root / "Downloads"
            source.mkdir(parents=True)
            with self.assertRaises(ValueError):
                validate_config(self._config(source, output))

    def test_output_inside_monitored_folder_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = source / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            output.mkdir()
            previous_output = output / "already organized.pdf"
            previous_output.write_bytes(b"do not touch")
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                engine.scan_once()
                for _ in range(3):
                    engine.scan_once()
                self.assertEqual(list(output.iterdir()), [previous_output])
            finally:
                engine.close()

    def test_collision_is_renamed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            folder = output / "Documents" / "Requisitions" / "PDF"
            folder.mkdir(parents=True)
            existing = folder / "Requisition.pdf"
            existing.write_bytes(b"keep original")
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                engine.scan_once()
                incoming = source / "Requisition.pdf"
                incoming.write_bytes(b"new one")
                engine.scan_once()
                engine.scan_once()
                copies = sorted(folder.glob("Requisition*.pdf"))
                self.assertEqual(len(copies), 2)
                self.assertEqual(existing.read_bytes(), b"keep original")
                self.assertEqual((folder / "Requisition (1).pdf").read_bytes(), b"new one")
            finally:
                engine.close()

    def test_new_file_arriving_while_monitor_is_stopped_is_found_after_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            config = self._config(source, output)
            first = AutomationEngine(config, app_dir=app_dir)
            first.scan_once()  # create and persist the initial baseline
            first.close()

            incoming = source / "Delivery Note while offline.pdf"
            incoming.write_bytes(b"arrived while app was closed")
            second = AutomationEngine(config, app_dir=app_dir)
            try:
                second.scan_once()
                result = second.scan_once()
                target = output / "Documents" / "Delivery Notes" / "PDF" / incoming.name
                self.assertEqual(result["processed"], 1)
                self.assertTrue(target.is_file())
            finally:
                second.close()

    def test_already_known_file_modification_is_not_copied_again(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            incoming = source / "Monthly Statement.pdf"
            incoming.write_bytes(b"first version")
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                engine.scan_once()  # existing file is baselined, not organized
                incoming.write_bytes(b"modified version")
                for _ in range(4):
                    engine.scan_once()
                target = output / "Documents" / "Monthly Statements" / "PDF" / incoming.name
                self.assertFalse(target.exists())
                self.assertTrue(incoming.exists())
            finally:
                engine.close()

    def test_incomplete_download_suffix_is_not_indexed_or_organized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "Organized"
            app_dir = root / "appdata"
            source.mkdir()
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                engine.scan_once()
                partial = source / "Monthly Statement.pdf.crdownload"
                partial.write_bytes(b"still downloading")
                for _ in range(4):
                    engine.scan_once()
                self.assertFalse(output.exists())
                self.assertTrue(partial.exists())
            finally:
                engine.close()

    def test_settings_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            source.mkdir()
            output = root / "Organized"
            config = self._config(source, output)
            config.topic_filter_enabled = True
            config.selected_topics = ["Statements", "Requisitions", "Quotations"]
            target = root / "settings.json"
            save_settings(config, target)
            loaded = load_settings(target)
            self.assertEqual(loaded.monitor_folders, [str(source)])
            self.assertEqual(loaded.output_folder, str(output))
            self.assertTrue(loaded.topic_filter_enabled)
            self.assertEqual(loaded.selected_topics, ["Statements", "Requisitions", "Quotations"])
            self.assertEqual(validate_config(loaded), [source])

    def test_unavailable_monitored_drive_does_not_prevent_other_monitor_settings_loading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing = root / "USB-drive-that-is-not-connected"
            output = root / "Organized"
            config = AutomationConfig(
                enabled=True,
                monitor_folders=[str(missing)],
                output_folder=str(output),
                categories=["Documents"],
                mode="copy",
                read_document_text=False,
            )
            self.assertEqual(validate_config(config, allow_missing_roots=True), [missing])
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_monitoring_same_folder_as_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self._config(root, root)
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_custom_partial_keyword_automatically_routes_to_exact_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Organized"
            app_dir = root / "appdata"
            custom_destination = root / "Company Records" / "Quotations"
            source.mkdir()
            app_dir.mkdir()
            (app_dir / "topic_rules.json").write_text(json.dumps([{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(custom_destination),
            }]), encoding="utf-8")
            config = self._config(source, output)
            config.topic_filter_enabled = True
            config.selected_topics = ["My Quotations"]
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()  # baseline
                incoming = source / "Quotation - S01610.pdf"
                incoming.write_bytes(b"quotation file")
                for _ in range(4):
                    result = engine.scan_once()
                target = custom_destination / incoming.name
                self.assertTrue(target.is_file())
                self.assertTrue(incoming.is_file())  # default test config is Copy
                self.assertFalse((output / "Documents" / "My Quotations" / "PDF" / incoming.name).exists())
                self.assertEqual(result["processed"], 0)  # file was processed in an earlier stable cycle
            finally:
                engine.close()

    def test_custom_partial_keyword_uses_exact_destination_in_background(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Output"
            app_dir = root / "appdata"
            destination = root / "Company Records" / "Quotations"
            source.mkdir()
            app_dir.mkdir()
            (app_dir / "topic_rules.json").write_text(json.dumps([{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(destination),
            }]), encoding="utf-8")
            config = self._config(source, output)
            config.topic_filter_enabled = True
            config.selected_topics = ["My Quotations"]
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()  # initial baseline
                incoming = source / "Quotation - S01610.pdf"
                incoming.write_bytes(b"sample quotation")
                for _ in range(4):
                    engine.scan_once()
                self.assertTrue((destination / incoming.name).is_file())
                self.assertTrue(incoming.is_file())
                self.assertFalse((output / "Documents" / "My Quotations" / "PDF" / incoming.name).exists())
            finally:
                engine.close()

    def test_monitor_picks_up_keyword_destination_edits_without_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Output"
            app_dir = root / "appdata"
            destination = root / "Records" / "QUO"
            source.mkdir()
            app_dir.mkdir()
            config = self._config(source, output)
            config.topic_filter_enabled = True
            config.selected_topics = ["Quotations"]
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()  # baseline with no custom routing rule
                (app_dir / "topic_rules.json").write_text(json.dumps([{
                    "name": "Quotations", "keywords": ["QUO"],
                    "categories": ["Documents"], "match_mode": "contains",
                    "destination": str(destination),
                }]), encoding="utf-8")
                incoming = source / "Quotation - S01610.pdf"
                incoming.write_bytes(b"new quotation")
                for _ in range(4):
                    engine.scan_once()
                self.assertTrue((destination / incoming.name).is_file())
                self.assertTrue(incoming.is_file())
            finally:
                engine.close()

    def test_custom_destination_move_can_be_undone(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            output = root / "General Output"
            app_dir = root / "appdata"
            destination = root / "Company Records" / "Quotations"
            source.mkdir()
            app_dir.mkdir()
            (app_dir / "topic_rules.json").write_text(json.dumps([{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(destination),
            }]), encoding="utf-8")
            config = self._config(source, output, mode="move")
            config.topic_filter_enabled = True
            config.selected_topics = ["My Quotations"]
            engine = AutomationEngine(config, app_dir=app_dir)
            try:
                engine.scan_once()
                incoming = source / "Quotation - S01610.pdf"
                incoming.write_bytes(b"quotation to move")
                for _ in range(4):
                    engine.scan_once()
                target = destination / incoming.name
                self.assertTrue(target.is_file())
                self.assertFalse(incoming.exists())
                journal = latest_movable_journal(output, origin="automatic")
                self.assertIsNotNone(journal)
                undo_result = undo_move_journal(journal)
                self.assertEqual(undo_result["restored"], 1)
                self.assertTrue(incoming.is_file())
                self.assertFalse(target.exists())
                mark_undo_restored_sources(journal, app_dir=app_dir, config=config)
            finally:
                engine.close()

    def test_activity_log_records_processed_arrival(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "Downloads"
            source.mkdir()
            output = root / "Organized"
            app_dir = root / "appdata"
            engine = AutomationEngine(self._config(source, output), app_dir=app_dir)
            try:
                engine.scan_once()
                incoming = source / "Monthly Statement.pdf"
                incoming.write_bytes(b"statement")
                engine.scan_once()
                engine.scan_once()
                log = (app_dir / "automation_activity.jsonl").read_text(encoding="utf-8").splitlines()
                events = [json.loads(line) for line in log]
                self.assertTrue(any(item.get("event") == "file_organization" and item.get("status") == "copied" for item in events))
            finally:
                engine.close()


if __name__ == "__main__":
    unittest.main()
