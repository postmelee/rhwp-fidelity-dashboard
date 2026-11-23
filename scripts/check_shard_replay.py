"""Validate completed shards or replay interruption on an immutable numeric record."""
import argparse
from collections import Counter
import copy
from pathlib import Path
import tempfile

from cohort_shards import DEFAULT_PAGES_PER_SHARD, SCOPES, completed, make_plan, partitions, receipt_inputs, save
from core import BACKENDS, HASH, canonical, digest, exact, match, read_json
from receipt_archive import validate_archive


def page_keys(docs):
    return {(d["id"], backend, page) for d in docs for backend in BACKENDS
            for page in range(1, d["pages"] + 1)}


def coverage_keys(counter, result):
    for backend, data in result["backends"].items():
        for doc in data["documents"]:
            counter.update((doc["id"], backend, row["page"]) for row in doc["scores"])


def require_coverage(checked, docs):
    expected = page_keys(docs)
    if set(checked) != expected or any(count != 1 for count in checked.values()):
        raise ValueError("Shard output must contain every expected document/backend/page exactly once")


def check_work(work, config, docs, scope, engine, budget, expected_reused):
    plan, groups = make_plan(engine or config["engine_sha"], config, docs, budget, scope)
    plan_sha = digest(canonical(plan))
    root = work / plan_sha
    if read_json(root / "plan.json") != plan:
        raise ValueError("Saved shard plan differs from the requested receipt scope")
    status = read_json(root / "status.json")
    states = status["shards"]
    if (status["plan_sha256"] != plan_sha or len(states) != len(groups)
            or not set(states) <= {"executed", "reused"} or states.count("reused") != expected_reused):
        raise ValueError("Incomplete or unexpected shard restart status")
    checkout = exact(read_json(root / "checkout.json"), "engine_sha boot plan")
    if checkout["engine_sha"] != plan["engine_sha"] or checkout["plan"] != plan_sha:
        raise ValueError("Shard checkout does not match the run plan")
    boot = match(HASH, checkout["boot"])
    wanted = {f"shard-{i}.json" for i in range(len(groups))}
    if {path.name for path in root.glob("shard-*.json")} != wanted:
        raise ValueError("Missing or unexpected shard checkpoint")
    checked = Counter()
    build = environment = None
    for i, group in enumerate(groups):
        saved = exact(read_json(root / f"shard-{i}.json"), "identity measurement measurement_sha256")
        identity = exact(saved["identity"], "build environment boot inputs plan")
        if i == 0:
            build, environment = (match(HASH, identity[field]) for field in ("build", "environment"))
        expected = {"build": build, "environment": environment, "boot": boot,
                    "inputs": digest(canonical(group)), "plan": plan_sha}
        if not completed(saved, expected, group):
            raise ValueError(f"Incomplete shard or producer mismatch at shard {i}")
        coverage_keys(checked, saved["measurement"])
    require_coverage(checked, docs)
    print(f"{len(groups)} shards, {expected_reused} reused, {len(checked)} unique backend-pages")


def replay(ledger):
    record = validate_archive(read_json(ledger))
    checked = Counter()
    cached = executed = 0
    with tempfile.TemporaryDirectory() as temp:
        for name, stage in record["stages"].items():
            result = stage["measurement"]
            ids = {d["id"] for d in result["backends"]["native"]["documents"]}
            groups = list(partitions([d for d in record["docs"] if d["id"] in ids], DEFAULT_PAGES_PER_SHARD))
            for restart in (False, True):
                for i, group in enumerate(groups):
                    if not restart and i:
                        break
                    keys = {d["id"] for d in group}
                    out = Path(temp) / f"{name}-{i}.json"
                    identity = {"build": result["build_sha256"], "environment": result["environment_sha256"],
                                "inputs": digest(canonical(group))}
                    if completed(read_json(out) if out.exists() else None, identity, group):
                        cached += 1
                    else:
                        subset = copy.deepcopy(result)
                        for backend in subset["backends"].values():
                            backend["documents"] = [d for d in backend["documents"] if d["id"] in keys]
                        save(out, {"identity": identity, "measurement": subset, "measurement_sha256": digest(canonical(subset))})
                        executed += 1
                    if restart:
                        row = read_json(out)
                        if not completed(row, identity, group) or completed(row, dict(identity, build=None), group):
                            raise ValueError("Replay failed to enforce checkpoint identity")
                        coverage_keys(checked, row["measurement"])
    require_coverage(checked, record["docs"])
    if not cached:
        raise ValueError("Replay did not reuse a checkpoint")
    print(f"{executed} numeric shards, {cached} reused after interruption, {len(checked)} unique backend-pages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path, nargs="?")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--scope", choices=SCOPES, default="original")
    parser.add_argument("--engine-sha")
    parser.add_argument("--pages-per-shard", type=int, default=DEFAULT_PAGES_PER_SHARD)
    parser.add_argument("--expected-reused", type=int, default=1)
    args = parser.parse_args()
    if bool(args.ledger) == bool(args.work_dir):
        parser.error("specify an archived cohort or a work directory")
    if args.ledger:
        replay(args.ledger)
    else:
        config, docs = receipt_inputs(args.scope)
        check_work(args.work_dir, config, docs, args.scope, args.engine_sha,
                   args.pages_per_shard, args.expected_reused)
