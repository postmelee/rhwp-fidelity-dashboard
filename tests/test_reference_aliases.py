import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from receipt_cohort import verify_reference_aliases


class PrintReferenceAliasTests(unittest.TestCase):
    def test_only_identical_input_and_print_recipe_can_share_reference(self):
        original = {"id": "registered-original", "input": "samples/source.hwp",
                    "source_sha256": "a" * 64, "pdf_sha256": "b" * 64, "pages": 2,
                    "compat": "2022", "reference_evidence": "tests/receipt.json"}
        alias = dict(original, id="alias-copy", input="mydocs/source.hwp",
                     reference_alias_of=original["id"])
        verify_reference_aliases({"documents": [original, alias]})
        for field, value in (("source_sha256", "0" * 64), ("pdf_sha256", "1" * 64),
                             ("compat", "2024"), ("pages", 3), ("input", "mydocs/other.hwp"),
                             ("reference_alias_of", "unregistered")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_reference_aliases({"documents": [original, dict(alias, **{field: value})]})
