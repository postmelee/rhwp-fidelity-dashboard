"""Classify the complete pinned inventory against upstream resolver and Print audits."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from corpus_inventory import ORACLE, RECEIPT, REV, inventory
from core import write_json


def classify(row, pairs, unmatched):
    states = {pair["status"] for pair in pairs}
    if "verified" in states:
        return "verified"
    if "mismatch" in states or "unavailable" in states:
        return "review_invalid_receipt"
    if "candidate" in states:
        return "review_candidate"
    if any("oracle" in rule["axes"] for rule in row["visual_deferrals"]):
        return "deferred_oracle"
    if row["path"] in unmatched:
        return "needs_print_review"
    return "outside_resolver_scope"


def main(repo, output):
    repo = repo.resolve()
    sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
    if sha != REV or subprocess.check_output(["git", "-C", repo, "status", "--porcelain"]):
        raise ValueError("A clean, complete pinned corpus checkout is required")
    sys.path.insert(0, str(repo / ORACLE))
    from audit_print_pairs import audit
    from oracle_resolver import build_manifest
    manifest = build_manifest(repo)
    audit_result = audit(repo, manifest, json.loads((repo / RECEIPT).read_bytes()))
    with tempfile.TemporaryDirectory() as temp:
        rows, summary = inventory(repo, Path(temp))
    pairs = defaultdict(list)
    for pair in audit_result["pairs"]:
        pairs[pair["sample"]].append(pair)
    unmatched = {entry["sample"] for entry in manifest["unmatched"]}
    items = []
    for row in rows:
        found = pairs[row["path"]]
        items.append({"path_sha256": hashlib.sha256(row["path"].encode()).hexdigest(),
                      "source_blob": row["blob"], "visual_deferrals": row["visual_deferrals"],
                      "resolver_scope": row["resolver_scope"],
                      "state": classify(row, found, unmatched),
                      "pairs": dict(Counter(p["status"] for p in found))})
    if len({i["path_sha256"] for i in items}) != summary["source_paths"]:
        raise ValueError("Inventory denominator mismatch")
    counts = dict(Counter(i["state"] for i in items))
    write_json(output, {"source_revision": REV, "receipt_sha256": summary["receipt_sha256"],
                        "paths": summary["source_paths"], "unique_blobs": summary["unique_blobs"],
                        "states": counts, "rows": items})
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.repo, args.output)
