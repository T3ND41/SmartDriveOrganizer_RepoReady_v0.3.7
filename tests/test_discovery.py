from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_drive_organizer.discovery import discover_repeated_groups


class DiscoveryTests(unittest.TestCase):
    def _files(self, root: Path, names: list[str], category: str = "Documents"):
        root.mkdir(parents=True, exist_ok=True)
        result = []
        for name in names:
            path = root / name
            path.write_text("sample", encoding="utf-8")
            result.append((path, category))
        return result

    def test_discovers_an_acronym_repeated_across_distinct_files(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates = self._files(Path(temp), ["LPO_2024.pdf", "LPO_2025.xlsx", "LPO_2026.docx"])
            groups = discover_repeated_groups(candidates)
            match = next(group for group in groups if group.phrase == "lpo")
            self.assertEqual(match.file_count, 3)
            self.assertEqual(match.suggested_name, "LPOs")

    def test_one_file_never_satisfies_two_file_minimum(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates = self._files(Path(temp), ["LPO_LPO_Mufulira_2024.pdf"])
            self.assertEqual(discover_repeated_groups(candidates), [])

    def test_discovers_repeated_multiword_phrase_and_distinct_count(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates = self._files(Path(temp), [
                "Copperbelt_Safety_Inspection_001.pdf",
                "Copperbelt_Safety_Inspection_002.docx",
                "Copperbelt_Safety_Inspection_003.xlsx",
            ])
            groups = discover_repeated_groups(candidates)
            match = next(group for group in groups if group.phrase == "copperbelt safety inspection")
            self.assertEqual(match.file_count, 3)
            self.assertEqual(len(match.sample_files), 3)

    def test_known_builtin_topic_phrases_are_not_suggested_again(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates = self._files(Path(temp), [
                "Monthly_Statement_2024.pdf",
                "Monthly_Statement_2025.pdf",
            ])
            phrases = {group.phrase for group in discover_repeated_groups(candidates)}
            self.assertNotIn("monthly statement", phrases)
            self.assertNotIn("statement", phrases)

    def test_same_pattern_is_separated_by_file_category(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            docs = self._files(root / "docs", ["LPO_01.pdf", "LPO_02.pdf"], "Documents")
            images = self._files(root / "images", ["LPO_01.jpg", "LPO_02.jpg"], "Images")
            groups = discover_repeated_groups(docs + images)
            self.assertEqual({g.category for g in groups if g.phrase == "lpo"}, {"Documents", "Images"})

    def test_saved_rules_suppress_patterns_the_user_already_approved(self):
        with tempfile.TemporaryDirectory() as temp:
            candidates = self._files(Path(temp), ["LPO_01.pdf", "LPO_02.pdf"])
            rules = [{"name": "Purchase Orders", "keywords": ["LPO"], "category": "Documents"}]
            groups = discover_repeated_groups(candidates, custom_rules=rules)
            self.assertFalse(any(g.phrase == "lpo" for g in groups))


if __name__ == "__main__":
    unittest.main()
