import unittest
import tempfile
from pathlib import Path

from smart_drive_organizer.classifier import (
    category_for, classify_selected_topic, classify_topic, extension_bucket, safe_folder_name,
    load_topic_rules, save_topic_rules,
)


class ClassifierTests(unittest.TestCase):
    def test_monthly_statement_rule(self):
        topic, reason, confidence = classify_topic(Path("Monthly_Statement_October_2026.pdf"), "Documents")
        self.assertEqual(topic, "Monthly Statements")
        self.assertIn("filename", reason)
        self.assertGreater(confidence, 0.9)

    def test_generic_requisition_filename_rule(self):
        topic, reason, confidence = classify_topic(Path("Site_Requisition_October_2026.pdf"), "Documents")
        self.assertEqual(topic, "Requisitions")
        self.assertIn("filename", reason)
        self.assertGreater(confidence, 0.9)

    def test_purchase_requisition_keeps_more_specific_group(self):
        topic, _, _ = classify_topic(Path("Purchase_Requisition_004.pdf"), "Documents")
        self.assertEqual(topic, "Purchase Requisitions")

    def test_delivery_note_rule(self):
        topic, _, _ = classify_topic(Path("DN-001_delivery-note.docx"), "Documents")
        self.assertEqual(topic, "Delivery Notes")

    def test_document_content_can_match(self):
        topic, reason, confidence = classify_topic(Path("scan_001.pdf"), "Documents", "MONTHLY STATEMENT FOR ACCOUNT 123")
        self.assertEqual(topic, "Monthly Statements")
        self.assertIn("document text", reason)
        self.assertGreater(confidence, 0.7)

    def test_custom_rule_applies_only_to_requested_category(self):
        rules = [{"name": "Site Inductions", "keywords": ["site induction"], "category": "Documents"}]
        topic, _, _ = classify_topic(Path("site-induction.pdf"), "Documents", custom_rules=rules)
        self.assertEqual(topic, "Site Inductions")
        other, _, _ = classify_topic(Path("site-induction.jpg"), "Images", custom_rules=rules)
        self.assertEqual(other, "Unclassified Images")

    def test_selective_statement_group_collapses_monthly_statement_label(self):
        result = classify_selected_topic(Path("Monthly_Statement_October_2026.pdf"), "Documents", selected_topics=["Statements"])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Statements")

    def test_selective_requisition_group_matches_purchase_requisition(self):
        result = classify_selected_topic(Path("Purchase_Requisition_004.pdf"), "Documents", selected_topics=["Requisitions"])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Requisitions")

    def test_selective_quotation_group_matches_rfq(self):
        result = classify_selected_topic(Path("RFQ_Valve_Quote.pdf"), "Documents", selected_topics=["Quotations"])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Quotations")

    def test_selective_topic_returns_none_for_unselected_topic_and_non_documents(self):
        self.assertIsNone(classify_selected_topic(Path("Supplier_Invoice.pdf"), "Documents", selected_topics=["Statements", "Requisitions", "Quotations"]))
        self.assertIsNone(classify_selected_topic(Path("Monthly_Statement.jpg"), "Images", selected_topics=["Statements"]))


    def test_custom_user_topic_matches_multiple_keywords_for_any_file_type(self):
        rules = [{
            "name": "Site Photographs",
            "keywords": ["site photo", "site photograph", "worksite picture"],
            "categories": ["Any"],
        }]
        result = classify_selected_topic(
            Path("Copperbelt_Site_Photo_Inspection_01.jpg"),
            "Images",
            selected_topics=["Site Photographs"],
            topic_rules=rules,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Site Photographs")
        self.assertIn("site photo", result[1])

    def test_custom_topic_category_scope_is_respected(self):
        rules = [{
            "name": "Training Videos",
            "keywords": ["safety induction", "training clip"],
            "categories": ["Videos"],
        }]
        video = classify_selected_topic(Path("Safety_Induction_2026.mp4"), "Videos", selected_topics=["Training Videos"], topic_rules=rules)
        image = classify_selected_topic(Path("Safety_Induction_2026.jpg"), "Images", selected_topics=["Training Videos"], topic_rules=rules)
        self.assertIsNotNone(video)
        self.assertIsNone(image)

    def test_custom_topic_can_match_supported_document_body(self):
        rules = [{
            "name": "Supplier Invoices",
            "keywords": ["vendor tax invoice", "supplier bill"],
            "categories": ["Documents"],
        }]
        result = classify_selected_topic(
            Path("scan_0004.pdf"), "Documents", "VENDOR TAX INVOICE", ["Supplier Invoices"], topic_rules=rules
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "Supplier Invoices")
        self.assertIn("document text", result[1])

    def test_topic_rules_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "topics.json"
            rules = [{"name": "Supplier Invoices", "keywords": ["invoice", "vendor bill"], "categories": ["Documents"]}]
            save_topic_rules(path, rules)
            self.assertEqual(load_topic_rules(path), [{
                "name": "Supplier Invoices",
                "keywords": ["invoice", "vendor bill"],
                "categories": ["Documents"],
                "destination": "",
                "match_mode": "whole_phrase",
            }])

    def test_partial_keyword_quo_matches_quotation_filename(self):
        rules = [{
            "name": "My Quotations",
            "keywords": ["QUO"],
            "categories": ["Documents"],
            "match_mode": "contains",
        }]
        result = classify_selected_topic(
            Path("Quotation - S01610.pdf"), "Documents",
            selected_topics=["My Quotations"], topic_rules=rules,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "My Quotations")
        self.assertIn("QUO", result[1])

    def test_whole_phrase_mode_does_not_treat_partial_keyword_as_match(self):
        rules = [{
            "name": "My Quotations",
            "keywords": ["QUO"],
            "categories": ["Documents"],
            "match_mode": "whole_phrase",
        }]
        result = classify_selected_topic(
            Path("Quotation - S01610.pdf"), "Documents",
            selected_topics=["My Quotations"], topic_rules=rules,
        )
        self.assertIsNone(result)

    def test_topic_destination_round_trip(self):
        from smart_drive_organizer.classifier import selected_topic_destination
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "topics.json"
            destination = Path(temp) / "Company Records" / "Quotations"
            rules = [{
                "name": "My Quotations", "keywords": ["QUO"],
                "categories": ["Documents"], "match_mode": "contains",
                "destination": str(destination),
            }]
            save_topic_rules(path, rules)
            loaded = load_topic_rules(path)
            self.assertEqual(selected_topic_destination("My Quotations", loaded), destination.resolve())

    def test_folder_name_is_sanitized_for_windows_paths(self):
        self.assertEqual(safe_folder_name("  ../../Invoices\\2026:*  "), "Invoices 2026")
        self.assertEqual(safe_folder_name("CON"), "_CON")

    def test_extension_mapping(self):
        self.assertEqual(category_for(Path("invoice.xlsx")), "Documents")
        self.assertEqual(category_for(Path("mine-tour.mp4")), "Videos")
        self.assertEqual(extension_bucket(Path("photo.final.JPG")), "JPG")
        self.assertEqual(extension_bucket(Path("README")), "NO EXTENSION")

    def test_multiple_keywords_all_route_to_same_custom_topic_destination(self):
        from smart_drive_organizer.classifier import selected_topic_destination
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            destination = Path(temp) / "Company Records" / "Quotations"
            rules = [{
                "name": "Quotations",
                "keywords": ["QUO", "Quotation", "Quote", "RFQ"],
                "categories": ["Documents"],
                "match_mode": "contains",
                "destination": str(destination),
            }]
            for filename in ("QUO-S01610.pdf", "Quotation-S01611.pdf", "Quote-S01612.pdf", "RFQ-S01613.pdf"):
                result = classify_selected_topic(Path(filename), "Documents", selected_topics=["Quotations"], topic_rules=rules)
                self.assertIsNotNone(result, filename)
                self.assertEqual(result[0], "Quotations")
            self.assertEqual(selected_topic_destination("Quotations", rules), destination.resolve())

    def test_custom_keyword_rule_persists_all_keywords_and_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "topic_rules.json"
            destination = Path(temp) / "records" / "quotations"
            original = [{
                "name": "Quotations",
                "keywords": ["QUO", "Quotation", "Quote", "RFQ"],
                "categories": ["Documents"],
                "match_mode": "contains",
                "destination": str(destination),
            }]
            save_topic_rules(path, original)
            reopened = load_topic_rules(path)
            self.assertEqual(reopened[0]["keywords"], original[0]["keywords"])
            self.assertEqual(reopened[0]["destination"], str(destination))

    def test_q_hyphen_u_hyphen_o_is_normalized_as_partial_code(self):
        rules = [{"name": "Quotations", "keywords": ["Q-U-O"], "categories": ["Documents"], "match_mode": "contains"}]
        result = classify_selected_topic(Path("Quotation - S01610.pdf"), "Documents", selected_topics=["Quotations"], topic_rules=rules)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
