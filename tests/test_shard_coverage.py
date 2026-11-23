from collections import Counter
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_shard_replay import check_work, page_keys, require_coverage
from cohort_shards import make_plan, receipt_inputs
from core import BACKENDS, canonical, digest, read_json, write_json


class ShardCoverageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.work = Path(folder.name)
        self.docs = [{"id": "one", "pages": 1}, {"id": "two", "pages": 2}]
        self.config = {"engine_sha": "1" * 40, "documents": self.docs}
        plan, groups = make_plan(self.config["engine_sha"], self.config, self.docs, 1, "tracked")
        self.plan_digest = digest(canonical(plan))
        self.root = self.work / self.plan_digest
        write_json(self.root / "plan.json", plan)
        boot = "b" * 64
        write_json(self.root / "checkout.json", {"boot": boot, "engine_sha": plan["engine_sha"],
                                                 "plan": self.plan_digest})
        write_json(self.root / "status.json", {"plan_sha256": self.plan_digest, "shards": ["reused", "executed"]})
        for i, group in enumerate(groups):
            build = "a" * 64
            measured = [{"id": d["id"], "status": "complete", "pdf_pages": d["pages"], "rendered_pages": d["pages"],
                         "scores": [{"page": p, "raw": 100} for p in range(1, d["pages"] + 1)]}
                        for d in group]
            backend = {"status": "complete", "exit_code": 0, "quality_alert": False, "documents": measured}
            result = {"schema_version": 1, "environment_sha256": "c" * 64, "build_sha256": build,
                      "backends": {b: copy.deepcopy(backend) for b in BACKENDS}}
            identity = {"build": build, "environment": "d" * 64, "boot": boot,
                        "plan": self.plan_digest, "inputs": digest(canonical(group))}
            write_json(self.root / f"shard-{i}.json", {"identity": identity, "measurement": result,
                                                       "measurement_sha256": digest(canonical(result))})

    def check(self):
        check_work(self.work, self.config, self.docs, "tracked", None, 1, 1)

    def test_original_and_tracked_scope_use_the_same_original_document_contract(self):
        _, original = receipt_inputs("original")
        _, tracked = receipt_inputs("tracked")
        self.assertEqual(tracked[:len(original)], original)
        self.assertGreater(len(tracked), len(original))
        self.assertEqual(len({d["id"] for d in tracked}), len(tracked))

    def test_current_manifest_and_expected_resume_validate(self):
        self.check()
        write_json(self.root / "status.json", {"plan_sha256": self.plan_digest, "shards": ["executed", "executed"]})
        with self.assertRaisesRegex(ValueError, "restart status"):
            self.check()

    def test_equal_total_with_wrong_backend_page_is_rejected(self):
        path = self.root / "shard-1.json"
        saved = read_json(path)
        saved["measurement"]["backends"]["native"]["documents"][0]["scores"][1]["page"] = 1
        saved["measurement_sha256"] = digest(canonical(saved["measurement"]))
        write_json(path, saved)
        with self.assertRaisesRegex(ValueError, "duplicate/out-of-range page"):
            self.check()

    def test_checkpoint_from_other_environment_is_rejected(self):
        path = self.root / "shard-1.json"
        saved = read_json(path)
        saved["identity"]["environment"] = "e" * 64
        write_json(path, saved)
        with self.assertRaisesRegex(ValueError, "producer mismatch"):
            self.check()

    def test_unexpected_checkpoint_is_rejected(self):
        write_json(self.root / "shard-2.json", {})
        with self.assertRaisesRegex(ValueError, "unexpected shard checkpoint"):
            self.check()

    def test_equal_total_with_an_extra_and_missing_key_is_rejected(self):
        keys = Counter(page_keys(self.docs))
        del keys[("one", "native", 1)]
        keys[("two", "native", 1)] += 1
        self.assertEqual(sum(keys.values()), 6)
        with self.assertRaisesRegex(ValueError, "every expected"):
            require_coverage(keys, self.docs)
