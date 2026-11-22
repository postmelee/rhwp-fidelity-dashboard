import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import canonical, digest
from track_cohort import PROTOCOL, archive_docs, release_sources, select, select_stable


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
        stable = dict(partial, tag="v1", cohort_sha256=digest(canonical(dict(config, tag="v1", engine_sha=sha))))
        self.assertEqual(select([stable], [("v1", sha), ("v2", newest)], config), ("v2", newest))
        self.assertEqual(select([partial] * 3, [("devel", sha)], config), ("", ""))

    def test_current_stable_precedes_old_unmeasured_tags(self):
        tags = ["v0.5.0", "v0.9.1"]
        sha = "a" * 40
        config = {"documents": []}
        hint = {"tag": tags[-1], "engine_sha": sha, "stages": {},
                "cohort_sha256": digest(canonical(dict(config, tag=tags[-1], engine_sha=sha)))}
        seen = []
        def resolve(tag):
            seen.append(tag)
            return (sha if tag == tags[-1] else "b" * 40), "stable-release"
        self.assertEqual(select_stable([], tags, config, resolve), (tags[-1], sha))
        self.assertEqual(select_stable([hint], tags, config, resolve), (tags[-1], sha))
        self.assertEqual(seen, [tags[-1], tags[-1]])
        self.assertEqual(select_stable([hint] * 3, tags, config, resolve), (tags[0], "b" * 40))

    def test_release_reuses_only_a_locked_stage(self):
        config = {"tag": "v1", "engine_sha": "a" * 40, "corpus_sha": "b" * 40,
                  "receipt_sha256": "c" * 64,
                  "documents": [{"id": "one", "pages": 2, "input": "samples/one.hwp",
                                 "source_sha256": "1" * 64, "pdf_sha256": "2" * 64}]}
        docs = archive_docs(config)
        fonts = {"native/one": "3" * 64, "wasm/one": "4" * 64}
        backend = {"status": "complete", "documents": [{"pdf_pages": 2, "rendered_pages": 2}]}
        stage = {"measurement": {"backends": {"native": backend, "wasm": backend},
                                 "build_sha256": "5" * 64, "environment_sha256": "6" * 64},
                 "artifacts": {k: {"font_supply_sha256": v} for k, v in fonts.items()}}
        src = {**config, "tag": "devel", "docs": docs, "run_id": 7, "attempt": 1,
               "producer_sha": "d" * 40, "protocol": PROTOCOL, "stages": {"pilot": stage},
               "cohort_sha256": digest(canonical(dict(config, tag="devel")))}
        scope = {"docs": docs, "backends": ["native", "wasm"], "profile": "print", "dpi": 96,
                 "protocol": PROTOCOL, "font_supply": fonts,
                 **{k: src[k] for k in ("engine_sha", "producer_sha", "corpus_sha", "receipt_sha256")}}
        lock = {"run_id": 7, "attempt": 1, "scope_sha256": digest(canonical(scope)),
                "stage_sha256": digest(canonical(stage)), "build_sha256": "5" * 64,
                "environment_sha256": "6" * 64}
        def resolve(change=None, target=None):
            return release_sources(target or config, [src], {"v1": {"pilot": dict(lock, **(change or {}))}})
        value, origin = resolve()["pilot"]
        self.assertEqual(value, stage)
        self.assertEqual((origin["tag"], origin["run_id"], origin["attempt"]), ("devel", 7, 1))
        self.assertEqual(release_sources(config, [src], {}), {})
        for field in ("scope_sha256", "stage_sha256", "build_sha256", "environment_sha256", "attempt"):
            with self.subTest(field=field):
                self.assertEqual(resolve({field: 0}), {})
        self.assertEqual(resolve(target=dict(config, engine_sha="f" * 40)), {})
        self.assertEqual(resolve(target=dict(config, documents=[dict(config["documents"][0], pages=1)])), {})
        stage["artifacts"]["native/one"]["font_supply_sha256"] = None
        self.assertEqual(resolve(), {})
