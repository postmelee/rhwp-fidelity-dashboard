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
import presentation
import wait_pages_artifact

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.docs = [{"id":"sample", "pages":2}]
        self.backend = {"status":"complete", "exit_code":1, "quality_alert":True,
                        "documents":[{"id":"sample", "status":"complete", "pdf_pages":2,
                                      "rendered_pages":2, "scores":[{"page":1,"raw":89.1},{"page":2,"raw":95}]}]}
    def test_pairing_requires_same_complete_count_matched_document(self):
        record = {"measurement":{"backends":{"native":copy.deepcopy(self.backend),"wasm":copy.deepcopy(self.backend)}}}
        rows = presentation.paired_pages(record,self.docs)
        self.assertEqual(rows[0], ("sample",1,89.1,89.1,0))
        record["measurement"]["backends"]["native"]["documents"][0]["rendered_pages"] = 3
        self.assertTrue(all(row[2:] == (None,None,None) for row in presentation.paired_pages(record,self.docs)))
        record["measurement"]["backends"]["native"]["documents"] = []
        self.assertTrue(all(row[2:] == (None,None,None) for row in presentation.paired_pages(record,self.docs)))
    def test_pairing_never_fills_missing_page_with_zero(self):
        record = {"measurement":{"backends":{"native":copy.deepcopy(self.backend),"wasm":copy.deepcopy(self.backend)}}}
        record["measurement"]["backends"]["wasm"]["documents"][0]["scores"].pop()
        self.assertEqual(presentation.paired_pages(record,self.docs)[1][2:], (None,None,None))
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
        fields = {k:"x" for k in ("source_ref","upstream_sha","corpus_sha256","font_sha256","adapter_sha256","protocol")}
        changed = dict(fields, upstream_sha="y")
        self.assertNotEqual(pipeline.identity(fields), pipeline.identity(changed))
    def test_tag_cycle_rejected(self):
        with patch.object(pipeline,"api",return_value={"object":{"type":"tag","sha":"a"*40}}):
            with self.assertRaises(ValueError):
                pipeline.resolve_ref("v1")
    def test_empty_page_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core.write_json(root/"corpus/manifest.json", {"schema_version":1,"documents":[]})
            pipeline.build(root/"records", root/"site", root/"corpus")
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
             "publication":{"approved":False,"metadata_approved":True,"raw_files":False,"evidence":"test"},
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
                 "run_id":1,"attempt":1,"resolved_at":"2026-01-01T00:00:00Z","measurement":m}
        last = {"source_ref":"v2", "upstream_sha":"2"*40, "status":"failed",
                "run_id":2,"attempt":1,"resolved_at":"2026-01-02T00:00:00Z","measurement":{"schema_version":1,"build_sha256":None,
                    "environment_sha256":None,"backends":{b:core.empty_backend() for b in core.BACKENDS}}}
        for record in (first,last):
            record.update(dashboard_sha="3"*40, source_kind="stable-release", protocol=core.PROTOCOL,
                          corpus_sha256="c"*64, font_sha256="d"*64, adapter_sha256="e"*64)
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(pipeline,"manifest",return_value={"documents":self.docs}), patch.object(
                    pipeline,"history",return_value=[first,last]):
                pipeline.build(Path(temp)/"records", Path(temp)/"site", Path(temp))
            summary = core.read_json(Path(temp)/"site/summary.json")
            self.assertEqual(summary["latest_attempted"]["run_id"],2)
            self.assertEqual(summary["last_complete"]["run_id"],1)
            page = (Path(temp)/"site/index.html").read_text()
            self.assertIn("Skia minus Canvas2D (points)", page)
            self.assertIn("Page-count equal/known docs", page)
            self.assertIn("Document and page details", page)
            self.assertIn("Reproduction and provenance", page)
            self.assertIn("89.1", page)

    def test_release_pagination_filters_and_orders_every_page(self):
        def release(i, **kwargs):
            return dict(id=i, published_at=f"2026-01-{i:02d}T00:00:00Z",
                        tag_name=f"v{i}", draft=False, prerelease=False, **kwargs)
        batches = [[release(3), dict(release(4), prerelease=True)],
                   [release(2), dict(release(1), draft=True)], []]
        with patch.object(pipeline, "api", side_effect=batches) as call:
            self.assertEqual([r["id"] for r in pipeline.stable_releases()], [2,3])
            self.assertEqual(call.call_args_list[-1].args[0], "releases?per_page=100&page=3")
    def test_backlog_does_not_skip_release_between_polls(self):
        def plan(tag, corpus, resolved=None):
            return {"source_ref":tag, "upstream_sha":resolved[0], "corpus_sha256":"c",
                    "font_sha256":"f","adapter_sha256":"a","protocol":"p"}
        releases = [{"tag_name":"v1"},{"tag_name":"v2"},{"tag_name":"v3"}]
        with patch.object(pipeline,"stable_releases",return_value=releases), patch.object(
                pipeline,"resolve_ref",side_effect=lambda tag:(tag+"sha","manual-tag")), patch.object(
                pipeline,"make_plan",side_effect=plan):
            prior = dict(plan("v1",None,("v1sha","stable-release")), status="complete")
            next_plan, needed = pipeline.choose_plan("",None,[prior])
            self.assertTrue(needed)
            self.assertEqual(next_plan["source_ref"],"v2")
            last_plan, needed = pipeline.choose_plan("",None,[prior,dict(next_plan,status="complete")])
            self.assertEqual(last_plan["source_ref"],"v3")
            _, needed = pipeline.choose_plan("",None,[prior,dict(next_plan,status="complete"),dict(last_plan,status="complete")])
            self.assertFalse(needed)
    def test_retagged_processed_release_is_pending(self):
        prior = {"source_ref":"v1","upstream_sha":"old","corpus_sha256":"c","font_sha256":"f",
                 "adapter_sha256":"a","protocol":"p"}
        with patch.object(pipeline,"stable_releases",return_value=[{"tag_name":"v1"}]), patch.object(
                pipeline,"resolve_ref",return_value=("new","manual-tag")), patch.object(
                pipeline,"make_plan",return_value=dict(prior,upstream_sha="new")):
            self.assertTrue(pipeline.choose_plan("",None,[prior])[1])
    def test_deployment_recovery_without_new_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            args = ["pipeline.py","publish","--reuse","--ledger",temp,"--out",temp+"/site"]
            with patch.object(sys,"argv",args), patch.object(pipeline,"ledger_repository") as ledger, patch.object(
                    pipeline,"build") as build:
                pipeline.main()
            ledger.assert_called_once_with(temp)
            build.assert_called_once()
            self.assertFalse((Path(temp)/"records").exists())
    def test_publish_job_does_not_depend_on_measurement_needed(self):
        source = (pipeline.ROOT/".github/workflows/fidelity.yml").read_text()
        publish = source.split("  publish:",1)[1]
        condition = next(l for l in publish.splitlines() if l.strip().startswith("if:"))
        self.assertNotIn("needed",condition)
        self.assertIn("publish --reuse",publish)
    def test_four_pair_manifest_is_metadata_only(self):
        catalog = core.manifest(pipeline.ROOT/"corpus",verify=False)
        self.assertEqual(len(catalog["documents"]),4)
        self.assertEqual(sum(d["pages"] for d in catalog["documents"]),4)
        for d in catalog["documents"]:
            self.assertIs(d["publication"]["raw_files"],False)
            self.assertTrue(d["document"]["source"].startswith("https://raw.githubusercontent.com/edwardkim/rhwp/"))

    def test_adapter_rejects_wrong_input_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            core.write_json(root/"silhouette_manifest.json", {"provenance":{
                "hwp":{"sha256":"x"*64},"pdf":{"sha256":"b"*64},"layout_generation":"2022",
                "raster_backend":"native-skia","comparison_profile":"print"}})
            core.write_json(root/"run_manifest.json", {"dpi":96})
            doc = {"document":{"sha256":"a"*64},"golden":{"sha256":"b"*64},"compat":"2022"}
            with self.assertRaises(ValueError):
                adapter.consume(root,doc,backend="native")

    def test_runtime_font_receipt_changes_environment_fingerprint(self):
        with patch.object(adapter,"inventory",return_value="a"*64):
            first = adapter.runtime_environment_digest(None,[{"font_supply":{"sha256":"b"*64}}])
            changed = adapter.runtime_environment_digest(None,[{"font_supply":{"sha256":"c"*64}}])
            self.assertNotEqual(first,changed)

