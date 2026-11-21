"""Select one upstream revision and archive only this run's observed results."""
import argparse
import os
from pathlib import Path

from core import KEY, PROTOCOL, SHA, canonical, digest, match, read_json, write_json
from pipeline import api, ledger_repository, resolve_ref, stable_releases
from receipt_archive import STAGES, persist, validate_archive
from receipt_cohort import CONFIG, contract, measure


def select(previous, candidates, config, retry_devel=False):
    attempts = {}
    for record in previous:
        key = (record["tag"], record["engine_sha"], record["cohort_sha256"])
        attempts.setdefault(key, []).append(record)
    for name, sha in candidates:
        match(KEY, name.replace(".", "-"))
        target = dict(config, tag=name, engine_sha=match(SHA, sha))
        records = attempts.get((name, sha, digest(canonical(target))), [])
        complete = any(
            set(record["stages"]) == set(STAGES)
            and all(backend["status"] == "complete"
                    for stage in record["stages"].values()
                    for backend in stage["measurement"]["backends"].values())
            for record in records
        )
        if name == "devel" and records and not retry_devel:
            continue
        if not complete and len(records) < 3:
            return name, sha
    return "", ""


def archive_docs(config):
    return [{**{k: d[k] for k in ("id", "pages", "source_sha256", "pdf_sha256")},
             "path_sha256": digest(d["input"].encode())} for d in config["documents"]]


def release_sources(config, previous, locks):
    # A reviewed target lock pins independent release expectations. Missing evidence
    # leaves the stage scheduled for a fresh measurement.
    links = {}
    if config["tag"] == "devel":
        return links
    by_run = {(r["run_id"], r["attempt"]): r for r in previous}
    for stage, lock in locks.get(config["tag"], {}).items():
        if stage not in STAGES:
            raise ValueError("Unknown release stage")
        prior = by_run.get((lock["run_id"], lock["attempt"]))
        if (not prior or stage not in prior["stages"] or stage in prior.get("stage_sources", {})
                or any(prior[k] != config[k] for k in ("engine_sha", "corpus_sha", "receipt_sha256"))
                or prior["cohort_sha256"] != digest(canonical(dict(config, tag=prior["tag"])))
                or prior["docs"] != archive_docs(config) or prior["protocol"] != PROTOCOL):
            continue
        value = prior["stages"][stage]
        data = value["measurement"]
        docs = prior["docs"][:1] if stage == "pilot" else prior["docs"][1:]
        if any(b["status"] != "complete" or any(d["pdf_pages"] != d["rendered_pages"] for d in b["documents"])
               for b in data["backends"].values()):
            continue
        fonts = {name: evidence["font_supply_sha256"] for name, evidence in value["artifacts"].items()}
        if not fonts or not all(fonts.values()):
            continue
        scope = {"docs": docs, "backends": sorted(data["backends"]), "profile": "print", "dpi": 96,
                 "protocol": PROTOCOL, "font_supply": fonts, "engine_sha": prior["engine_sha"],
                 "producer_sha": prior["producer_sha"], "corpus_sha": prior["corpus_sha"],
                 "receipt_sha256": prior["receipt_sha256"]}
        fingerprint = digest(canonical(scope))
        if (lock["build_sha256"] != data["build_sha256"] or lock["environment_sha256"] != data["environment_sha256"]
                or lock["scope_sha256"] != fingerprint or lock["stage_sha256"] != digest(canonical(value))):
            continue
        links[stage] = (value, {**{k: prior[k] for k in ("run_id", "attempt", "tag", "producer_sha", "cohort_sha256")},
                                "stage_sha256": lock["stage_sha256"], "scope_sha256": fingerprint})
    return links


def target_locks():
    path = CONFIG.with_name("release-stage-locks.json")
    return read_json(path) if path.is_file() else {}


def plan(track):
    config, _ = contract()
    ledger = Path("ledger")
    ledger_repository(ledger)
    previous = [validate_archive(read_json(p)) for p in (ledger / "cohorts").glob("*.json")]
    if track == "devel":
        candidates = [("devel", api("commits/devel")["sha"])]
    else:
        candidates = ((r["tag_name"], resolve_ref(r["tag_name"])[0]) for r in stable_releases())
    tag, sha = select(previous, candidates, config, os.environ.get("RETRY_DEVEL") == "true")
    links = release_sources(dict(config, tag=tag, engine_sha=sha), previous, target_locks()) if sha else {}
    with open(os.environ["GITHUB_OUTPUT"], "a") as dst:
        for stage in STAGES:
            print(f"measure_{stage}={str(stage not in links).lower()}", file=dst)
        print(f"tag={tag}\nsha={sha}", file=dst)
    print(f"{track} · {sha or 'no new target'}")


def archive(config):
    docs = archive_docs(config)
    value = {"schema_version": 1, "docs": docs, "run_id": int(os.environ["GITHUB_RUN_ID"]),
             "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]), "producer_sha": os.environ["GITHUB_SHA"],
             "protocol": PROTOCOL, "cohort_sha256": digest(canonical(config)),
             **{k: config[k] for k in ("tag", "engine_sha", "corpus_sha", "receipt_sha256")}}
    value["stages"] = {s: read_json(Path("incoming") / (s + ".json")) for s in STAGES
                       if (Path("incoming") / (s + ".json")).is_file()}
    if config["tag"] in target_locks():
        folder = Path("prior-ledger")
        ledger_repository(folder)
        previous = [validate_archive(read_json(p)) for p in (folder / "cohorts").glob("*.json")]
        links = release_sources(config, previous, target_locks())
        if links:
            value["schema_version"] = 2
            value["stage_sources"] = {}
        for stage, (record, source) in links.items():
            if stage in value["stages"]:
                raise ValueError("Both observed and linked results for one stage")
            value["stages"][stage] = record
            value["stage_sources"][stage] = source
    if os.environ["MEASURE_RESULT"] in ("success", "skipped") and set(value["stages"]) != set(STAGES):
        raise ValueError("Missing successful measurement")
    persist(validate_archive(value), Path("ledger"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "pilot", "expanded", "archive"))
    args = parser.parse_args()
    if args.command == "plan":
        plan(os.environ["TRACK"])
    else:
        config, _ = contract()
        config.update(engine_sha=match(SHA, os.environ["ENGINE_SHA"]), tag=os.environ["TRACK_TAG"])
        if args.command == "archive":
            archive(config)
        else:
            # This credential-free checkout is disposable. Preserve the measured plan in each stage digest.
            write_json(CONFIG, config)
            measure(Path("upstream").resolve(), Path("work").resolve(), args.command)
