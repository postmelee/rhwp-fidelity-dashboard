"""Check interrupted numeric shard aggregation with the immutable published release record."""
import argparse
from collections import Counter
import copy
from pathlib import Path
import tempfile

from cohort_shards import completed, partitions, save
from core import BACKENDS, canonical, digest, read_json
from receipt_archive import validate_archive


def replay(ledger):
    record = validate_archive(read_json(ledger))
    checked = Counter()
    expected = {(d["id"], backend, page) for d in record["docs"] for backend in BACKENDS
                for page in range(1, d["pages"] + 1)}
    cached = executed = 0
    with tempfile.TemporaryDirectory() as temp:
        for name, stage in record["stages"].items():
            result = stage["measurement"]
            ids = {d["id"] for d in result["backends"]["native"]["documents"]}
            groups = list(partitions([d for d in record["docs"] if d["id"] in ids], 8))
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
                        assert completed(row, identity, group)
                        assert not completed(row, dict(identity, build="0" * 64), group)
                        for backend, data in row["measurement"]["backends"].items():
                            for d in data["documents"]:
                                checked.update((d["id"], backend, s["page"]) for s in d["scores"])
    assert set(checked) == expected and set(checked.values()) == {1} and cached > 0
    print(f"{executed} numeric shards, {cached} reused after interruption, {len(checked)} unique backend-pages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    replay(parser.parse_args().ledger)
