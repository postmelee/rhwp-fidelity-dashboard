"""Classify the complete pinned inventory against upstream resolver and Print audits."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from corpus_inventory import classify, ORACLE, RECEIPT, REV, inventory
from core import write_json


def additional_receipts(repo, audit):
    paths = subprocess.check_output(["git", "-C", repo, "ls-tree", "-rz", "--name-only", REV]).split(b"\0")
    bundles, extra = [], set()
    for raw in sorted(paths):
        if not raw.lower().endswith(b".json") or b"receipt" not in raw.rsplit(b"/", 1)[-1].lower():
            continue
        name = raw.decode()
        if name == RECEIPT:
            continue
        path = repo / name
        if path.is_symlink() or path.stat().st_size > 4_000_000:
            continue
        data = path.read_bytes()
        try:
            doc = json.loads(data)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
            bundles.append({"path": name, "status": "different_schema"})
            continue
        try:
            checked = audit(repo, {"pairs": [], "unmatched": []}, doc)
        except ValueError:
            bundles.append({"path": name, "status": "unsupported_receipt"})
            continue
        for pair in checked["pairs"]:
            if pair["status"] == "verified":
                extra.add((pair["sample"], pair["pdf"]))
        bundles.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "counts": checked["statusCounts"]})
    return bundles, extra


def worklist(repo, rows, pairs, additional):
    """Attach the pinned bytes and upstream candidate paths to every review task."""
    def file_digest(path):
        # Git blob identity is shared by byte-identical paths.
        with (repo / path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    by_path = defaultdict(set)
    for source, pdf in additional:
        by_path[source].add(pdf)
    source_hashes = {}
    tasks = []
    for row in rows:
        path = row["path"]
        blob = row["blob"]
        if blob not in source_hashes:
            source_hashes[blob] = file_digest(path)
        candidates = {p["pdf"]: p["status"] for p in pairs[path]}
        for pdf in by_path[path]:
            if candidates.get(pdf) in {"mismatch", "unavailable"}:
                raise ValueError("Conflicting Print evidence for " + path)
            candidates[pdf] = "verified"
        tasks.append({"path": path, "source_blob": blob, "source_sha256": source_hashes[blob],
                      "oracle_state": "verified" if "verified" in candidates.values() else row["oracle_state"],
                      "visual_deferrals": row["visual_deferrals"],
                      "pdf_candidates": [{"path": pdf, "audit_status": status}
                                         for pdf, status in sorted(candidates.items())]})
    return {"revision": REV, "paths": len(tasks), "unique_blobs": len(source_hashes),
            "states": dict(Counter(task["oracle_state"] for task in tasks)), "tasks": tasks}


def main(repo, output, worklist_output=None):
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
        state = classify(row, found, unmatched)
        if state != row["oracle_state"]:
            raise ValueError("Path-only resolver projection differs from complete checkout")
        items.append({"path_sha256": hashlib.sha256(row["path"].encode()).hexdigest(),
                      "source_blob": row["blob"], "visual_deferrals": row["visual_deferrals"],
                      "resolver_scope": row["resolver_scope"],
                      "state": state,
                      "pairs": dict(Counter(p["status"] for p in found))})
    if len({i["path_sha256"] for i in items}) != summary["source_paths"]:
        raise ValueError("Inventory denominator mismatch")
    bundles, verified = additional_receipts(repo, audit)
    known = {(p["sample"], p["pdf"]) for p in audit_result["pairs"] if p["status"] == "verified"}
    extra = sorted(verified - known)
    print("Additional receipt discovery:", len(bundles), "files,", len(extra), "new verified pairs")
    counts = dict(Counter(i["state"] for i in items))
    write_json(output, {"source_revision": REV, "receipt_sha256": summary["receipt_sha256"],
                        "paths": summary["source_paths"], "unique_blobs": summary["unique_blobs"],
                        "additional_receipts": bundles, "additional_verified_pairs": extra,
                        "states": counts, "rows": items})
    if worklist_output:
        write_json(worklist_output, worklist(repo, rows, pairs, extra))
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--worklist", type=Path, help="Write a path-level Print review worklist")
    args = parser.parse_args()
    main(args.repo, args.output, args.worklist)
