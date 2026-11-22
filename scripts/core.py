"""Trusted metadata boundary. No upstream HTML, paths or arbitrary strings are published."""
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

PROTOCOL = "silhouette-96dpi-rgb232-radius2-v1"
SHA = re.compile(r"[0-9a-f]{40}")
HASH = re.compile(r"[0-9a-f]{64}")
KEY = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
STATES = {"empty", "complete", "partial", "failed", "unavailable"}
BACKENDS = ("native", "wasm")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def read_json(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 8_000_000:
        raise ValueError("unsafe JSON file")
    return json.loads(path.read_text())

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")

def integer(x, maximum=1000000):
    if type(x) is not int or not 0 <= x <= maximum:
        raise ValueError("invalid nonnegative integer")
    return x

def exact(obj, keys):
    if type(obj) is not dict or set(obj) != set(keys.split()):
        raise ValueError("unexpected fields")
    return obj

def match(pattern, value):
    if type(value) is not str or not pattern.fullmatch(value):
        raise ValueError("invalid identifier")
    return value

def safe_path(root, relative):
    if type(relative) is not str or "\\" in relative:
        raise ValueError("invalid path")
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError("path traversal")
    root = Path(root).resolve()
    dest = root / p
    if dest.is_symlink() or not dest.resolve().is_relative_to(root):
        raise ValueError("path escapes corpus")
    return dest

def safe_file(root, relative):
    dest = safe_path(root, relative)
    if not dest.is_file():
        raise ValueError("missing corpus file")
    return dest

def verify_document_inputs(root, document):
    """Check the bytes supplied to one document's render using bounded reads."""
    sources = [document[name] for name in ("document", "golden", "font_environment")
               if document[name]["path"] is not None]
    for group, message in ((sources, "corpus hash mismatch"), (document["fonts"], "font hash mismatch")):
        for asset in group:
            with safe_file(root, asset["path"]).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
                    raise ValueError(message)


def manifest(root, verify=True):
    root = Path(root)
    m = read_json(root / "manifest.json")
    exact(m, "schema_version documents")
    if type(m["schema_version"]) is not int or m["schema_version"] != 1 or type(m["documents"]) is not list:
        raise ValueError("manifest schema")
    seen = set()
    for d in m["documents"]:
        exact(d, "id document golden compat pages font_environment fonts publication")
        key = match(KEY, d["id"])
        if key in seen:
            raise ValueError("duplicate document")
        seen.add(key)
        if d["compat"] not in ("2022", "2024") or integer(d["pages"]) < 1:
            raise ValueError("invalid golden contract")
        exact(d["publication"], "approved evidence metadata_approved raw_files")
        if d["publication"]["raw_files"] is not False:
            raise ValueError("this dashboard does not redistribute corpus assets")
        if d["publication"]["approved"] is not True or d["publication"]["metadata_approved"] is not True:
            raise ValueError("publication permission missing")
        if not isinstance(d["publication"]["evidence"], str) or not d["publication"]["evidence"].strip():
            raise ValueError("publication evidence missing")
        for name in ("document", "golden", "font_environment"):
            record = d[name]
            exact(record, "path sha256 source provenance")
            if name == "font_environment" and record["path"] is None and record["sha256"] is None:
                if not record["source"] or not record["provenance"]:
                    raise ValueError("default font contract missing")
                continue
            match(HASH, record["sha256"])
            safe_path(root, record["path"])
            if not all(isinstance(record[k], str) and record[k].strip() for k in ("source", "provenance")):
                raise ValueError("source/provenance missing")
        if not d["golden"]["provenance"].startswith("Hancom Print "):
            raise ValueError("independent Hancom Print required")
        if type(d["fonts"]) is not list:
            raise ValueError("font contract missing")
        for font in d["fonts"]:
            exact(font, "path sha256 source license usage_approved")
            match(HASH, font["sha256"])
            safe_path(root, font["path"])
            if font["usage_approved"] is not True or not font["license"] or not font["source"]:
                raise ValueError("font redistribution not approved")
        if verify:
            verify_document_inputs(root, d)
    return m

def stats(scores):
    if not scores:
        return {"median": None, "p10": None, "min": None, "below90": 0}
    values = sorted(scores)
    # Nearest-rank P10. Each page has equal weight; not a document accuracy rate.
    return {"median": statistics.median(values), "p10": values[max(0, math.ceil(len(values)*0.1)-1)],
            "min": min(values), "below90": sum(x < 90 for x in values)}

def empty_backend():
    return {"status": "unavailable", "exit_code": None, "quality_alert": False,
            "documents": []}

def validate_backend(value, documents):
    exact(value, "status exit_code quality_alert documents")
    if value["status"] not in STATES:
        raise ValueError("backend status")
    if value["exit_code"] is not None:
        integer(value["exit_code"], 255)
    if type(value["quality_alert"]) is not bool or type(value["documents"]) is not list:
        raise ValueError("backend fields")
    allowed = {d["id"]: d["pages"] for d in documents}
    seen = set()
    for row in value["documents"]:
        exact(row, "id status pdf_pages rendered_pages scores")
        key = match(KEY, row["id"])
        if key not in allowed or key in seen or row["status"] not in STATES:
            raise ValueError("unexpected document")
        seen.add(key)
        for field in ("pdf_pages", "rendered_pages"):
            if row[field] is not None:
                integer(row[field])
        if type(row["scores"]) is not list or len(row["scores"]) > allowed[key]:
            raise ValueError("too many pages")
        pages = set()
        for score in row["scores"]:
            exact(score, "page raw")
            p = integer(score["page"])
            if not 1 <= p <= allowed[key] or p in pages:
                raise ValueError("duplicate/out-of-range page")
            pages.add(p)
            x = score["raw"]
            if type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 100:
                raise ValueError("invalid score")
        if row["status"] == "complete":
            if pages != set(range(1, allowed[key]+1)):
                raise ValueError("incomplete page coverage")
            if row["pdf_pages"] != allowed[key]:
                raise ValueError("golden page contract mismatch")
            if row["rendered_pages"] is None:
                raise ValueError("unknown rendered page count")
    if value["status"] == "complete" and value["exit_code"] not in (0, 1):
        raise ValueError("complete backend has execution failure")
    alert = any(s["raw"] < 90 for d in value["documents"] for s in d["scores"]) or any(
        d["pdf_pages"] is not None and d["rendered_pages"] is not None and d["pdf_pages"] != d["rendered_pages"]
        for d in value["documents"]) or value["exit_code"] == 1
    if alert and value["quality_alert"] is not True:
        raise ValueError("hidden quality alert")
    if value["status"] == "complete" and (seen != set(allowed) or not allowed or
            any(d["status"] != "complete" for d in value["documents"])):
        raise ValueError("false completion")
    return value

def validate_measurement(value, documents):
    exact(value, "schema_version environment_sha256 build_sha256 backends")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("schema version")
    for name in ("environment_sha256", "build_sha256"):
        if value[name] is not None:
            match(HASH, value[name])
    exact(value["backends"], "native wasm")
    for backend in BACKENDS:
        validate_backend(value["backends"][backend], documents)
    if any(d["scores"] for b in BACKENDS for d in value["backends"][b]["documents"]):
        if value["environment_sha256"] is None or value["build_sha256"] is None:
            raise ValueError("scores lack producer provenance")
    return value

def public_record(plan, measurement, documents):
    # plan is generated in the trusted resolver and never comes from upstream execution.
    validate_measurement(measurement, documents)
    result = dict(plan)
    result["measurement"] = measurement
    states = [measurement["backends"][b]["status"] for b in BACKENDS]
    result["status"] = ("empty" if not documents else "complete" if states == ["complete"]*2
                        else "partial" if any(d["scores"] for b in BACKENDS
                                             for d in measurement["backends"][b]["documents"])
                        else "failed")
    return result

def coverage(backend, documents):
    rows = {d["id"]: d for d in backend["documents"]}
    scores = [s["raw"] for d in rows.values() for s in d["scores"]]
    target = sum(d["pages"] for d in documents)
    failed = [d for d in documents if d["id"] in rows and rows[d["id"]]["status"] == "failed"]
    skipped = [d for d in documents if d["id"] not in rows or rows[d["id"]]["status"] == "unavailable"]
    measured_docs = sum(d["status"] == "complete" for d in rows.values())
    failed_pages = sum(d["pages"] - len(rows[d["id"]]["scores"]) for d in failed)
    skipped_pages = sum(d["pages"] for d in skipped)
    return {"target_docs": len(documents), "measured_docs": measured_docs,
            "failed_docs": len(failed), "skipped_docs": len(skipped),
            "target_pages": target, "measured_pages": len(scores), "failed_pages": failed_pages,
            "skipped_pages": skipped_pages, "unmeasured_pages": target-len(scores),
            "page_count_mismatch": sum(d["pdf_pages"] != d["rendered_pages"] for d in rows.values()
                                      if d["pdf_pages"] is not None and d["rendered_pages"] is not None),
            **stats(scores)}
