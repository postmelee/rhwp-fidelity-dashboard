import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import read_json
import pipeline
from pr_evidence import import_archive
from pr_evidence_site import common_pages, render_diff, visual_sweep

CORPUS = pipeline.ROOT / "corpus"
EVIDENCE = CORPUS / "pr-evidence"


class PullRequestEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.ci = read_json(EVIDENCE / "render-diff-44925877031-1.json")
        self.sweep = read_json(EVIDENCE / "visual-sweep-9024.json")

    def test_artifact_digest_is_checked_before_parsing(self):
        with self.assertRaisesRegex(ValueError, "artifact SHA-256 mismatch"):
            import_archive(b"not the pinned ZIP", self.ci["origin"])

    def test_render_diff_uses_upstream_decisions_and_scope(self):
        _, body, summary = render_diff(self.ci, "record.json")
        self.assertEqual(summary["decisions"]["canvas"]["pass"], 3)
        self.assertEqual(summary["decisions"]["direct_pdf"]["pass"], 3)
        self.assertEqual(summary["decisions"]["browser_pdf"]["warning"], 4)
        self.assertEqual(summary["coverage"][3]["measured"], {"documents": 0, "pages": 0})
        self.assertTrue(all(r["page_count_mismatch_docs"] is None for r in summary["coverage"]))
        self.assertIn("Image size", body)
        self.assertIn("No Evidence", body)
        self.assertNotEqual(self.ci["origin"]["pr_head"], self.ci["origin"]["source_sha"])
        self.assertEqual(len(self.ci["build"]["browser_receipts"]), 18)
        self.assertIsNone(self.ci["build"]["executables"]["target/debug/rhwp"]["sha256"])

    def test_sweep_below_90_and_lowest_page_links(self):
        _, body, summary = visual_sweep(self.sweep, "record.json")
        self.assertEqual(summary["common_pages"], {"native": 763, "wasm": 763})
        for row in summary["raw"]:
            base = row["side"] == "base"
            self.assertEqual((row["below_90_documents"], row["below_90_pages"]), (1, 18) if base else (0, 0))
            self.assertIn(f'href="#{row["lowest"]["anchor"]}"', body)
            self.assertIn(f'id="{row["lowest"]["anchor"]}"', body)
        self.assertEqual(summary["raw"][0]["lowest"]["page"], 608)

    def test_deltas_use_only_measured_common_pages_under_the_same_conditions(self):
        base = copy.deepcopy(self.sweep["series"]["base"]["native"])
        head = copy.deepcopy(self.sweep["series"]["head"]["native"])
        base["scores"] = {"1": 89, "2": 0, "3": 90}
        head["scores"] = {"2": 90, "3": None, "4": 99}
        self.assertEqual(common_pages(base, head), {"2"})
        for key in head["conditions"]:
            with self.subTest(key=key):
                different = copy.deepcopy(head)
                different["conditions"][key] = None
                self.assertEqual(common_pages(base, different), set())
        head["counts"]["rhwp"] -= 1
        self.assertEqual(common_pages(base, head), set())

    def test_pr_scores_do_not_populate_a_release_even_when_source_shas_match(self):
        sha = self.sweep["series"]["head"]["native"]["source_sha"]
        output = {}
        with (
            patch.dict("os.environ", {"REFRESH_RELEASE": "1"}),
            patch.object(pipeline, "stable_releases", return_value=[{"tag_name": "v99.0.0"}]),
            patch.object(pipeline, "resolve_ref", return_value=(sha, "stable-release")),
            patch.object(Path, "mkdir"),
            patch.object(Path, "write_text", lambda path, data, **kwargs: output.update({path: data})),
            patch.object(Path, "write_bytes", lambda path, data: output.update({path: data})),
        ):
            out = Path("memory-output")
            pipeline.build(EVIDENCE / "empty-records", out, CORPUS)
        summary = json.loads(output[out / "summary.json"])
        self.assertIsNone(summary["last_complete"])
        self.assertIsNone(summary["latest_attempted"])
        self.assertEqual(summary["receipt_cohort_runs"], [])
        index = output[out / "index.html"]
        self.assertIn(f'value="release-{sha}">v99.0.0', index)
        overview = index.split('<section id="overview"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Unmeasured", overview)
        self.assertNotIn("96.34886", overview)
        for entry in summary["pr_evidence"]:
            self.assertIn(f'href="{entry["view"]}"', index)
            self.assertIn(out / entry["record"], output)
            self.assertIn(out / entry["view"], output)
        self.assertFalse(any(path.parent == out / "records" for path in output))


if __name__ == "__main__":
    unittest.main()
