import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import canonical, digest
from track_cohort import select


class TrackTests(unittest.TestCase):
    def test_latest_devel_and_separate_tag(self):
        sha = "a" * 40
        config = {"documents": []}
        stage = {"measurement": {"backends": {"native": {"status": "complete"}, "wasm": {"status": "complete"}}}}
        record = {"tag": "devel", "engine_sha": sha, "stages": {"pilot": stage, "expanded": stage},
                  "cohort_sha256": digest(canonical(dict(config, tag="devel", engine_sha=sha)))}
        self.assertEqual(select([record], [("devel", sha)], config), ("", ""))
        newest = "c" * 40
        self.assertEqual(select([record], [("devel", newest)], config), ("devel", newest))
        self.assertEqual(select([record], [("v1", sha)], config), ("v1", sha))
        partial = dict(record, stages={})
        self.assertEqual(select([partial], [("devel", sha)], config), ("", ""))
        self.assertEqual(select([partial], [("devel", sha)], config, retry_devel=True), ("devel", sha))
        self.assertEqual(select([partial] * 3, [("devel", sha)], config), ("", ""))
