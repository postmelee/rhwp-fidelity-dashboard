"""Validate bounded numeric results from the pinned producer and append them to data."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

from core import (BACKENDS, HASH, KEY, PROTOCOL, SHA, canonical, digest, exact, integer,
                  match, read_json, validate_measurement, write_json)
from pipeline import ROOT, git, ledger_repository
from receipt_cohort import contract

REPO = "postmelee/rhwp-fidelity-dashboard"
STAGES = ("pilot", "expanded")


def validate_stage(row, docs, stage, expected):
    exact(row, "stage run_id attempt producer_sha engine_sha cohort_sha256 protocol measurement artifacts")
    if row["stage"] != stage or any(row[k] != value for k, value in expected.items()):
        raise ValueError("Unexpected measurement identity")
    match(SHA, row["producer_sha"])
    validate_measurement(row["measurement"], docs)
    artifacts = row["artifacts"]
    scored = {backend + "/" + r["id"] for backend in BACKENDS
              for r in row["measurement"]["backends"][backend]["documents"] if r["scores"]}
    if not isinstance(artifacts, dict) or set(artifacts) != scored:
        raise ValueError("Page evidence coverage mismatch")
    for item in artifacts.values():
        exact(item, "run_manifest_sha256 export_sha256 tsv_sha256 font_supply_sha256")
        for key, value in item.items():
            if key != "font_supply_sha256" or value is not None:
                match(HASH, value)


def validate_archive(value):
    fields = "schema_version tag cohort_sha256 corpus_sha receipt_sha256 engine_sha docs run_id attempt producer_sha protocol stages"
    exact(value, fields + (" stage_sources" if value.get("schema_version") == 2 else ""))
    if value["schema_version"] not in (1, 2) or value["protocol"] != PROTOCOL:
        raise ValueError("Unsupported receipt report")
    match(KEY, value["tag"].replace(".", "-"))
    for key in ("cohort_sha256", "receipt_sha256"):
        match(HASH, value[key])
    for key in ("engine_sha", "corpus_sha", "producer_sha"):
        match(SHA, value[key])
    integer(value["run_id"], 10**16)
    integer(value["attempt"], 10**6)
    docs = value["docs"]
    if not isinstance(docs, list) or not 1 <= len(docs) <= 10000:
        raise ValueError("Invalid cohort size")
    for d in docs:
        exact(d, "id pages source_sha256 pdf_sha256 path_sha256")
        match(KEY, d["id"])
        if integer(d["pages"]) == 0:
            raise ValueError("Invalid reference page count")
        for k in ("source_sha256", "pdf_sha256", "path_sha256"):
            match(HASH, d[k])
    if len({d["id"] for d in docs}) != len(docs):
        raise ValueError("Duplicate cohort ID")
    if not isinstance(value["stages"], dict) or set(value["stages"]) - set(STAGES):
        raise ValueError("Unexpected cohort stage")
    expected = {k: value[k] for k in ("run_id", "attempt", "producer_sha", "engine_sha", "cohort_sha256", "protocol")}
    sources = value.get("stage_sources", {})
    if not isinstance(sources, dict) or set(sources) - set(value["stages"]):
        raise ValueError("Invalid release stage sources")
    for stage, row in value["stages"].items():
        producer = expected.copy()
        if stage in sources:
            source = sources[stage]
            exact(source, "run_id attempt tag producer_sha cohort_sha256 stage_sha256 scope_sha256")
            integer(source["run_id"], 10**16)
            integer(source["attempt"], 10**6)
            match(KEY, source["tag"].replace(".", "-"))
            match(SHA, source["producer_sha"])
            for k in ("cohort_sha256", "scope_sha256", "stage_sha256"):
                match(HASH, source[k])
            if source["stage_sha256"] != digest(canonical(row)):
                raise ValueError("Linked measurement digest mismatch")
            producer.update({k: source[k] for k in ("run_id", "attempt", "producer_sha", "cohort_sha256")})
        validate_stage(row, docs[:1] if stage == "pilot" else docs[1:], stage, producer)
    return value


def api(path, raw=False):
    response = subprocess.check_output(["gh", "api", "repos/" + REPO + "/" + path], timeout=90)
    return response if raw else json.loads(response)


def collect(request):
    config, _ = contract()
    run_id = integer(request["run_id"], 10**16)
    attempt = integer(request["attempt"], 10**6)
    run = api(f"actions/runs/{run_id}/attempts/{attempt}")
    if (run["status"] != "completed" or run["head_repository"]["full_name"] != REPO
            or run["path"] != ".github/workflows/receipt-cohort.yml"
            or run["head_sha"] != match(SHA, request["head_sha"])):
        raise ValueError("Incorrect producer run")
    docs = [{**{k: d[k] for k in ("id", "pages", "source_sha256", "pdf_sha256")},
             "path_sha256": digest(d["input"].encode())} for d in config["documents"]]
    value = {"schema_version": 1, "docs": docs, "run_id": run_id, "attempt": attempt,
             "producer_sha": match(SHA, request["producer_sha"]), "protocol": PROTOCOL,
             "cohort_sha256": digest(canonical(config)), "stages": {},
             **{k: config[k] for k in ("tag", "engine_sha", "corpus_sha", "receipt_sha256")}}
    artifacts = api(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    accepted_names = {f"receipt-cohort-numeric-{attempt}"}
    if run_id == 44766813207 and attempt == 1:
        accepted_names.add("receipt-cohort-numeric")
    matches = [a for a in artifacts if a["name"] in accepted_names and not a["expired"]]
    if len(matches) > 1 or any(a["size_in_bytes"] > 4_000_000 for a in matches):
        raise ValueError("Ambiguous or oversized numeric artifact")
    if not matches and run["conclusion"] == "success":
        raise ValueError("Missing completed measurement")
    if matches:
        item = matches[0]
        content = api(f'actions/artifacts/{integer(item["id"], 10**16)}/zip', raw=True)
        if item.get("digest") and item["digest"] != "sha256:" + digest(content):
            raise ValueError("Artifact digest mismatch")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for entry in archive.infolist():
                stage = entry.filename.removesuffix(".json")
                if entry.filename != stage + ".json" or stage not in STAGES or stage in value["stages"] or entry.file_size > 2_000_000:
                    raise ValueError("Invalid numeric archive member")
                value["stages"][stage] = json.loads(archive.read(entry))
    if run["conclusion"] == "success" and set(value["stages"]) != set(STAGES):
        raise ValueError("Missing successful run stage")
    return validate_archive(value)


def persist(value, folder):
    env = ledger_repository(folder, write=True)
    name = f'cohorts/{value["run_id"]}-{value["attempt"]}.json'
    target = folder / name
    if target.exists():
        if read_json(target) != value:
            raise ValueError("Immutable cohort record collision")
        return
    write_json(target, value)
    git(["add", "--", name], folder, env)
    git(["-c", "user.name=github-actions[bot]", "-c",
         "user.email=41898282+github-actions[bot]@users.noreply.github.com",
         "commit", "-m", "Record release Print cohort measurement"], folder, env)
    git(["push", "origin", "HEAD:refs/heads/data"], folder, env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    if args.request:
        request = read_json(args.request)
    else:
        event = read_json(os.environ["GITHUB_EVENT_PATH"])["workflow_run"]
        if event["head_branch"] != "main" or event["event"] != "workflow_dispatch":
            raise SystemExit("Only main manual measurements can be imported automatically")
        request = {"run_id": event["id"], "attempt": event["run_attempt"],
                   "head_sha": event["head_sha"], "producer_sha": event["head_sha"]}
    persist(collect(request), Path("ledger"))
