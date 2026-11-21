"""Reproduce the paired historical page table from PR #9024's published evidence."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

REV = "39a3774de60c81a3b803d158c044ddc195733eb6"
FOLDER = "mydocs/pr/assets/issue8946/stage10-20261114/"
RAW = f"https://raw.githubusercontent.com/edwardkim/rhwp/{REV}/{FOLDER}"
BASE_FOLDER = "mydocs/pr/assets/issue8946/stage9-20261113/"


def fetch(name):
    with urlopen(RAW + name, timeout=90) as response:
        return response.read()


def tsv_records(value):
    if isinstance(value, dict):
        if "tsv_sha256" in value and "tsv" in value:
            yield value
        else:
            for child in value.values():
                yield from tsv_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from tsv_records(child)


def read_pages(name, backend, evidence):
    data = fetch("original/head/" + name)
    digest = hashlib.sha256(data).hexdigest()
    matches = [row for row in evidence if row["tsv_sha256"] == digest
               and Path(row["tsv"]).name == name
               and row["provenance"]["raster_backend"] == backend
               and row["provenance"]["comparison_profile"] == "print"]
    if not matches:
        raise ValueError(f"Missing Print evidence for {name}")
    inputs = {(row["provenance"]["hwp"]["sha256"], row["provenance"]["pdf"]["sha256"])
              for row in matches}
    if len(inputs) != 1:
        raise ValueError(f"Ambiguous input pair for {name}")
    pages = {}
    for row in csv.DictReader(io.StringIO(data.decode()), delimiter="\t"):
        page = int(row["page"])
        score = float(row["silhouette_raw_match_percent"])
        if page in pages or not 0 <= score <= 100:
            raise ValueError(f"Invalid score or duplicate page in {name}")
        pages[page] = score
    if set(pages) != set(range(1, 764)):
        raise ValueError(f"Incomplete page scope in {name}")
    return inputs.pop(), pages


def visual_sweep(repo):
    """Verify the submitted HWPX comparison against both sets of original TSVs."""
    files = {}

    def read(folder, name):
        path = folder + name
        data = subprocess.check_output(["git", "--no-lazy-fetch", "-C", str(repo), "show", f"{REV}:{path}"])
        files[path] = hashlib.sha256(data).hexdigest()
        return data

    def rows(data):
        return csv.DictReader(io.StringIO(data.decode()), delimiter="\t")

    comparison_name = "last-devel-full-comparison.tsv"
    comparison_rows = list(rows(read(FOLDER, comparison_name)))
    comparison = json.loads(read(FOLDER, "last-devel-full-comparison.json"))
    producer = json.loads(read(FOLDER, "producer.json"))
    reference = json.loads(read(BASE_FOLDER, "local-reference-preservation.json"))
    base = json.loads(read(BASE_FOLDER, "visual-provenance.json"))
    head = json.loads(read(FOLDER, "visual-provenance.json"))
    series = {"base": {}, "head": {}}
    for backend, renderer in (("native", "native-skia"), ("wasm", "wasm-canvas2d")):
        entry, = (d for d in comparison["datasets"] if d["document"] == "hwpx" and d["backend"] == backend)
        values = [r for r in comparison_rows if r["document"] == "hwpx" and r["backend"] == backend]
        for side, folder, evidence, subdir in (
            ("base", BASE_FOLDER, base, "last"), ("head", FOLDER, head, "head"),
        ):
            filename = f"original/{subdir}/hwpx-{backend}.tsv"
            data = read(folder, filename)
            proof, = (r for r in evidence if r.get("tsv_sha256") == files[folder + filename]
                      and r["backend"] == backend and (
                          r.get("tsv") == filename if side == "head" else
                          (r.get("group"), r.get("key"), r.get("revision")) ==
                          ("original", "sample10-hwpx", subdir)))
            p = proof["provenance"]
            source = proof.get("renderer_source_sha", proof.get("source"))
            if (source != comparison[side] or source != producer[side]
                    or p["raster_backend"] != renderer or p["comparison_profile"] != "print"
                    or p["pdf"]["sha256"] != reference["sha256"]
                    or p["pdf"]["path"] != reference["source"]):
                raise ValueError("Visual Sweep producer or Print reference mismatch")
            programs = ([p["rhwp_binary"]] if backend == "native" else p["wasm"]["files"])
            artifacts = {Path(x["path"]).name: x["sha256"] for x in programs}
            binary = next(iter(artifacts.values())) if backend == "native" else artifacts["rhwp_bg.wasm"]
            if binary != producer[backend][side]["sha256"]:
                raise ValueError("Visual Sweep executable mismatch")
            settings = {key: p.get(key) for key in (
                "image_decoding", "pdf_rasterizer", "svg_rasterizer", "png_exporter_sha256",
                "font_environment", "font_supply", "native_webfont_fallback", "linked_images",
            )}
            if backend == "wasm":
                settings["wasm"] = {k: v for k, v in p["wasm"].items() if k != "files"}
            conditions = {
                "document_sha256": p["hwp"]["sha256"], "reference_sha256": p["pdf"]["sha256"],
                "backend": renderer, "profile": "print", "dpi": 96, "compat": p["layout_generation"],
                "settings_sha256": hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(),
            }
            source_pages = [(int(r["page"]), float(r["silhouette_raw_match_percent"])) for r in rows(data)]
            scores = [(int(r["page"]), float(r[side + "_raw"])) for r in values]
            counts = proof["page_counts"]
            expected = list(range(1, counts["pdf"] + 1))
            if ([page for page, _ in source_pages] != expected or [page for page, _ in scores] != expected
                    or counts["rhwp"] != counts["pdf"] or len(scores) != entry["pages"]
                    or any(not 0 <= raw <= 100 or abs(display - raw) > 0.005001
                           for (_, display), (_, raw) in zip(source_pages, scores))):
                raise ValueError("Visual Sweep comparison differs from the verified original TSV")
            series[side][backend] = {
                "source_sha": source, "source_tree_sha": subprocess.check_output(
                    ["git", "--no-lazy-fetch", "-C", str(repo), "rev-parse", f"{source}^{{tree}}"],
                    text=True).strip(),
                "artifacts": artifacts, "conditions": conditions, "counts": counts,
                "sweep_script_sha256": p["sweep_script"]["sha256"],
                "original_tsv": folder + filename, "scores": dict(scores),
            }
        if series["base"][backend]["conditions"] != series["head"][backend]["conditions"]:
            raise ValueError("Visual Sweep base/head conditions differ")
    return {"kind": "submitted_visual_sweep", "pr": 9024, "revision": REV, "document": "HWPX",
            "reference": reference["source"], "comparison_tsv": FOLDER + comparison_name,
            "files": files, "series": series}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?")
    parser.add_argument("--upstream", type=Path, help="Read the pinned Visual Sweep evidence from local Git")
    args = parser.parse_args()
    if args.upstream:
        print(json.dumps(visual_sweep(args.upstream), indent=2, sort_keys=True, allow_nan=False))
        return
    if args.snapshot is None:
        parser.error("supply the existing page snapshot or --upstream")
    evidence = list(tsv_records(json.loads(fetch("visual-provenance.json"))))
    a, native = read_pages("hwpx-native.tsv", "native-skia", evidence)
    b, wasm = read_pages("hwpx-wasm.tsv", "wasm-canvas2d", evidence)
    if a != b:
        raise ValueError("Different source or reference PDF")
    expected = [[p, native[p], wasm[p]] for p in sorted(native)]
    if json.loads(args.snapshot.read_text()) != expected:
        raise ValueError("Dashboard page rows differ from verified TSVs")
    print(f"Verified {len(expected)} paired pages and both TSV hashes at {REV}")


if __name__ == "__main__":
    main()
