"""Measure the receipt-backed corpus against one pinned release in two stages."""
import argparse
from pathlib import Path
import os
import re
from urllib.parse import quote
import urllib.request

import adapter
from core import BACKENDS, PROTOCOL, canonical, digest, manifest, read_json, validate_measurement, write_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "corpus/receipt-cohort.json"


def contract(config=None):
    if config is None:
        config = read_json(CONFIG)
    base = "https://raw.githubusercontent.com/edwardkim/rhwp/" + config["corpus_sha"] + "/"
    defaults = manifest(ROOT / "corpus", verify=False)["documents"][0]
    docs = []
    for row in config["documents"]:
        reference_base = ("https://raw.githubusercontent.com/edwardkim/rhwp/"
                          + row["reference_revision"] + "/" if "reference_revision" in row else base)
        def asset(path, sha, provenance, origin):
            return {"path": "cache/" + row["id"] + "/" + Path(path).name, "source": origin + quote(path),
                    "sha256": sha, "provenance": provenance}
        print_provenance = "Hancom Print " + row["hancom"]
        if "reference_archive" in row:
            print_provenance += " (archived record)"
        docs.append({
            "id": row["id"], "compat": row.get("compat", "2022"), "pages": row["pages"],
            "document": asset(row["input"], row["source_sha256"], "Public upstream verification input", base),
            "golden": asset(row["pdf"], row["pdf_sha256"], print_provenance, reference_base),
            "publication": {"approved": True, "metadata_approved": True, "raw_files": False,
                            "evidence": reference_base + quote(row.get("reference_evidence", config["receipt"]))},
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
    original = [r for r in config["documents"] if "reference_evidence" not in r]
    if set(rows) != {r["id"] for r in original} or len(rows) != len(original):
        raise ValueError("Receipt cohort membership mismatch")
    for item in original:
        rec = rows[item["id"]]
        if (rec["input"], rec["input_sha256"], rec["pdf"], rec["pdf_sha256"], rec["origin"]["engine"]) != (
                item["input"], item["source_sha256"], item["pdf"], item["pdf_sha256"], item["hancom"]):
            raise ValueError("Receipt and cohort disagree")


def verify_registered(config):
    import json
    verify_reference_aliases(config)
    docs = [d for d in config["documents"] if "reference_alias_of" not in d]
    verify_later_registered(d for d in docs if "reference_revision" in d)
    extra = [d for d in docs if "reference_evidence" in d and "reference_revision" not in d]
    if not extra:
        return
    base = "https://raw.githubusercontent.com/edwardkim/rhwp/" + config["corpus_sha"] + "/"
    def fetch(path):
        with urllib.request.urlopen(base + quote(path), timeout=60) as response:
            return json.load(response)
    registry = {d["sample"]: d for d in fetch(config["registry"])["references"]}
    sources = {path: fetch(path) for path in {d.get("measurement_evidence", d["reference_evidence"]) for d in extra}}
    for doc in extra:
        ref = registry[doc["input"]]
        keys = ("source_sha256", "pdf_sha256", "pdf", "pages")
        if (any(ref[k] != doc[k] for k in keys) or ref["provenance"] != "desktop_hancom_print"
                or ref["evidence"] != doc["reference_evidence"]):
            raise ValueError("Registered Print reference differs from measured scope")
        if "measurement_evidence" in doc:
            measured = [r for r in sources[doc["measurement_evidence"]]["results"]
                        if r["input"] == doc["input"] and r["reference_pdf"] == doc["pdf"]]
            if ({r["backend"] for r in measured} != {"native", "wasm"} or len(measured) != 2
                    or any((r["input_sha256"], r["pdf_sha256"], r["pages"], r["profile"]) !=
                           (doc["source_sha256"], doc["pdf_sha256"], doc["pages"], "print") for r in measured)):
                raise ValueError("Historical Print measurement disagrees with registered inputs")
            continue
        audit = [r for r in sources[ref["evidence"]] if r["hwp"] == doc["input"] and r["pdf"] == doc["pdf"]]
        if (len(audit) != 1 or audit[0]["input_sha256"] != doc["source_sha256"]
                or audit[0]["pdf_sha256"] != doc["pdf_sha256"] or audit[0]["input_matches_issue"] is not True
                or audit[0]["pdf_matches_issue"] is not True):
            raise ValueError("Historical input audit differs from registered Print reference")


def verify_reference_aliases(config):
    """Bind an alias to an already verified reference and identical input conditions."""
    source_docs = {r["id"]: r for r in config["documents"] if "reference_alias_of" not in r}
    for alias in config["documents"]:
        if "reference_alias_of" not in alias:
            continue
        original = source_docs.get(alias["reference_alias_of"])
        if original is None:
            raise ValueError("Missing independently verified original for the alias")
        if alias["input"] == original["input"] or Path(alias["input"]).name != Path(original["input"]).name:
            raise ValueError("Alias must name a different pinned path with the same basename")
        retained = {k: v for k, v in alias.items() if k not in ("id", "input", "reference_alias_of")}
        if retained != {k: v for k, v in original.items() if k not in ("id", "input")}:
            raise ValueError("Alias changed the original input digest or Print conditions")


def verify_archived_print(doc, archive):
    """Validate the paired Print record and content control in the official archive."""
    if doc["reference_archive"] != "official-print-references-v1":
        raise ValueError("Unknown archived Print record format")
    matches = [row for row in archive["references"]
               if (row["input"], row["input_sha256"], row["pdf"], row["pdf_sha256"], row["pages"])
               == (doc["input"], doc["source_sha256"], doc["pdf"], doc["pdf_sha256"], doc["pages"])]
    if len(matches) != 1:
        raise ValueError("Archived Print record differs from the pinned measurement input")
    record = matches[0]
    receipt = record["receipt"]
    job_id, version = receipt.get("job_id"), receipt.get("hancom_version")
    if (not isinstance(job_id, str)
            or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", job_id)
            or not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", version)
            or receipt.get("engine") != doc["hancom"] or doc["hancom"] != "2024"
            or doc.get("compat") != "2024"
            or type(receipt.get("pdf_print_method")) is not int or receipt["pdf_print_method"] != 0
            or receipt.get("pdf_output_mode") != "frame_print_to_pdf_ex_one_up"
            or receipt.get("input_preprocess") != "none"
            or type(receipt.get("pdf_page_count")) is not int
            or receipt["pdf_page_count"] != doc["pages"]):
        raise ValueError("Archived Print job conditions differ")
    controls = [row for row in archive["independent_print_content_control"]
                if row["document"] == record["key"]]
    expected = (doc["pages"], doc["pages"], doc["pages"], [])
    if (len(controls) != 1 or tuple(controls[0].get(key) for key in
            ("prior_pages", "new_pages", "matched_text_pages", "print_text_differences")) != expected):
        raise ValueError("Archived Print content control differs")


def verify_later_registered(documents):
    import json
    from functools import lru_cache

    items = list(documents)
    if not items:
        return
    from registered_print_queue import REGISTRY, explicit_print, fetch, reviewed_print_note

    @lru_cache(maxsize=None)
    def registry(revision):
        return {r["sample"]: r for r in json.loads(fetch(revision, REGISTRY))["references"]}

    evidence = lru_cache(maxsize=None)(fetch)
    for doc in items:
        revision = doc["reference_revision"]
        if "reference_archive" in doc:
            raw = evidence(revision, doc["reference_evidence"])
            if digest(raw) != doc["reference_evidence_sha256"]:
                raise ValueError("Archived Print evidence differs from the pinned evidence")
            verify_archived_print(doc, json.loads(raw))
            continue
        ref = registry(revision)[doc["input"]]
        if (ref["provenance"] != "desktop_hancom_print"
                or any(ref[k] != doc[k] for k in ("source_sha256", "pdf", "pdf_sha256", "pages"))
                or ref["evidence"] != doc["reference_evidence"]):
            raise ValueError("Later registration differs from the pinned measurement input")
        raw = evidence(revision, ref["evidence"])
        if digest(raw) != doc["reference_evidence_sha256"]:
            raise ValueError("Later Print evidence differs from the pinned evidence")
        if "print_note" in doc:
            reviewed = reviewed_print_note(revision, ref, evidence)
            actual = ((reviewed[0], reviewed[1]) if reviewed and all(doc.get(k) == v for k, v in reviewed[2].items())
                      else None)
        else:
            actual = explicit_print(ref, json.loads(raw))
        if actual != (doc["hancom"], doc["compat"]):
            raise ValueError("Later Print measurement conditions differ")


def measure(upstream, output, stage, config=None):
    import pypdfium2
    config, docs = contract(config)
    verify_receipt(config)
    verify_registered(config)
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
