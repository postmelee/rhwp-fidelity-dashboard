import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import write_json
from local_print_intake import receipt_cases


def index_receipts(receipt):
    return {(row["input"], row["pdf"]): row for row in receipt["cases"]}


class PrintReceiptBatchTests(unittest.TestCase):
    def test_conflicting_pair_only_postpones_its_source(self):
        one = {"input": "a.hwp", "pdf": "a.pdf", "output_hash": "one"}
        two = {"input": "b.hwp", "pdf": "b.pdf", "output_hash": "two"}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_json(folder / "1.json", {"cases": [one]})
            write_json(folder / "2.json", {"cases": [two]})
            write_json(folder / "3.json", {"cases": [one]})
            merged, conflicts, sha = receipt_cases(folder, index_receipts)
            self.assertEqual(merged["cases"], [one, two])
            self.assertEqual(conflicts, set())
            write_json(folder / "3.json", {"cases": [dict(one, output_hash="changed")]})
            merged, conflicts, changed_sha = receipt_cases(folder, index_receipts)
            self.assertEqual(merged["cases"], [two])
            self.assertEqual(conflicts, {"a.hwp"})
            self.assertNotEqual(sha, changed_sha)
