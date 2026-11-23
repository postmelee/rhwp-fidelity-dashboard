import base64
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from adapter import REQUIRED, probe
from core import canonical, digest, read_json, write_json
from stable_preflight import (
    CONTRACT, ENTRYPOINT, FILES, StablePreflight, build, inspect_commit, reports, validate,
)
from track_cohort import select_stable

ENGINE = "1" * 40
ROOT = "2" * 40
SCRIPTS = "3" * 40
SOURCE = "\n".join(repr(flag) for flag in sorted(REQUIRED)) + "\n"


def fixture(sha=ENGINE, missing=(), source=SOURCE, root=ROOT, scripts=SCRIPTS):
    data = source.encode()
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()
    return {
        f"git/commits/{sha}": {"sha": sha, "tree": {"sha": root}},
        f"git/trees/{root}": {"sha": root, "truncated": False, "tree": [
            {"path": "scripts", "type": "tree", "mode": "040000", "sha": scripts},
        ]},
        f"git/trees/{scripts}": {"sha": scripts, "truncated": False, "tree": [
            {"path": name, "type": "blob", "mode": "100644", "sha": blob}
            for name in sorted(FILES - set(missing))
        ]},
        f"git/blobs/{blob}": {"sha": blob, "size": len(data), "encoding": "base64",
                             "content": base64.b64encode(data).decode()},
    }


def error(status, headers=None, body=b""):
    return HTTPError("https://api.github.com", status, "test", headers or {}, io.BytesIO(body))


def report(items, contract=CONTRACT):
    return {"schema_version": 1, "run_id": 333, "attempt": 1, "producer_sha": "b" * 40,
            "contract_sha256": contract, "releases": items}


