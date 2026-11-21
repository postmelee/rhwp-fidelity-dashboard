import hashlib
from collections import defaultdict
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oracle_queue import worklist


class WorklistTests(unittest.TestCase):
    def test_same_blob_keeps_separate_receipt_decisions(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            rows = []
            for path in ("first.hwp", "alias.hwp"):
                (repo / path).write_bytes(b"same bytes")
                rows.append({"path": path, "blob": "a" * 40, "oracle_state": "review_candidate",
                             "visual_deferrals": []})
            pairs = defaultdict(list, {r["path"]: [{"pdf": "one.pdf", "status": "candidate"}]
                                       for r in rows})
            result = worklist(repo, rows, pairs, [("first.hwp", "one.pdf")])
            self.assertEqual(result["unique_blobs"], 1)
            self.assertEqual(result["states"], {"verified": 1, "review_candidate": 1})
            self.assertEqual({r["source_sha256"] for r in result["tasks"]},
                             {hashlib.sha256(b"same bytes").hexdigest()})
            pairs["first.hwp"][0]["status"] = "mismatch"
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                worklist(repo, rows, pairs, [("first.hwp", "one.pdf")])
