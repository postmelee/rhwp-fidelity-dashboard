"""Prepare locally held Hancom Print pairs for the dashboard's existing Linux runner."""
import argparse
from collections import Counter, defaultdict
from importlib import import_module
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import sys

from core import canonical, digest, manifest, read_json, safe_file, write_json
from corpus_inventory import ORACLE, REV, sources
from receipt_cohort import ROOT


# The document inventory and the receipt format have independent lifetimes.
AUDITOR_REV = "77e4c3d1369623818e8cf3213e3fdc21d8e6502e"


def receipt_cases(path, index_receipts):
    """Load a batch of job receipts and postpone ambiguous versions of a pair."""
    if not path.is_dir():
        receipt = read_json(path)
        return receipt, set(), digest(canonical(receipt))
    paths = sorted(entry for entry in path.glob("*.json") if entry.is_file() and not entry.is_symlink())
    if not paths:
        raise ValueError("No Print receipts in the batch directory")
    pairs = defaultdict(dict)
    for receipt in paths:
        for pair, record in index_receipts(read_json(receipt)).items():
            pairs[pair][digest(canonical(record))] = record
    conflicts = {source for (source, _), versions in pairs.items() if len(versions) > 1}
    merged = {"cases": [next(iter(versions.values())) for (source, _), versions in sorted(pairs.items())
                        if source not in conflicts]}
    scope = {"entries": [(pair, sorted(versions)) for pair, versions in sorted(pairs.items())]}
    return merged, conflicts, digest(canonical(scope))


def audit_receipts(repo, receipt_path):
    with TemporaryDirectory() as scratch:
        # Package-relative imports keep the inventory's oracle_resolver out of this audit.
        package = "rhwp_print_" + AUDITOR_REV
        folder = Path(scratch) / package
        folder.mkdir()
        (folder / "__init__.py").touch()
        for name in ("audit_print_pairs.py", "oracle_resolver.py"):
            blob = AUDITOR_REV + ":" + ORACLE + name
            result = subprocess.run(["git", "-C", repo, "show", blob], capture_output=True)
            if result.returncode:
                raise ValueError(f"Cannot read pinned receipt auditor {blob}: {result.stderr.decode().strip()}")
            (folder / name).write_bytes(result.stdout)
        sys.path.insert(0, scratch)
        try:
            module = import_module(package + ".audit_print_pairs")
            receipt, conflicts, receipt_digest = receipt_cases(receipt_path, module.index_receipts)
            rows = module.audit(repo, {"pairs": [], "unmatched": []}, receipt)["pairs"]
            return rows, conflicts, receipt_digest
        finally:
            sys.path.remove(scratch)
            for name in (".audit_print_pairs", ".oracle_resolver", ""):
                sys.modules.pop(package + name, None)


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
    git = ["git", "-C", repo]
    pairs, conflicting_sources, receipt_digest = audit_receipts(repo, receipt_path)
    defaults = manifest(ROOT / "corpus", verify=False)["documents"][0]
    found = defaultdict(list)
    for pair in pairs:
        if pair["sample"] in files:
            found[pair["sample"]].append(pair)
    docs, accounting = [], []
    scope = {"corpus_sha": REV, "receipt_auditor_sha": AUDITOR_REV, "receipt_sha256": receipt_digest,
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
                evidence = pair["print"]
                conditions = evidence.get("result", evidence)
                profile = " ".join(str(conditions[key]) for key in ("engine", "hancom_version", "pdf_output_mode")
                                   if key in conditions)
                provenance = "Hancom Print " + evidence["kind"] + " " + profile
                assets = []
                for name, hash_key, asset_provenance in ((path, "sampleHash", "Pinned rhwp inventory source"),
                                                    (pair["pdf"], "pdfHash", provenance)):
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
                                   "source": "urn:sha256:" + expected, "provenance": asset_provenance})
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
    report = {**scope, "paths": len(files), "verified": len(docs),
              "out_of_inventory": sum(p["sample"] not in files for p in pairs), "rows": accounting}
    outside = conflicting_sources - files.keys()
    if outside:
        report["out_of_inventory_conflicts"] = len(outside)
    write_json(folder / "intake.json", report)
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
