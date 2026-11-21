"""Select one upstream revision and archive only this run's observed results."""
import argparse
import os
from pathlib import Path

from core import KEY, PROTOCOL, SHA, canonical, digest, match, read_json, write_json
from pipeline import api, ledger_repository, resolve_ref, stable_releases
from receipt_archive import STAGES, persist, validate_archive
from receipt_cohort import CONFIG, contract, measure


def select(previous, candidates, config):
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
        if not complete and len(records) < 3:
            return name, sha
    return "", ""


def plan(track):
    config, _ = contract()
    ledger = Path("ledger")
    ledger_repository(ledger)
    previous = [validate_archive(read_json(p)) for p in (ledger / "cohorts").glob("*.json")]
    if track == "devel":
        candidates = [("devel", api("commits/devel")["sha"])]
    else:
        candidates = ((r["tag_name"], resolve_ref(r["tag_name"])[0]) for r in stable_releases())
    tag, sha = select(previous, candidates, config)
    with open(os.environ["GITHUB_OUTPUT"], "a") as dst:
        print(f"tag={tag}\nsha={sha}", file=dst)
    print(f"{track} · {sha or 'no new target'}")


def archive(config):
    docs = [{**{k: d[k] for k in ("id", "pages", "source_sha256", "pdf_sha256")},
             "path_sha256": digest(d["input"].encode())} for d in config["documents"]]
    value = {"schema_version": 1, "docs": docs, "run_id": int(os.environ["GITHUB_RUN_ID"]),
             "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]), "producer_sha": os.environ["GITHUB_SHA"],
             "protocol": PROTOCOL, "cohort_sha256": digest(canonical(config)),
             **{k: config[k] for k in ("tag", "engine_sha", "corpus_sha", "receipt_sha256")}}
    value["stages"] = {s: read_json(Path("incoming") / (s + ".json")) for s in STAGES
                       if (Path("incoming") / (s + ".json")).is_file()}
    if os.environ["MEASURE_RESULT"] == "success" and set(value["stages"]) != set(STAGES):
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
