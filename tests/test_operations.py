import json
import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.models import PlannedFile, ScanPlan
from smart_drive_organizer.operations import run_plan, undo_move_journal


class OperationTests(unittest.TestCase):
    def _make_plan(self, root: Path, output: Path, filename="Monthly Statement.pdf") -> ScanPlan:
        source = root / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"original file contents")
        destination = output / "Documents" / "Monthly Statements" / "PDF" / filename
        item = PlannedFile(source, "Documents", "Monthly Statements", "PDF", destination, "test", 1.0, source.stat().st_size)
        return ScanPlan(root, output, ["Documents"], [item])

    def test_copy_keeps_original_and_creates_verified_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root, output = Path(temp) / "source", Path(temp) / "output"
            root.mkdir()
            plan = self._make_plan(root, output)
            result = run_plan(plan, "copy")
            target = Path(result["journal"]["actions"][0]["destination"])
            self.assertTrue(plan.files[0].source.exists())
            self.assertEqual(target.read_bytes(), b"original file contents")
            self.assertEqual(result["journal"]["actions"][0]["status"], "copied")

    def test_move_can_be_undone(self):
        with tempfile.TemporaryDirectory() as temp:
            root, output = Path(temp) / "source", Path(temp) / "output"
            root.mkdir()
            plan = self._make_plan(root, output)
            result = run_plan(plan, "move")
            self.assertFalse(plan.files[0].source.exists())
            target = Path(result["journal"]["actions"][0]["destination"])
            self.assertTrue(target.exists())
            undone = undo_move_journal(result["journal_path"])
            self.assertEqual(undone["restored"], 1)
            self.assertTrue(plan.files[0].source.exists())
            self.assertFalse(target.exists())

    def test_collision_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root, output = Path(temp) / "source", Path(temp) / "output"
            root.mkdir()
            plan = self._make_plan(root, output)
            plan.files[0].destination.parent.mkdir(parents=True, exist_ok=True)
            plan.files[0].destination.write_bytes(b"do not overwrite")
            result = run_plan(plan, "copy")
            action = result["journal"]["actions"][0]
            self.assertEqual(plan.files[0].destination.read_bytes(), b"do not overwrite")
            copied = Path(action["destination"])
            self.assertNotEqual(copied, plan.files[0].destination)
            self.assertEqual(copied.read_bytes(), b"original file contents")

    def test_undo_recovers_a_move_interrupted_before_journal_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            root, output = Path(temp) / "source", Path(temp) / "output"
            root.mkdir()
            source = root / "Monthly Statement.pdf"
            target = output / "Documents" / "Monthly Statements" / "PDF" / source.name
            target.parent.mkdir(parents=True)
            target.write_bytes(b"interrupted move contents")
            journal_path = output / ".smart_drive_organizer_history" / "run_interrupted.json"
            journal = {
                "mode": "move", "status": "running",
                "actions": [{"source": str(source), "destination": str(target), "status": "in_progress"}]
            }
            journal_path.parent.mkdir(parents=True)
            journal_path.write_text(json.dumps(journal), encoding="utf-8")
            result = undo_move_journal(journal_path)
            self.assertEqual(result["restored"], 1)
            self.assertEqual(source.read_bytes(), b"interrupted move contents")
            self.assertFalse(target.exists())

    def test_copy_run_is_not_eligible_for_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            root, output = Path(temp) / "source", Path(temp) / "output"
            root.mkdir()
            plan = self._make_plan(root, output)
            result = run_plan(plan, "copy")
            with self.assertRaises(ValueError):
                undo_move_journal(result["journal_path"])


if __name__ == "__main__":
    unittest.main()
