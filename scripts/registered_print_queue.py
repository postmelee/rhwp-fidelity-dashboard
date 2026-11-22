"""Audit newer upstream Print registrations against a fixed dashboard inventory."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen


from core import SHA, match, read_json, write_json
from corpus_inventory import REV

REGISTRY = "tests/fixtures/oracle_page_count_verified_references.json"
LIMIT = 32 * 1024 * 1024


def fetch(revision, name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError("Invalid upstream reference path")
    url = f"https://raw.githubusercontent.com/edwardkim/rhwp/{match(SHA, revision)}/{quote(name)}"
    with urlopen(url, timeout=60) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Public reference exceeds the measurement size limit")
    return data


def explicit_print(registered, evidence):
    """Return conditions only for an exact linked output in a known evidence format."""
    expected = (registered["pdf"], registered["pdf_sha256"], registered["pages"])
    source = registered["source_sha256"]
    if isinstance(evidence, dict) and isinstance(evidence.get("datasets"), dict):
        for dataset in evidence["datasets"].values():
            original = dataset.get("input", {})
            if original.get("sha256") != source:
                continue
            for print_record in (dataset.get("print", {}), dataset.get("archived_print", {})):
                if tuple(print_record.get(k) for k in ("path", "sha256", "pages")) == expected:
                    return print_record.get("engine"), print_record.get("compat")
    if isinstance(evidence, list):
        for row in evidence:
            output = row.get("output", {})
            if (row.get("input_sha256") == source
                    and tuple(row.get(k) for k in ("file", "sha256", "pages")) == expected
                    and output.get("input_preprocess") == "none"
                    and output.get("pdf_print_method") == 0
                    and output.get("pdf_output_mode") in {"hancom2020_pdf_driver_one_up", "frame_print_to_pdf_ex_one_up"}
                    and output.get("hancom_version")):
                return output["engine"], row["compat"]
    if isinstance(evidence, dict) and "official_print" in evidence:
        output = evidence["official_print"]
        if (evidence.get("input_sha256") == source
                and tuple(output.get(k) for k in ("path", "sha256", "pdf_page_count")) == expected
                and output.get("pdf_print_method") == 0
                and output.get("input_preprocess") == "none"
                and output.get("pdf_output_mode") == "hancom2020_pdf_driver_one_up"
                and output.get("hancom_version")):
            return output["engine"], "2022"
    return None


def acquisition_plan(worklist, ready):
    """Queue every path once, retaining aliases for evaluation before new Print."""
    known = {d["input"]: d["source_sha256"] for d in ready}
    verified_hashes = set(known.values())
    states = {
        "verified": "review_verified_pair_for_admission",
        "review_candidate": "review_existing_pdf",
        "needs_print_review": "check_local_print_preflight",
        "outside_resolver_scope": "check_other_reference_sources",
        "deferred_oracle": "review_deferral",
    }
    order = ("ready", "review_verified_pair_for_admission", "review_same_bytes_reference",
             "review_existing_pdf", "check_local_print_preflight", "check_other_reference_sources",
             "review_deferral", "review_other")
    queue = {state: [] for state in order}
    tasks = worklist["tasks"]
    if len({t["path"] for t in tasks}) != worklist["paths"]:
        raise ValueError("Acquisition denominator mismatch")
    for task in sorted(tasks, key=lambda t: t["path"]):
        path, sha = task["path"], task["source_sha256"]
        if path in known:
            if known[path] != sha:
                raise ValueError("Ready Print no longer matches the source inventory")
            status = "ready"
        elif task["oracle_state"] == "verified":
            status = states["verified"]
        elif sha in verified_hashes:
            status = "review_same_bytes_reference"
        else:
            status = states.get(task["oracle_state"], "review_other")
        queue[status].append({"path": path, "source_sha256": sha,
                              "source_blob": task["source_blob"], "pdf_candidates": task["pdf_candidates"]})
    return {"paths": len(tasks), "counts": {state: len(queue[state]) for state in order},
            "ready_distinct_source_bytes": len(verified_hashes), "queue": queue}


def audit(revision, worklist):
    import pypdfium2
    from track_cohort import tracked_config

    if worklist["revision"] != REV:
        raise ValueError("Wrong source inventory revision")
    tasks = {r["path"]: r for r in worklist["tasks"]}
    tracked = tracked_config()["documents"]
    known = {r["input"] for r in tracked}
    registry = json.loads(fetch(revision, REGISTRY))
    reports, admitted = [], []
    evidence_cache = {}
    for ref in registry["references"]:
        source = ref["sample"]
        path = tasks.get(source)
        detail = {"path": source, "pdf": ref["pdf"], "pages": ref["pages"]}
        reports.append(detail)
        if ref["provenance"] != "desktop_hancom_print":
            detail["status"] = "different_reference_type"
            continue
        if source in known:
            detail["status"] = "already_tracked"
            continue
        if path is None:
            detail["status"] = "outside_pinned_inventory"
            continue
        if path["source_sha256"] != ref["source_sha256"]:
            detail["status"] = "source_changed"
            continue
        evidence_path = ref["evidence"]
        try:
            if evidence_path not in evidence_cache:
                evidence_cache[evidence_path] = fetch(revision, evidence_path)
            evidence_raw = evidence_cache[evidence_path]
            conditions = explicit_print(ref, json.loads(evidence_raw)) if evidence_path.endswith(".json") else None
            if not conditions or not conditions[0] or conditions[1] not in ("2022", "2024"):
                detail["status"] = "print_conditions_review"
                continue
            pdf = fetch(revision, ref["pdf"])
            if hashlib.sha256(pdf).hexdigest() != ref["pdf_sha256"]:
                detail["status"] = "pdf_hash_mismatch"
                continue
            with pypdfium2.PdfDocument(pdf) as doc:
                if len(doc) != ref["pages"]:
                    detail["status"] = "pdf_page_count_mismatch"
                    continue
        except HTTPError as error:
            if error.code != 404:
                raise
            detail["status"] = "registered_file_missing"
            continue
        except ValueError:
            detail["status"] = "unsupported_evidence_or_asset"
            continue
        detail["status"] = "verified_for_measurement"
        admitted.append({"input": source, "id": "registered-" + hashlib.sha256(source.encode()).hexdigest()[:16],
                         "source_sha256": ref["source_sha256"], "pdf": ref["pdf"], "pdf_sha256": ref["pdf_sha256"],
                         "pages": ref["pages"], "reference_revision": revision, "reference_evidence": evidence_path,
                         "reference_evidence_sha256": hashlib.sha256(evidence_raw).hexdigest(),
                         "hancom": conditions[0], "compat": conditions[1]})
    return {"source_revision": REV, "reference_revision": revision, "registry": REGISTRY,
            "status_counts": dict(Counter(row["status"] for row in reports)),
            "rows": reports, "admitted": admitted,
            "acquisition": acquisition_plan(worklist, [*tracked, *admitted])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_revision")
    parser.add_argument("worklist", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = audit(args.reference_revision, read_json(args.worklist))
    write_json(args.output, report)
    print("Print registration audit:", report["status_counts"], flush=True)
    print("Acquisition queue:", report["acquisition"]["counts"], flush=True)