class RetryPolicyTests(unittest.TestCase):
    def plan(self, tag, corpus=None, resolved=None):
        return {"source_ref":tag,"upstream_sha":tag+"sha","corpus_sha256":"c",
                "font_sha256":"f","adapter_sha256":"a","protocol":"p"}
    def choose(self, tags, past, ref=""):
        with patch.object(pipeline,"stable_releases",return_value=[{"tag_name":t} for t in tags]), patch.object(
                pipeline,"resolve_ref",side_effect=lambda tag:(tag+"sha","stable-release")), patch.object(
                pipeline,"make_plan",side_effect=self.plan):
            return pipeline.choose_plan(ref,None,past)
    def record(self, tag, status, time="2026-01-01T00:00:00Z"):
        return dict(self.plan(tag),status=status,resolved_at=time)

    def test_failed_and_partial_attempts_retry(self):
        for state in ("failed","partial"):
            self.assertTrue(self.choose(["v1"],[self.record("v1",state)])[1])

    def test_retry_cap_preserves_history_and_manual_override(self):
        past = [self.record("v1","failed") for _ in range(3)]
        before = copy.deepcopy(past)
        self.assertFalse(self.choose(["v1"],past)[1])
        self.assertEqual(past,before)
        self.assertTrue(self.choose(["v1"],past,ref="v1")[1])

    def test_new_release_precedes_retryable_old_failure(self):
        old = self.record("v1","failed")
        plan, needed = self.choose(["v1","v2"],[old])
        self.assertTrue(needed)
        self.assertEqual(plan["source_ref"],"v2")

    def test_retries_use_least_recent_attempt(self):
        first = self.record("v1","failed","2026-01-02T00:00:00Z")
        second = self.record("v2","partial","2026-01-01T00:00:00Z")
        self.assertEqual(self.choose(["v1","v2"],[second,first])[0]["source_ref"],"v2")
        retried = self.record("v2","failed","2026-01-03T00:00:00Z")
        self.assertEqual(self.choose(["v1","v2"],[second,first,retried])[0]["source_ref"],"v1")

    def test_complete_quality_alert_is_not_execution_retry(self):
        row = dict(self.record("v1","complete"),quality_alert=True)
        self.assertFalse(self.choose(["v1"],[row])[1])

class PagesVisibilityTests(unittest.TestCase):
    def test_delayed_visibility_retries_exact_id(self):
        batches = iter([[], [{"name":"github-pages","id":10,"expired":False}]])
        pauses = []
        wait_pages_artifact.wait(lambda:next(batches), 10, pause=pauses.append, attempts=2)
        self.assertEqual(pauses,[3])

    def test_wrong_expired_and_duplicate_artifacts_rejected(self):
        row = {"name":"github-pages","id":10,"expired":False}
        for artifacts in [[dict(row,id=11)], [dict(row,expired=True)], [row,row]]:
            self.assertFalse(wait_pages_artifact.ready(artifacts,10))

    def test_invisible_artifact_fails_before_deploy(self):
        with self.assertRaises(RuntimeError):
            wait_pages_artifact.wait(lambda:[],10,pause=lambda _:None,attempts=2)

if __name__ == "__main__":
    unittest.main()
