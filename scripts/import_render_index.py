"""Verify an indexed upstream PR Render Diff and export its measured first-page tracks."""
import argparse
import io
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
from zipfile import ZipFile

from core import HASH, SHA, digest, match, write_json
from pr_evidence import BUILD, MEMBER, RESULTS, import_archive

REPO = "edwardkim/rhwp"


def api(path, binary=False):
    data = subprocess.check_output(["gh", "api", f"repos/{REPO}/{path}"])
    return data if binary else json.loads(data)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def artifact(rows, name, run, job):
    found = [r for r in rows if r["name"] == name and not r["expired"]
             and r["workflow_run"]["id"] == run and job["started_at"] <= r["created_at"] <= job["completed_at"]]
    require(len(found) == 1, "Expected exactly one artifact from this producer interval: " + name)
    item = found[0]
    require(0 < item["size_in_bytes"] <= 64_000_000, "Archive exceeds import budget")
    checksum = match(HASH, item["digest"].removeprefix("sha256:"))
    data = api(f"actions/artifacts/{item['id']}/zip", binary=True)
    require(digest(data) == checksum, "Downloaded archive digest differs")
    return item, data


def member(bundle, path):
    match(MEMBER, path)
    entry = bundle.getinfo(path)
    require(entry.file_size <= 32_000_000, "Member exceeds import budget")
    return bundle.read(entry)


def collect(run, attempt, pr):
    route = f"actions/runs/{run}/attempts/{attempt}"
    meta = api(route)
    require(meta["event"] == "pull_request" and meta["repository"]["full_name"] == REPO
            and meta["path"] == ".github/workflows/render-diff.yml" and meta["id"] == run
            and meta["run_attempt"] == attempt and meta["status"] == "completed", "Wrong workflow attempt")
    jobs = [j for j in api(route + "/jobs?per_page=100")["jobs"] if j["name"] == "Canvas visual diff"]
    require(len(jobs) == 1, "Expected one Canvas visual diff job")
    job = jobs[0]
    require(job["run_id"] == run and job["run_attempt"] == attempt and job["conclusion"] == "success",
            "Producer job did not complete successfully")
    steps = {s["name"] for s in job["steps"] if s["conclusion"] == "success"}
    require({"Upload render diff artifacts", "Upload render diff index"} <= steps, "Missing producer upload")
    origin_step = f"Render Diff identity PR #{pr} base "
    bases = [s[len(origin_step):] for s in steps if s.startswith(origin_step)]
    require(len(bases) == 1, "Missing PR identity from producer job")
    base = match(SHA, bases[0])
    listed = api(f"actions/runs/{run}/artifacts?per_page=100")
    require(listed["total_count"] <= 100, "Incomplete artifact listing")
    idx, index_zip = artifact(listed["artifacts"], f"render-diff-index-{run}-{attempt}", run, job)
    prod, archive = artifact(listed["artifacts"], "render-diff-artifacts", run, job)
    with ZipFile(io.BytesIO(index_zip)) as small, ZipFile(io.BytesIO(archive)) as full:
        require(small.namelist() == ["evidence.json"] and len(full.namelist()) == len(set(full.namelist())),
                "Unexpected archive layout")
        raw = member(small, "evidence.json")
        require(raw == member(full, BUILD + "evidence.json"), "Published index differs from producer archive")
        index = json.loads(raw)
        head = match(SHA, meta["head_sha"])
        tested = match(SHA, index["tested_sha"])
        require((index["schema_version"], index["run_id"], index["run_attempt"], index["pr_head"]) ==
                (1, run, attempt, head), "Index run or source identity differs")
        commit = api("git/commits/" + tested)
        require(tested == head or [p["sha"] for p in commit["parents"]] == [base, head],
                "Tested source differs from PR identity")
        for path, checksum in index["files"].items():
            require(digest(member(full, path)) == match(HASH, checksum), "Indexed digest differs: " + path)
        build = json.loads(member(full, BUILD + "build.json"))
        require(index["build"] == build, "Index build record differs")
        native_path = BUILD + "native-build.txt"
        native = dict(line.split(maxsplit=1) for line in member(full, native_path).decode().splitlines())
        native_sha = match(HASH, native["sha256"].split()[0])
        require(native["source_sha"] == tested and index["native_build"] ==
                {"source_sha": tested, "sha256": native_sha}, "Native build receipt differs")
        fixtures = set()
        for file in ("results.json", "pdf-results.json"):
            fixtures.update(json.loads(member(full, RESULTS + file))["config"]["fixtures"])
        blobs = {}
        root = "rhwp-studio/public/samples"
        for fixture in sorted(fixtures):
            match(MEMBER, fixture)
            path = root + "/" + fixture
            item = api("contents/" + quote(path) + "?ref=" + tested)
            require(item["type"] == "file" and item["path"] == path, "Fixture is missing from tested tree")
            blobs[fixture] = match(SHA, item["sha"])
    origin = {"run_id": run, "attempt": attempt, "job_id": job["id"], "repository": REPO,
              "pr": pr, "pr_base": base, "pr_head": head, "source_sha": tested,
              "source_tree_sha": commit["tree"]["sha"], "fixture_root": root, "fixture_blobs": blobs,
              "artifact_id": prod["id"], "artifact_name": prod["name"], "artifact_sha256": digest(archive),
              "index_artifact_id": idx["id"], "index_sha256": digest(raw), "measured_at": job["completed_at"]}
    pull = api(f"pulls/{pr}")
    if pull.get("merged") and pull["head"]["sha"] == head:
        merged = match(SHA, pull["merge_commit_sha"])
        origin["merge_sha"] = merged
        origin["merge_tree_sha"] = match(SHA, api("git/commits/" + merged)["tree"]["sha"])
    report = import_archive(archive, origin)
    report["build"]["executables"]["target/debug/rhwp"].update(sha256=native_sha, source=native_path)
    for track, key in (("canvas", "canvas"), ("browser_pdf", "browser"), ("direct_pdf", "direct")):
        rows = report["tracks"][track]["pages"]
        expected = sorted((r["fixture"], r["page"]) for r in rows if r["status"] not in {"unmeasured", "error"})
        supplied = sorted(tuple(p) for p in index["comparisons"][key]["pages"])
        require(expected == supplied, "Index page scope differs from results: " + key)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "attempt", "pr"):
        parser.add_argument(name, type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_json(args.output, collect(args.run, args.attempt, args.pr))
