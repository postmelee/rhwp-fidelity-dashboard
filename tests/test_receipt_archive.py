from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cohort_site import summarize
from core import BACKENDS, PROTOCOL, empty_backend
from receipt_archive import validate_archive


class ReceiptCoverageTests(unittest.TestCase):
    def setUp(self):
        identity = {"engine_sha": "1" * 40, "producer_sha": "2" * 40, "cohort_sha256": "3" * 64,
                    "run_id": 11, "attempt": 2, "protocol": PROTOCOL}
        docs = [{"id": name, "pages": 2, "source_sha256": "a" * 64, "pdf_sha256": "b" * 64,
                 "path_sha256": h * 64} for name, h in (("pilot", "c"), ("later", "d"))]
        result = {"schema_version": 1, "build_sha256": "4" * 64, "environment_sha256": "5" * 64,
                  "backends": {b: empty_backend() for b in BACKENDS}}
        stage = {**identity, "stage": "pilot", "measurement": result, "artifacts": {}}
        self.record = {**identity, "schema_version": 1, "tag": "v0.9.1", "receipt_sha256": "6" * 64,
                       "corpus_sha": "7" * 40, "docs": docs, "stages": {"pilot": stage}}

    def test_unattempted_pages_stay_visible(self):
        result = summarize(validate_archive(self.record))
        self.assertEqual(result["paired_pages"], 0)
        self.assertEqual(len(result["pages"]), 4)
        self.assertIsNone(result["pages"][-1]["native"])

    def test_refuse_wrong_attempt_and_unexpected_artifact(self):
        stage = self.record["stages"]["pilot"]
        stage["attempt"] = 1
        with self.assertRaises(ValueError):
            validate_archive(self.record)
        stage["attempt"] = 2
        stage["artifacts"]["unexpected"] = {}
        with self.assertRaises(ValueError):
            validate_archive(self.record)

    def test_mismatched_page_count_has_no_delta(self):
        stage = self.record["stages"]["pilot"]
        for b in BACKENDS:
            stage["measurement"]["backends"][b] = {
                "status": "complete", "exit_code": 0, "quality_alert": True,
                "documents": [{"id": "pilot", "status": "complete", "pdf_pages": 2,
                               "rendered_pages": 3 if b == "native" else 2,
                               "scores": [{"page": p, "raw": 99} for p in (1, 2)]}]}
            stage["artifacts"][b + "/pilot"] = {k: "8" * 64 for k in
                ("run_manifest_sha256", "export_sha256", "tsv_sha256", "font_supply_sha256")}
        result = summarize(validate_archive(self.record))
        self.assertEqual(result["paired_docs"], 0)
        self.assertEqual(result["docs_at_or_above_90"], 0)
        self.assertIsNone(result["lowest_below_90"])
        self.assertIsNone(result["pages"][0]["delta"])
        self.assertEqual(result["by_backend"]["native"]["page_count_mismatch"], 1)

    def test_print_floor_includes_boundary_and_checks_both_renderers(self):
        stage = self.record["stages"]["pilot"]
        for b in BACKENDS:
            stage["measurement"]["backends"][b] = {
                "status": "complete", "exit_code": 0, "quality_alert": True,
                "documents": [{"id": "pilot", "status": "complete", "pdf_pages": 2, "rendered_pages": 2,
                               "scores": [{"page": 1, "raw": 99}, {"page": 2, "raw": 90}]}]}
            stage["artifacts"][b + "/pilot"] = {k: "8" * 64 for k in
                ("run_manifest_sha256", "export_sha256", "tsv_sha256", "font_supply_sha256")}
        result = summarize(validate_archive(self.record))
        self.assertEqual((result["docs_at_or_above_90"], result["paired_docs"]), (1, 1))
        self.assertIsNone(result["lowest_below_90"])
        stage["measurement"]["backends"]["wasm"]["documents"][0]["scores"][1]["raw"] = 89.999
        result = summarize(validate_archive(self.record))
        self.assertEqual((result["docs_at_or_above_90"], result["paired_docs"]), (0, 1))
        self.assertEqual(result["lowest_below_90"], {"document": "pilot", "page": 2, "backend": "wasm", "score": 89.999})
