"""Measure the receipt-backed corpus against one pinned release in two stages."""
import argparse
from pathlib import Path
import os
import urllib.request

import adapter
from core import BACKENDS, PROTOCOL, canonical, digest, manifest, read_json, validate_measurement, write_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "corpus/receipt-cohort.json"


def contract():
    config = read_json(CONFIG)
    base = "https://raw.githubusercontent.com/edwardkim/rhwp/" + config["corpus_sha"] + "/"
    defaults = manifest(ROOT / "corpus", verify=False)["documents"][0]
    docs = []
    for row in config["documents"]:
        def asset(path, sha, provenance):
            return {"path": "cache/" + row["id"] + "/" + Path(path).name, "source": base + path,
                    "sha256": sha, "provenance": provenance}
        docs.append({
            "id": row["id"], "compat": "2022", "pages": row["pages"],
            "document": asset(row["input"], row["source_sha256"], "Public upstream verification input"),
            "golden": asset(row["pdf"], row["pdf_sha256"], "Hancom Print " + row["hancom"]),
            "publication": {"approved": True, "metadata_approved": True, "raw_files": False,
                            "evidence": base + config["receipt"]},
            "font_environment": defaults["font_environment"], "fonts": defaults["fonts"],
        })
    return config, docs


def verify_receipt(config):
    import json
    url = "https://raw.githubusercontent.com/edwardkim/rhwp/" + config["corpus_sha"] + "/" + config["receipt"]
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(2_000_000)
    if digest(data) != config["receipt_sha256"]:
        raise ValueError("Print receipt digest mismatch")
    rows = {r["key"]: r for r in json.loads(data)["cases"]}
    if set(rows) != {r["id"] for r in config["documents"]} or len(rows) != len(config["documents"]):
        raise ValueError("Receipt cohort membership mismatch")
    for item in config["documents"]:
        rec = rows[item["id"]]
        if (rec["input"], rec["input_sha256"], rec["pdf"], rec["pdf_sha256"], rec["origin"]["engine"]) != (
                item["input"], item["source_sha256"], item["pdf"], item["pdf_sha256"], item["hancom"]):
            raise ValueError("Receipt and cohort disagree")


def measure(upstream, output, stage):
    import pypdfium2
    config, docs = contract()
    verify_receipt(config)
    docs = docs[:1] if stage == "pilot" else docs[1:]
    corpus = output / "corpus"
    write_json(corpus / "manifest.json", {"schema_version": 1, "documents": docs})
    adapter.materialize(corpus, docs)
    for doc in docs:
        with pypdfium2.PdfDocument(str(corpus / doc["golden"]["path"])) as pdf:
            if len(pdf) != doc["pages"]:
                raise ValueError("Independent PDF page count mismatch")
    result = adapter.run(upstream, corpus, output / stage / "result.json", config["engine_sha"])
    validate_measurement(result, docs)
    artifacts = {}
    for backend in BACKENDS:
        for row in result["backends"][backend]["documents"]:
            if not row["scores"]:
                continue
            folder = output / stage / "private" / backend / "full" / row["id"] / row["id"]
            provenance = read_json(folder / "silhouette_manifest.json")["provenance"]
            font_supply = provenance.get("font_supply")
            receipt = folder / ("native-export.json" if backend == "native" else "wasm-export-complete.json")
            artifacts[backend + "/" + row["id"]] = {
                "run_manifest_sha256": digest((folder / "run_manifest.json").read_bytes()),
                "export_sha256": digest(receipt.read_bytes()), "tsv_sha256": digest((folder / "silhouette.tsv").read_bytes()),
                "font_supply_sha256": digest(canonical(font_supply)) if font_supply else None,
            }
    record = {"stage": stage, "run_id": int(os.environ["GITHUB_RUN_ID"]),
              "attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]), "producer_sha": os.environ["GITHUB_SHA"],
              "engine_sha": config["engine_sha"], "cohort_sha256": digest(canonical(config)),
              "protocol": PROTOCOL, "measurement": result, "artifacts": artifacts}
    write_json(output / "numeric" / (stage + ".json"), record)
    print("COHORT_RECORD " + canonical(record).decode(), flush=True)
    if any(result["backends"][backend]["status"] != "complete" for backend in BACKENDS):
        raise SystemExit("Incomplete renderer coverage; numeric rows retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("stage", choices=("pilot", "expanded"))
    args = parser.parse_args()
    measure(args.upstream.resolve(), args.output.resolve(), args.stage)
