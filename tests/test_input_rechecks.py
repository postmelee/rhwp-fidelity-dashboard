import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import digest, verify_document_inputs


class InputRecheckTests(unittest.TestCase):
    def test_rechecks_current_document_golden_and_shared_fonts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def asset(name):
                (root / name).write_bytes(name.encode())
                return {"path": name, "sha256": digest(name.encode())}

            font = asset("font.ttf")
            first = {"document": asset("first.hwp"), "golden": asset("first.pdf"),
                     "font_environment": {"path": None}, "fonts": [font]}
            second = {"document": asset("second.hwp"), "golden": asset("second.pdf"),
                      "font_environment": asset("environment.json"), "fonts": [font]}
            (root / "second.pdf").write_bytes(b"changed")
            verify_document_inputs(root, first)
            with self.assertRaisesRegex(ValueError, "corpus hash mismatch"):
                verify_document_inputs(root, second)
            (root / "font.ttf").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "font hash mismatch"):
                verify_document_inputs(root, first)
