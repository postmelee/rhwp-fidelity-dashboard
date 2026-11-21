"""Revalidate the devel Studio renderer artifact for one fixed run attempt."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from urllib.parse import quote
from urllib.request import urlopen
from zipfile import ZipFile

REPO = "edwardkim/rhwp"
RUN = 44270213909
JOB = 134684787521
ATTEMPT = 1
SHA = "08b38c12a75fa5cabfe5fbbfde9388aceb3fcca3"
TREE = "fd066bb4f6db75e02176ed5e5e2f98372f0c895d"
ARTIFACT = 14414315436
DIGEST = "53f1713bac59e465e70b3463fa0ca379ce9409c6a43e65c5afc0ee16b53700d5"
PREFIX = "output/frontend-canvas-gates/canvaskit-readiness/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(path, binary=False):
    data = subprocess.check_output(["gh", "api", f"repos/{REPO}/{path}"], timeout=120)
    return data if binary else json.loads(data)


def source(path):
    with urlopen(f"https://raw.githubusercontent.com/{REPO}/{SHA}/" + quote(path), timeout=40) as response:
        return response.read()


def main():
    run = api(f"actions/runs/{RUN}/attempts/{ATTEMPT}")
    assert (run["event"], run["head_branch"], run["head_sha"], run["path"], run["conclusion"]) == (
        "workflow_dispatch", "devel", SHA, ".github/workflows/ci.yml", "success")
    assert api("git/commits/" + SHA)["tree"]["sha"] == TREE
    job = api(f"actions/jobs/{JOB}")
    assert (job["run_id"], job["run_attempt"], job["name"], job["conclusion"]) == (
        RUN, ATTEMPT, "Frontend package gates", "success")
    upload, = [s for s in job["steps"] if s["name"] == "Upload frontend Canvas evidence"]
    artifact = api(f"actions/artifacts/{ARTIFACT}")
    assert artifact["workflow_run"]["id"] == RUN and artifact["name"] == "frontend-canvas-evidence"
    assert upload["conclusion"] == "success" and upload["started_at"] <= artifact["created_at"] <= upload["completed_at"]
    assert artifact["digest"] == "sha256:" + DIGEST
    data = api(f"actions/artifacts/{ARTIFACT}/zip", binary=True)
    assert sha(data) == DIGEST
    with ZipFile(io.BytesIO(data)) as files:
        build = json.loads(files.read("output/frontend-canvas-build/build.json"))
        gates = json.loads(files.read("output/frontend-canvas-gates/result.json"))
        assert build["source_sha"] == gates["source_sha"] == SHA and build["source_dirty"] is False
        assert build["success"] and gates["success"] and gates["artifacts"] == build["artifacts"]
        assert "renderer-baseline.mjs" in gates["checks"]
        report = json.loads(files.read(PREFIX + "browser-baseline-report.json"))
        samples = {s["id"]: s for s in json.loads(source("scripts/renderer_baseline_manifest.json"))["samples"]
                   if s.get("canvaskitReadinessGate")}
        expected = {(key, s["page"], b) for key, s in samples.items() for b in ("canvas2d", "canvaskit-default")}
        inputs = {key: source("samples/" + s["file"]) for key, s in samples.items()}
        hashes = {key: "sha256:" + sha(data) for key, data in inputs.items()}
        blobs = {key: hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                 for key, data in inputs.items()}
        seen = set()
        rows = []
        for row in report["results"]:
            key = row["sampleId"], row["page"], row["backend"]
            assert key in expected and key not in seen
            seen.add(key)
            identity = row["comparisonIdentity"]
            assert hashes[key[0]] == row["documentDigest"] == identity["documentDigest"]
            assert identity["page"] == key[1] and identity["sampleId"] == key[0]
            assert row["profile"] == row["actualProfile"] == identity["profile"] == "screen"
            assert row["actualBackend"] == identity["backend"] and identity["surface"]
            if row["actualBackend"] != key[2]:
                assert row["fontFallback"]
            png = files.read(PREFIX + key[0] + "/" + PurePosixPath(row["path"]).name)
            assert sha(png) == row["artifact"]["sha256"] and len(png) == row["artifact"]["sizeBytes"]
            rows.append({k: row[k] for k in ("comparisonIdentity", "backend", "fontFallback", "timings")})
        assert seen == expected
        gate = report["canvaskitReadinessGate"]
        checks = {r["sampleId"]: r for r in gate["checks"]}
        assert len(checks) == len(gate["checks"]) and set(checks) == set(samples)
        evidence = {
            "run": RUN, "attempt": ATTEMPT, "job": JOB, "tree": TREE, "source_sha": SHA,
            "archive_sha256": DIGEST, "build": build["artifacts"], "studio_checks": gates["checks"],
            "browser": report["browserVersion"], "summary": gate["summary"], "rows": rows,
            "input_blobs": blobs,
            "readiness": [{k: r[k] for k in ("sampleId", "passed", "blockers", "activeBackend",
                "backendFallbackReason", "surfaceBackend", "surfaceFallbackReason", "performanceBudget")}
                for r in checks.values()]
        }
        snapshot = Path(__file__).with_name("site") / "studio-screen.json"
        if evidence != json.loads(snapshot.read_bytes()):
            raise ValueError("Published browser evidence differs from the verified producer")
        # Rebuild the candidate projection with the fixed corpus tree, independent of Pages.
        from preview_presentation import transition_scope
        from corpus_inventory import ROOTS, REV
        root_tree = api("git/trees/" + REV)
        def entries(parts):
            tree = root_tree
            for part in parts:
                entry, = [e for e in tree["tree"] if e["path"] == part]
                tree = api("git/trees/" + entry["sha"] + ("?recursive=1" if part == parts[-1] else ""))
                assert not tree.get("truncated")
            return tree["tree"]
        paths = []
        for root in ROOTS:
            for entry in entries(root.split("/")):
                if entry["type"] != "blob" or not entry["path"].lower().endswith((".hwp", ".hwpx")):
                    continue
                path = root + "/" + entry["path"]
                paths.append({"path_sha256": sha(path.encode()), "blob": entry["sha"], "receipt_verified": False})
        assert len(paths) == len({r["path_sha256"] for r in paths}) == 3800
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "corpus-index.json").write_text(json.dumps({"source_revision": REV, "rows": paths}))
            transition_scope(folder, evidence)
            indexed = json.loads((folder / "canvaskit-scope.json").read_bytes())["rows"]
            assert len(indexed) == len(paths) and all(r["blockers"] for r in indexed)
            assert {r["blob"] for r in indexed if r["screen"]} == set(blobs.values())
            print("CANDIDATE_SCOPE", len(indexed), "paths,", sum(bool(r["screen"]) for r in indexed), "matching paths")
        print("BROWSER_EVIDENCE " + json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
