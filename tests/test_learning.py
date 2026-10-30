from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.learning import (
    load_memory, memory_summary, record_discovery_decisions,
    record_filing_correction, rejected_discovery_patterns,
)


class LearningMemoryTests(unittest.TestCase):
    def test_rejected_discovery_is_remembered_and_returned_to_scanner(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "learning_memory.json"
            record_discovery_decisions([], [{"phrase": "old supplier", "category": "Documents", "name": "Old Supplier"}], path)
            ignored = rejected_discovery_patterns(path)
            self.assertEqual(ignored, [{"category": "Documents", "phrase": "old supplier"}])
            self.assertEqual(memory_summary(path)["rejected_groups"], 1)

    def test_approval_clears_previous_rejection_for_same_pattern(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "learning_memory.json"
            record_discovery_decisions([], [{"phrase": "LPO", "category": "Documents"}], path)
            record_discovery_decisions([{"phrase": "LPO", "category": "Documents", "name": "Purchase Orders"}], [], path)
            self.assertEqual(rejected_discovery_patterns(path), [])
            self.assertEqual(memory_summary(path)["approved_groups"], 1)

    def test_filing_correction_is_persisted_and_updated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "learning_memory.json"
            record_filing_correction("Documents", "supplier quote", "Quotations", "C:/source/a.pdf", "C:/records/quotes", path)
            record_filing_correction("Documents", "supplier quote", "Supplier Quotations", path=path)
            memory = load_memory(path)
            self.assertEqual(len(memory["filing_corrections"]), 1)
            self.assertEqual(memory["filing_corrections"][0]["topic"], "Supplier Quotations")


if __name__ == "__main__":
    unittest.main()
