import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import core
import pipeline
import adapter

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.docs = [{"id":"sample", "pages":2}]
        self.backend = {"status":"complete", "exit_code":1, "quality_alert":True,
                        "documents":[{"id":"sample", "status":"complete", "pdf_pages":2,
                                      "rendered_pages":2, "scores":[{"page":1,"raw":89.1},{"page":2,"raw":95}]}]}
    def test_quality_exit_one_is_complete(self):
        self.assertEqual(core.validate_backend(self.backend, self.docs)["status"], "complete")
        self.assertEqual(core.coverage(self.backend, self.docs)["below90"], 1)
    def test_finite_and_numeric(self):
        for value in (float("nan"), float("inf"), -1, 101, True, "99"):
            with self.subTest(value=value):
                b = copy.deepcopy(self.backend)
                b["documents"][0]["scores"][0]["raw"] = value
                with self.assertRaises(ValueError):
                    core.validate_backend(b, self.docs)
    def test_duplicate_and_missing_pages(self):
        for scores in ([{"page":1,"raw":99}], [{"page":1,"raw":99},{"page":1,"raw":99}]):
            b = copy.deepcopy(self.backend)
            b["documents"][0]["scores"] = scores
            with self.assertRaises(ValueError):
                core.validate_backend(b, self.docs)
    def test_unknown_metadata_rejected(self):
        b = copy.deepcopy(self.backend)
        b["html"] = "<script>alert(1)</script>"
        with self.assertRaises(ValueError):
            core.validate_backend(b, self.docs)
    def test_page_count_mismatch_not_hidden(self):
        b = copy.deepcopy(self.backend)
        b["documents"][0]["rendered_pages"] = 3
        core.validate_backend(b, self.docs)
        self.assertEqual(core.coverage(b, self.docs)["page_count_mismatch"], 1)
    def test_empty_statistics_not_fabricated(self):
        self.assertEqual(core.stats([]), {"median":None, "p10":None, "min":None, "below90":0})
    def test_nearest_rank_percentile(self):
        self.assertEqual(core.stats(list(range(1, 21)))["p10"], 2)
    def test_unavailable_coverage(self):
        c = core.coverage(core.empty_backend(), self.docs)
        self.assertEqual((c["skipped_docs"], c["skipped_pages"], c["measured_pages"]), (1,2,0))
    def test_path_traversal_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"ok").write_text("ok")
            (root/"link").symlink_to(root/"ok")
            for path in ("../ok", "/etc/passwd", "link", "a\\b"):
                with self.assertRaises(ValueError):
                    core.safe_file(root, path)
    def test_ref_rejects_shell_input_before_network(self):
        for ref in ("$(whoami)", "--help", "../main", "a\nb"):
            with self.assertRaises(ValueError):
                pipeline.resolve_ref(ref)
    def test_annotated_tag_chain(self):
        with patch.object(pipeline, "api", side_effect=[
            {"object":{"type":"tag","sha":"a"*40}},
            {"object":{"type":"tag","sha":"b"*40}},
            {"object":{"type":"commit","sha":"c"*40}}]):
            self.assertEqual(pipeline.resolve_ref("v1.0.0"), ("c"*40,"manual-tag"))
    def test_retag_changes_identity(self):
        fields = {k:"x" for k in ("upstream_sha","corpus_sha256","font_sha256","adapter_sha256","protocol")}
        changed = dict(fields, upstream_sha="y")
        self.assertNotEqual(pipeline.identity(fields), pipeline.identity(changed))
    def test_tag_cycle_rejected(self):
        with patch.object(pipeline,"api",return_value={"object":{"type":"tag","sha":"a"*40}}):
            with self.assertRaises(ValueError):
                pipeline.resolve_ref("v1")
    def test_empty_page_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pipeline.build(root/"records", root/"site", pipeline.ROOT/"corpus")
            page = (root/"site/index.html").read_text()
            data = core.read_json(root/"site/summary.json")
            self.assertIn("No measurements available", page)
            self.assertIn("overflow-x:auto", page)
            self.assertIsNone(data["last_complete"])
            self.assertEqual(data["target_documents"], 0)
    def test_adapter_accepts_complete_warning_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core.write_json(root/"silhouette_manifest.json", {
                "run_state":"complete","completed_pages":[1,2],
                "pr_review_gate":{"document_page_counts":{"pdf":2,"rhwp":2}},
                "metrics":[{"page":1,"silhouette_raw_match_percent":89},
                           {"page":2,"silhouette_raw_match_percent":95}]})
            self.assertEqual(adapter.consume(root, self.docs[0])["status"], "complete")
    def test_adapter_incomplete_not_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core.write_json(root/"silhouette_manifest.json", {
                "run_state":"incomplete","completed_pages":[1],
                "pr_review_gate":{"document_page_counts":{"pdf":2,"rhwp":2}},
                "metrics":[{"page":1,"silhouette_raw_match_percent":99}]})
            self.assertEqual(adapter.consume(root, self.docs[0])["status"], "failed")
    def test_workflow_security_contract(self):
        text = (pipeline.ROOT/".github/workflows/fidelity.yml").read_text()
        self.assertNotIn("pull_request_target", text)
        self.assertNotIn("--resume", text)
        self.assertNotIn("persist-credentials: true", text)
        for line in text.splitlines():
            if "uses:" in line:
                self.assertRegex(line.strip(), r"uses: [A-Za-z0-9_/-]+@[0-9a-f]{40}$")
        self.assertIn('REQUESTED_REF:', text)
        self.assertIn('contents: read', text)
        self.assertIn('id-token: write', text)
        self.assertIn('path: result.json', text)

if __name__ == "__main__":
    unittest.main()
