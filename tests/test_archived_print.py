import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import digest
from receipt_cohort import verify_registered


class ArchivedPrintTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "id": "archived-case",
            "input": "samples/case.hwpx",
            "source_sha256": "a" * 64,
            "pdf": "pdf/case-2024.pdf",
            "pdf_sha256": "b" * 64,
            "pages": 2,
            "reference_revision": "c" * 40,
            "reference_evidence": "mydocs/pr/assets/official-print-references.json",
            "reference_archive": "official-print-references-v1",
            "hancom": "2024",
            "compat": "2024",
        }
        self.archive = {
            "references": [{
                "key": "case",
                "input": self.document["input"],
                "input_sha256": self.document["source_sha256"],
                "pdf": self.document["pdf"],
                "pdf_sha256": self.document["pdf_sha256"],
                "pages": 2,
                "receipt": {
                    "job_id": "1d535beb-ec42-4ea9-b3ef-a318fedddd61",
                    "hancom_version": "13.0.0.3901",
                    "engine": "2024",
                    "pdf_print_method": 0,
                    "pdf_output_mode": "frame_print_to_pdf_ex_one_up",
                    "input_preprocess": "none",
                    "pdf_page_count": 2,
                },
            }],
            "independent_print_content_control": [{
                "document": "case",
                "prior_pages": 2,
                "new_pages": 2,
                "matched_text_pages": 2,
                "print_text_differences": [],
            }],
        }

    def verify(self, expected_digest=None):
        raw = json.dumps(self.archive).encode()
        doc = dict(self.document, reference_evidence_sha256=expected_digest or digest(raw))
        with patch("registered_print_queue.fetch", return_value=raw) as fetch:
            verify_registered({"documents": [doc]})
            fetch.assert_called_once_with(doc["reference_revision"], doc["reference_evidence"])

    def test_archived_reference_validates_through_normal_cohort_entrypoint(self):
        self.verify()

    def test_rejects_replaced_archive_and_pdf(self):
        with self.assertRaisesRegex(ValueError, "pinned evidence"):
            self.verify(expected_digest="0" * 64)
        self.archive["references"][0]["pdf_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "pinned measurement input"):
            self.verify()

    def test_rejects_different_modes_and_preprocessing(self):
        receipt = self.archive["references"][0]["receipt"]
        for key, value in (("pdf_output_mode", "hancom2024_pdf_driver_one_up"),
                           ("input_preprocess", "scripts_disabled"),
                           ("pdf_print_method", False),
                           ("pdf_page_count", 1),
                           ("job_id", "not-a-job-uuid"),
                           ("hancom_version", "13.0")):
            with self.subTest(key=key), patch.dict(receipt, {key: value}):
                with self.assertRaisesRegex(ValueError, "job conditions"):
                    self.verify()

    def test_rejects_different_compatibility_profile(self):
        self.document["compat"] = "2022"
        with self.assertRaisesRegex(ValueError, "job conditions"):
            self.verify()

    def test_rejects_incomplete_text_comparison(self):
        self.archive["independent_print_content_control"][0]["matched_text_pages"] = 1
        with self.assertRaisesRegex(ValueError, "content control"):
            self.verify()
