"""Reproduce initial Native Skia failures on public, receipt-backed inputs."""
import argparse
from pathlib import Path

import adapter
from core import canonical, manifest, write_json
from receipt_cohort import contract, verify_receipt, verify_registered
from track_cohort import tracked_config


def main(upstream, work):
    config, documents = contract(tracked_config())
    verify_receipt(config)
    verify_registered(config)
    # Use the same registered cohort as the production run, including its passing controls.
    ids = {d["id"] for d in config["documents"] if "reference_evidence" in d}
    docs = [d for d in documents if d["id"] in ids]
    if not docs:
        raise ValueError("No registered controls or failed inputs")
    corpus = work / "corpus"
    write_json(corpus / "manifest.json", {"schema_version": 1, "documents": docs})
    adapter.materialize(corpus, docs)
    manifest(corpus)
    for doc in docs:
        code, base, log = adapter.sweep_document(upstream, corpus, work, "native", doc, True)
        result = adapter.sweep_diagnosis(base, log)
        if result["silhouette_manifest.json"]:
            row = adapter.consume(base, doc, selected=True, backend="native")
            result["score"] = row["scores"][0]["raw"] if row["scores"] else None
            result["rendered_pages"] = row["rendered_pages"]
        print("Native diagnostic " + canonical({"id": doc["id"], "exit": code, **result}).decode(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    main(args.upstream.resolve(), args.work.resolve())
