import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from receipt_cohort import verify_reference_aliases
from registered_print_queue import reviewed_print_note


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



class ReviewedPrintNotesTests(unittest.TestCase):
    def test_source_notes_are_scoped_to_their_registered_revision(self):
        registered = {"sample": "samples/a.hwp", "source_sha256": "a" * 64}
        original = {"registered": registered, "note": "old.json", "markers": ["old Print"],
                    "hancom": "2020", "compat": "2022"}
        reviewed = {"revision": "new", "entries": [
            dict(original, revision="old"),
            dict(original, note="new.json", markers=["new Print"], hancom="2024"),
        ]}
        read = Mock(side_effect=[b"old Print", b"new Print", b"changed"])
        with patch("registered_print_queue.read_json", return_value=reviewed):
            self.assertEqual(reviewed_print_note("old", registered, read)[:2], ("2020", "2022"))
            self.assertEqual(reviewed_print_note("new", registered, read)[:2], ("2024", "2022"))
            self.assertIsNone(reviewed_print_note("other", registered, read))
            self.assertIsNone(reviewed_print_note("new", dict(registered, source_sha256="b" * 64), read))
            with self.assertRaisesRegex(ValueError, "Reviewed Print details changed"):
                reviewed_print_note("new", registered, read)
        self.assertEqual(read.call_count, 3)
