"""Enumerate a pinned Git tree and audit a named Hancom Print receipt set."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

REV = "2f4f60fbffa1cbed1d7baa8b6d36f40f0940dee0"
ROOTS = ("samples", "tests/fixtures", "mydocs/pr/assets", "pdf")
RECEIPT = "mydocs/pr/assets/hyunmyungjanelee_20261112/mcp-print-reference/receipts.json"
FIXTURES = "tests/fixtures/"
SCOPE = "scripts/regression_document_scope.py"
ORACLE = "tools/oracle_public/"
SOURCE_FILES = (
    FIXTURES + "transferred_exam_regressions.txt", FIXTURES + "deferred_document_regressions.txt",
    SCOPE, ORACLE + "audit_print_pairs.py", ORACLE + "oracle_resolver.py",
    FIXTURES + "deferred_regression_documents.txt",
    FIXTURES + "deferred_visual_regression_inputs.tsv",
)
DASHBOARD = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def blob(repo, path):
    return git(repo, "show", REV + ":" + path)


def sources(repo):
    files = {}
    entries = git(repo, "ls-tree", "-rz", REV, "--", *ROOTS)
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = raw_path.decode("utf-8")
        if kind == "blob" and PurePosixPath(path).suffix.lower() in {".hwp", ".hwpx"}:
            files[path] = (oid, mode)
    return files


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


def resolver_names(repo, scratch, files):
    # This pinned resolver discovers candidates using paths alone. The audit below
    # reads the original Git bytes for every path named in a Print receipt.
    from oracle_resolver import build_manifest
    paths = [p for p in files if p.startswith("samples/")]
    paths.extend(p.decode() for p in git(repo, "ls-tree", "-rz", "--name-only", REV, "--", "pdf").split(b"\0")
                 if p.lower().endswith(b".pdf"))
    for name in paths:
        path = scratch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
    return build_manifest(scratch)


def inventory(repo, scratch):
    files = sources(repo)
    receipt_bytes = blob(repo, RECEIPT)
    receipts = json.loads(receipt_bytes)
    for name in SOURCE_FILES:
        dest = scratch / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob(repo, name))
    sys.path[:0] = [str(scratch / "scripts"), str(scratch / ORACLE)]
    import audit_print_pairs
    from regression_document_scope import is_deferred_regression_input

    # Only hydrate the exact receipt inputs. The upstream audit hashes their bytes.
    pairs = audit_print_pairs.index_receipts(receipts)
    for name in sorted({name for pair in pairs for name in pair}):
        dest = scratch / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as output:
            subprocess.run(["git", "-C", str(repo), "show", REV + ":" + name],
                           stdout=output, check=True)
    audited = audit_print_pairs.audit(scratch, {"pairs": [], "unmatched": []}, receipts)
    by_source = defaultdict(list)
    for pair in audited["pairs"]:
        by_source[pair["sample"]].append({"pdf": pair["pdf"], "status": pair["status"]})
    candidates = resolver_names(repo, scratch, files)
    queue = audit_print_pairs.audit(scratch, candidates, receipts)
    all_pairs = defaultdict(list)
    for pair in queue["pairs"]:
        all_pairs[pair["sample"]].append(pair)
    unmatched = {entry["sample"] for entry in candidates["unmatched"]}
    if by_source.keys() - files.keys():
        raise ValueError("Receipt references a source outside the pinned inventory")

    axes = defaultdict(list)
    for line in (scratch / (FIXTURES + "deferred_visual_regression_inputs.tsv")).read_text().splitlines():
        if line and not line.startswith("#"):
            path, names, issue = line.split("\t")
            axes[path].append({"axes": names.split(","), "issue": issue})

    def lines(name):
        return blob(repo, FIXTURES + name).decode().splitlines()

    baseline = {line.split("\t", 1)[0] for line in lines("oracle_page_count_baseline.tsv")
                if line and not line.startswith("#")}
    deferred_names = set(lines("deferred_document_regressions.txt"))
    excluded = set(lines("transferred_exam_regressions.txt")) | deferred_names
    counts = Counter(oid for oid, mode in files.values())
    roots = {root: Counter() for root in ROOTS}
    rows = []
    for path, (oid, mode) in sorted(files.items()):
        root = next(root for root in ROOTS if path.startswith(root + "/"))
        name = PurePosixPath(path)
        roots[root][name.suffix.lower()[1:]] += 1
        resolver = "outside_samples"
        if root == "samples":
            resolver = "excluded" if name.name in deferred_names or path[8:] in excluded else "in_scope"
        rows.append({"path": path, "blob": oid, "git_mode": mode, "paths_with_same_blob": counts[oid],
                     "general_regression_deferred": is_deferred_regression_input(path),
                     "visual_deferrals": axes[path], "page_count_baseline": path in baseline,
                     "resolver_scope": resolver, "receipt_pairs": by_source.get(path, [])})
    for row in rows:
        row["oracle_state"] = classify(row, all_pairs[row["path"]], unmatched)
    summary = {"source_revision": REV, "source_paths": len(rows), "unique_blobs": len(counts),
               "by_root": roots, "receipt_file": RECEIPT,
               "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
               "receipt_pair_status": audited["statusCounts"],
               "receipt_verified_sources": sum(any(p["status"] == "verified" for p in entries)
                                               for entries in by_source.values())}
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--rows", type=Path, help="Private per-path JSON destination")
    parser.add_argument("--check", action="store_true", help="Compare to the public snapshot")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        rows, summary = inventory(args.repo, Path(folder))
    if args.rows:
        args.rows.write_text(json.dumps({"source_revision": REV, "rows": rows}, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    if args.check and summary != json.loads((DASHBOARD / "corpus/inventory-summary.json").read_text()):
        raise SystemExit("Inventory differs from the published snapshot")


if __name__ == "__main__":
    main()