class PreflightTests(unittest.TestCase):
    def test_contract_checks_agree_with_local_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / "scripts"
            scripts.mkdir()
            for name in FILES:
                (scripts / name).write_text(SOURCE if name == ENTRYPOINT else "")
            self.assertEqual(probe(root), digest(SOURCE.encode()))
            for name in FILES:
                path = scripts / name
                source = path.read_text()
                path.unlink()
                with self.subTest(name=name), self.assertRaises((OSError, ValueError)):
                    probe(root)
                path.write_text(source)
        self.assertEqual(inspect_commit(fixture().__getitem__, "v0.9.1", ENGINE)["status"], "static_pass")

    def test_confirmed_missing_file_uses_only_matching_trees(self):
        api = fixture(missing=[ENTRYPOINT])
        del api[next(key for key in api if key.startswith("git/blobs/"))]
        row = inspect_commit(api.__getitem__, "v0.5.0", ENGINE)
        self.assertEqual((row["status"], row["missing_files"]), ("unsupported", [ENTRYPOINT]))
        api[f"git/trees/{SCRIPTS}"]["truncated"] = True
        row = inspect_commit(api.__getitem__, "v0.5.0", ENGINE)
        self.assertEqual((row["status"], row["missing_files"]), ("api_error", []))
        api[f"git/trees/{SCRIPTS}"].update(truncated=False, sha=ROOT)
        self.assertEqual(inspect_commit(api.__getitem__, "v0.5.0", ENGINE)["status"], "api_error")

    def test_missing_options_require_verified_parseable_blob(self):
        api = fixture(source=SOURCE.replace("'--dpi'\n", ""))
        row = inspect_commit(api.__getitem__, "v0.8.7", ENGINE)
        self.assertEqual((row["status"], row["missing_options"]), ("unsupported", ["--dpi"]))
        blob = next(key for key in api if key.startswith("git/blobs/"))
        api[blob]["content"] = base64.b64encode(b"a" * api[blob]["size"]).decode()
        row = inspect_commit(api.__getitem__, "v0.8.7", ENGINE)
        self.assertEqual((row["status"], row["missing_options"]), ("api_error", []))
        self.assertEqual(inspect_commit(fixture(source='"').__getitem__, "v0.8.7", ENGINE)["status"], "api_error")

    def test_classifies_transient_failures(self):
        cases = [
            (error(401), "authentication"),
            (error(403), "authentication"),
            (error(403, {"X-RateLimit-Remaining": "0"}), "rate_limited"),
            (error(403, {"Retry-After": "60"}), "rate_limited"),
            (error(403, body=b"Secondary rate limit"), "rate_limited"),
            (error(429), "rate_limited"),
            (error(404), "api_error"),
            (error(503), "api_error"),
            (URLError(TimeoutError()), "timeout"),
        ]
        for failure, expected in cases:
            def api(_):
                raise failure
            with self.subTest(expected=expected):
                row = inspect_commit(api, "v1", ENGINE)
                self.assertEqual(row["status"], expected)
                self.assertEqual((row["missing_files"], row["missing_options"]), ([], []))

    def test_stable_skips_confirmed_mismatch_and_keeps_latest_precedence(self):
        supported = "9" * 40
        latest = "a" * 40
        tags = {"v0.5.0": ENGINE, "v0.9.0": supported, "v0.9.1": latest}
        config = {"documents": []}
        stage = {"measurement": {"backends": {"native": {"status": "complete"}, "wasm": {"status": "complete"}}}}
        record = {"tag": "v0.9.1", "engine_sha": latest, "stages": {"pilot": stage, "expanded": stage},
                  "cohort_sha256": digest(canonical(dict(config, tag="v0.9.1", engine_sha=latest)))}
        def resolve(tag):
            return tags[tag], "stable-release"
        old = fixture(missing=[ENTRYPOINT])
        new = fixture(sha=supported, root="c" * 40, scripts="d" * 40)
        new[f"git/commits/{latest}"] = {"sha": latest, "tree": {"sha": "c" * 40}}
        preflight = StablePreflight((old | new).__getitem__, [])
        self.assertEqual(select_stable([record], list(tags), config, resolve, preflight), ("v0.9.0", supported))
        self.assertEqual([row["status"] for row in preflight.observations], ["unsupported", "static_pass"])
        fresh = StablePreflight((old | new).__getitem__, [])
        self.assertEqual(select_stable([], list(tags), config, resolve, fresh), ("v0.9.1", latest))
        self.assertEqual(len(fresh.observations), 1)

    def test_cache_is_for_contract_and_commit_transient_is_retried(self):
        old = inspect_commit(fixture(missing=[ENTRYPOINT]).__getitem__, "v0.5.0", ENGINE)
        transient = dict(old, tag="v0.9.1", status="timeout", engine_sha="c" * 40, missing_files=[])
        current = StablePreflight(fixture(sha="c" * 40).__getitem__, [report([old, transient])])
        self.assertFalse(current.allows("v0.5.0", ENGINE))
        self.assertEqual(current.observations, [])
        self.assertTrue(current.allows("v0.9.1", "c" * 40))
        fresh = StablePreflight(fixture().__getitem__, [report([old], contract="0" * 64)])
        self.assertTrue(fresh.allows("v0.5.0", ENGINE))
        self.assertFalse(current.allows("v0.5.0-alias", ENGINE))
        self.assertEqual(current.observations[-1], dict(old, tag="v0.5.0-alias"))

    def test_rate_limit_stops_more_ref_resolution(self):
        calls = []
        def resolve(tag):
            calls.append(tag)
            raise error(429)
        preflight = StablePreflight(self.fail, [])
        self.assertEqual(select_stable([], ["v0.5.0", "v0.9.0", "v0.9.1"], {}, resolve, preflight), ("", ""))
        self.assertEqual(calls, ["v0.9.1"])
        self.assertEqual(preflight.observations[0]["status"], "rate_limited")
        self.assertIsNone(preflight.observations[0]["engine_sha"])

    def test_report_and_site_expose_unsupported_without_a_score(self):
        missing = inspect_commit(fixture(missing=[ENTRYPOINT]).__getitem__, "v0.5.0", ENGINE)
        value = report([missing])
        self.assertEqual(validate(value, 333, 1, "b" * 40), value)
        with self.assertRaises(ValueError):
            validate(value, 334, 1, "b" * 40)
        with self.assertRaises(ValueError):
            validate(report([dict(missing, missing_files=[])]))
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            ledger = out / "compatibility"
            ledger.mkdir()
            write_json(ledger / "333-1.json", value)
            self.assertEqual(reports(ledger), [value])
            self.assertIn("stable-compatibility.html", build(ledger, out))
            self.assertIn("Unsupported by this producer", (out / "stable-compatibility.html").read_text())
            row = read_json(out / "stable-compatibility.json")["releases"][0]
            self.assertEqual(row["status"], "unsupported")
            self.assertNotIn("score", row)


if __name__ == "__main__":
    unittest.main()
