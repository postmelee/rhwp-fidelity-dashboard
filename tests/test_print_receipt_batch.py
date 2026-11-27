import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import write_json
import local_print_intake
from local_print_intake import audit_receipts, receipt_cases


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

    def test_audit_loads_both_modules_from_the_pinned_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            oracle = repo / "tools/oracle_public"
            oracle.mkdir(parents=True)
            auditor = oracle / "audit_print_pairs.py"
            resolver = oracle / "oracle_resolver.py"
            auditor.write_text("from . import oracle_resolver\n"
                               "def audit(repo, manifest, receipt):\n"
                               "    return {'pairs': [oracle_resolver.PROFILE]}\n"
                               "def index_receipts(document): return {}\n")
            resolver.write_text("PROFILE = 'inventory'\n")

            def git(*args):
                return subprocess.check_output(["git", "-C", repo, "-c", "user.name=Tester", "-c",
                                                "user.email=tester@example.invalid", *args], text=True).strip()

            git("init", "-q")
            git("add", ".")
            git("commit", "-qm", "inventory")
            inventory = git("rev-parse", "HEAD")
            resolver.write_text("PROFILE = 'driver'\n")
            git("commit", "-qam", "updated receipt contract")
            newer = git("rev-parse", "HEAD")
            git("checkout", "-q", inventory)
            auditor.write_text("raise AssertionError('worktree auditor loaded')")
            receipts = repo / "receipts.json"
            write_json(receipts, {"cases": []})
            for revision, expected in ((newer, "driver"), (inventory, "inventory"), (newer, "driver")):
                with patch.object(local_print_intake, "AUDITOR_REV", revision):
                    rows, conflicts, _ = audit_receipts(repo, receipts)
                    self.assertEqual(rows, [expected])
                    self.assertEqual(conflicts, set())
            with patch.object(local_print_intake, "AUDITOR_REV", "0" * 40):
                with self.assertRaisesRegex(ValueError, "Cannot read pinned receipt auditor"):
                    audit_receipts(repo, receipts)
