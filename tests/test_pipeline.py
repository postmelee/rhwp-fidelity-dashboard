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
                "radius_px":2,"silhouette_method":"threshold_boundary_color_support_v1",
                "pr_review_gate":{"document_page_counts":{"pdf":2,"rhwp":2}},
                "metrics":[{"page":1,"silhouette_raw_match_percent":89},
                           {"page":2,"silhouette_raw_match_percent":95}]})
            self.assertEqual(adapter.consume(root, self.docs[0])["status"], "complete")
    def test_adapter_incomplete_not_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core.write_json(root/"silhouette_manifest.json", {
                "run_state":"incomplete","completed_pages":[1],
                "radius_px":2,"silhouette_method":"threshold_boundary_color_support_v1",
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

    def test_missing_publication_permission_rejected(self):
        d = {"id":"sample","compat":"2024","pages":1,"fonts":[],
             "publication":{"approved":False,"metadata_approved":True,"evidence":"test"},
             **{k:{"path":"example","sha256":"0"*64,"source":"test","provenance":"Hancom Print 2024"}
                for k in ("document","golden","font_environment")}}
        with tempfile.TemporaryDirectory() as temp:
            core.write_json(Path(temp)/"manifest.json", {"schema_version":1,"documents":[d]})
            with self.assertRaises(ValueError):
                core.manifest(temp, verify=False)
    def test_complete_execution_failure_rejected(self):
        b = copy.deepcopy(self.backend)
        b["exit_code"] = 2
        with self.assertRaises(ValueError):
            core.validate_backend(b, self.docs)
    def test_scores_require_build_provenance(self):
        m = {"schema_version":1, "build_sha256":None, "environment_sha256":None,
             "backends":{"native":self.backend,"wasm":core.empty_backend()}}
        with self.assertRaises(ValueError):
            core.validate_measurement(m, self.docs)
    def test_latest_attempt_does_not_replace_last_complete(self):
        m = {"schema_version":1,"build_sha256":"a"*64,"environment_sha256":"b"*64,
             "backends":{"native":copy.deepcopy(self.backend),"wasm":copy.deepcopy(self.backend)}}
        first = {"source_ref":"v1", "upstream_sha":"1"*40, "status":"complete",
                 "run_id":1,"attempt":1,"measurement":m}
        last = {"source_ref":"v2", "upstream_sha":"2"*40, "status":"failed",
                "run_id":2,"attempt":1,"measurement":{"schema_version":1,"build_sha256":None,
                    "environment_sha256":None,"backends":{b:core.empty_backend() for b in core.BACKENDS}}}
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(pipeline,"manifest",return_value={"documents":self.docs}), patch.object(
                    pipeline,"history",return_value=[first,last]):
                pipeline.build(Path(temp)/"records", Path(temp)/"site", Path(temp))
            summary = core.read_json(Path(temp)/"site/summary.json")
            self.assertEqual(summary["latest_attempted"]["run_id"],2)
            self.assertEqual(summary["last_complete"]["run_id"],1)

if __name__ == "__main__":
    unittest.main()
