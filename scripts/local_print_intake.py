"""Prepare locally held Hancom Print pairs for the dashboard's existing Linux runner."""
import argparse
from collections import Counter, defaultdict
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import sys

from core import canonical, digest, manifest, read_json, safe_file, write_json
from corpus_inventory import ORACLE, REV, sources
from receipt_cohort import ROOT


def receipt_cases(path, index_receipts):
    """Load a batch of job receipts and postpone ambiguous versions of a pair."""
    if path.is_dir():
        paths = sorted(entry for entry in path.glob("*.json") if entry.is_file() and not entry.is_symlink())
        if not paths:
            raise ValueError("No Print receipts in the batch directory")
    else:
        paths = [path]
    pairs = defaultdict(dict)
    for receipt in paths:
        for pair, record in index_receipts(read_json(receipt)).items():
            pairs[pair][digest(canonical(record))] = record
    conflicts = {source for (source, _), versions in pairs.items() if len(versions) > 1}
    merged = {"cases": [next(iter(versions.values())) for (source, _), versions in sorted(pairs.items())
                        if source not in conflicts]}
    scope = {"entries": [(pair, sorted(versions)) for pair, versions in sorted(pairs.items())]}
    return merged, conflicts, digest(canonical(scope))


def prepare(repo, receipt_path, target, metadata_evidence, compat):
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target) as scratch:
        return prepare_in(repo, receipt_path, target, Path(scratch) / "corpus", metadata_evidence, compat)


def prepare_in(repo, receipt_path, target, folder, metadata_evidence, compat):
    import pypdfium2

    if not metadata_evidence.strip():
        raise ValueError("Numeric metadata permission evidence is required")
    if subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip() != REV:
        raise ValueError("Input inventory checkout must match the pinned corpus revision")
    files = sources(repo)
    # Only the PDFs and receipts may be newly produced. Load the pinned audit implementation.
    git = ["git", "-C", repo]
    with TemporaryDirectory() as scratch:
        for name in ("audit_print_pairs.py", "oracle_resolver.py"):
            (Path(scratch) / name).write_bytes(subprocess.check_output(git + ["show", REV + ":" + ORACLE + name]))
        sys.path.insert(0, scratch)
        try:
            from audit_print_pairs import audit, index_receipts
            receipt, conflicting_sources, receipt_digest = receipt_cases(receipt_path, index_receipts)
            pairs = audit(repo, {"pairs": [], "unmatched": []}, receipt)["pairs"]
        finally:
            sys.path.pop(0)
    defaults = manifest(ROOT / "corpus", verify=False)["documents"][0]
    found = defaultdict(list)
    for pair in pairs:
        if pair["sample"] in files:
            found[pair["sample"]].append(pair)
    docs, accounting = [], []
    scope = {"corpus_sha": REV, "receipt_sha256": receipt_digest,
             "compat": compat, "metadata_evidence": metadata_evidence}
    folder.mkdir()
    for path, (blob, _) in sorted(files.items()):
        key = digest(path.encode())
        candidates = found[path]
        verified = [p for p in candidates if p["status"] == "verified"]
        state = "no_receipt"
        if path in conflicting_sources:
            state = "conflicting_receipts"
        if candidates:
            state = "multiple_verified_outputs" if len(verified) > 1 else "receipt_incomplete"
        if len(verified) == 1:
            pair = verified[0]
            actual = subprocess.check_output(git + ["hash-object", "--no-filters", "--", path], text=True).strip()
            if actual != blob:
                state = "source_changed_since_inventory"
            else:
                assets = []
                for name, hash_key, provenance in ((path, "sampleHash", "Pinned rhwp inventory source"),
                                                    (pair["pdf"], "pdfHash", "Hancom Print " + pair["print"]["kind"])):
                    suffix = Path(name).suffix.lower()
                    relative = f"cache/{key}/input{suffix}"
                    data = safe_file(repo, name)
                    dest = folder / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    expected = pair[hash_key]["actualSha256"]
                    shutil.copyfile(data, dest)
                    if digest(dest.read_bytes()) != expected:
                        raise ValueError("Local file changed during intake")
                    assets.append({"path": relative, "sha256": expected,
                                   "source": "urn:sha256:" + expected, "provenance": provenance})
                with pypdfium2.PdfDocument(str(folder / assets[1]["path"])) as pdf:
                    pages = len(pdf)
                if pages < 1:
                    raise ValueError("Empty reference PDF")
                docs.append({"id": key, "pages": pages, "compat": compat, "document": assets[0],
                             "golden": assets[1], "fonts": defaults["fonts"],
                             "font_environment": defaults["font_environment"],
                             "publication": {"approved": True, "metadata_approved": True, "raw_files": False,
                                             "evidence": metadata_evidence}})
                state = "verified"
        accounting.append({"path_sha256": key, "blob": blob, "status": state,
                           "receipt_states": dict(Counter(p["status"] for p in candidates))})
    write_json(folder / "manifest.json", {"schema_version": 1, "documents": docs})
    manifest(folder, verify=False)
    write_json(folder / "intake.json", {**scope, "paths": len(files), "verified": len(docs),
                                       "out_of_inventory": sum(p["sample"] not in files for p in pairs),
                                       "out_of_inventory_conflicts": len(conflicting_sources - files.keys()),
                                       "rows": accounting})
    final = target / digest(canonical([read_json(folder / "intake.json"), docs]))
    try:
        os.rename(folder, final)
    except OSError:
        if not final.is_dir() or any((final / name).read_bytes() != (folder / name).read_bytes()
                                     for name in ("intake.json", "manifest.json")):
            raise
    print(final)
    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("receipts", type=Path, help="A Print receipt JSON or a directory of job receipts")
    parser.add_argument("output", type=Path)
    parser.add_argument("--metadata-evidence", required=True, help="Approval or public provenance for numeric metadata")
    parser.add_argument("--compat", choices=("2022", "2024"), required=True)
    args = parser.parse_args()
    prepare(args.inventory.resolve(), args.receipts, args.output, args.metadata_evidence, args.compat)
