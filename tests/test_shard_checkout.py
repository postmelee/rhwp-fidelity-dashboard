import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cohort_shards import check_sources


class GeneratedStudioOutputs(unittest.TestCase):
    def test_resume_accepts_only_identical_mirrors(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            mirror = repo / "rhwp-studio/public/rhwp.js"
            product = repo / "pkg/rhwp.js"
            mirror.parent.mkdir(parents=True)
            product.parent.mkdir()
            mirror.write_bytes(b"published")
            source = repo / "source"
            source.write_bytes(b"engine")
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "add", "rhwp-studio", "source"], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.org",
                            "commit", "-qm", "fixture"], cwd=repo, check=True)
            check_sources(repo)
            mirror.write_bytes(b"built")
            with self.assertRaises(ValueError):
                check_sources(repo)
            product.write_bytes(b"built")
            check_sources(repo, allow_generated=True)
            mirror.write_bytes(b"different")
            with self.assertRaises(ValueError):
                check_sources(repo, allow_generated=True)
            mirror.write_bytes(b"built")
            source.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                check_sources(repo, allow_generated=True)
