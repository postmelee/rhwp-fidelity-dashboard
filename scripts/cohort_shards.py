"""Measure a fixed receipt cohort in document shards on one Linux runner."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile

import adapter
from core import PROTOCOL, canonical, digest, manifest, read_json, validate_measurement, write_json
from receipt_cohort import contract, verify_receipt


def partitions(documents, pages):
    if pages < 1 or len({d["id"] for d in documents}) != len(documents):
        raise ValueError("Invalid budget or duplicate document IDs")
    shard, count = [], 0
    for doc in sorted(documents, key=lambda item: item["id"]):
        if shard and count + doc["pages"] > pages:
            yield shard
            shard, count = [], 0
        shard.append(doc)
        count += doc["pages"]
    if shard:
        yield shard


def check_sources(repo, allow_generated=False):
    paths = subprocess.check_output(["git", "diff", "--name-only", "-z", "HEAD", "--"], cwd=repo)
    for raw in filter(None, paths.split(b"\0")):
        name = os.fsdecode(raw)
        generated = {"rhwp-studio/public/rhwp.js": "pkg/rhwp.js",
                     "rhwp-studio/public/rhwp_bg.wasm": "pkg/rhwp_bg.wasm"}
        if not allow_generated or name not in generated:
            raise ValueError("Unexpected tracked source change: " + name)
        mirror, original = repo / name, repo / generated[name]
        if (not mirror.is_file() or mirror.is_symlink() or not original.is_file()
                or original.is_symlink() or digest(mirror.read_bytes()) != digest(original.read_bytes())):
            raise ValueError("Generated Studio mirror differs from built package: " + name)


def save(path, value):
    # The driver holds an exclusive lock. A stopped writer leaves only an unconsumed temporary file.
    temporary = path.with_suffix(".tmp")
    write_json(temporary, value)
    os.replace(temporary, path)


def completed(saved, identity, docs):
    if not saved or identity is None or saved.get("identity") != identity:
        return False
    result = saved["measurement"]
    if digest(canonical(result)) != saved["measurement_sha256"]:
        raise ValueError("Damaged shard checkpoint")
    validate_measurement(result, docs)
    expected = {d["id"] for d in docs}
    return result["build_sha256"] == identity["build"] and all(
        backend["status"] == "complete" and {d["id"] for d in backend["documents"]} == expected
        for backend in result["backends"].values()
    )


def run(repo, folder, budget, limit, engine=None):
    import pypdfium2
    config, docs = contract()
    verify_receipt(config)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if sha != (engine or config["engine_sha"]):
        raise ValueError("Checkout must match the receipt cohort engine revision")
    # Checkpoints are local to a runner boot and an exact adapter/upstream contract.
    code = digest(canonical({f: digest(Path(__file__).with_name(f).read_bytes())
                             for f in ("adapter.py", "core.py", "receipt_cohort.py", "cohort_shards.py")}))
    boot = digest(Path("/proc/sys/kernel/random/boot_id").read_bytes())
    groups = list(partitions(docs, budget))
    plan = {"engine_sha": sha, "cohort_sha256": digest(canonical(config)), "protocol": PROTOCOL,
            "producer_sha256": code, "shards": [[d["id"] for d in g] for g in groups]}
    root = folder / digest(canonical(plan))
    root.mkdir(parents=True, exist_ok=True)
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        check_sources(repo, allow_generated=any(root.glob("shard-*.json")))
        write_json(root / "plan.json", plan)
        corpus = root / "corpus"
        adapter.materialize(corpus, docs)
        for doc in docs:
            with pypdfium2.PdfDocument(str(corpus / doc["golden"]["path"])) as pdf:
                if len(pdf) != doc["pages"]:
                    raise ValueError("Reference page count changed")
        env = adapter.inventory(corpus / "cache/fonts")
        state = ["pending"] * len(groups)
        executed = 0
        prepared = None
        for i, group in enumerate(groups):
            write_json(corpus / "manifest.json", {"schema_version": 1, "documents": group})
            manifest(corpus)
            checkpoint = root / f"shard-{i}.json"
            def identity():
                build = adapter.build_identity(repo)
                return {"build": build, "environment": env, "boot": boot,
                        "inputs": digest(canonical(group)), "plan": digest(canonical(plan))} if build else None
            if completed(read_json(checkpoint) if checkpoint.exists() else None, identity(), group):
                state[i] = "reused"
                prepared = adapter.build_identity(repo)
            elif limit is None or executed < limit:
                with tempfile.TemporaryDirectory(dir=root) as work:
                    check_sources(repo, allow_generated=prepared is not None or checkpoint.exists())
                    result = adapter.run(repo, corpus, Path(work) / "result.json", sha, prepared_build=prepared)
                    validate_measurement(result, group)
                    record = {"identity": identity(), "measurement": result,
                              "measurement_sha256": digest(canonical(result))}
                    save(checkpoint, record)
                    state[i] = "executed" if completed(record, record["identity"], group) else "incomplete"
                prepared = record["identity"]["build"] if state[i] == "executed" else None
                executed += 1
            save(root / "status.json", {"plan_sha256": digest(canonical(plan)), "shards": state})
        print(root, state)
        return all(s in ("reused", "executed") for s in state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--engine-sha", help="Exact target engine SHA (defaults to the cohort release)")
    parser.add_argument("--pages-per-shard", type=int, default=8)
    parser.add_argument("--max-new-shards", type=int)
    args = parser.parse_args()
    if args.max_new_shards is not None and args.max_new_shards < 0:
        parser.error("max-new-shards must be nonnegative")
    done = run(args.upstream.resolve(), args.work.resolve(), args.pages_per_shard, args.max_new_shards, args.engine_sha)
    raise SystemExit(0 if done else 2)
