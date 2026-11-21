"""Import an audited upstream Render Diff ZIP. No renderer or extraction is needed."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZipFile

from core import HASH, SHA, digest, integer, match, read_json

ROOT = Path(__file__).resolve().parents[1]
RESULTS = "rhwp-studio/e2e/screenshots/render-diff/"
BUILD = "output/render-diff-build/"
BACKENDS = {
    "canvas": "Canvas · legacy vs layer",
    "direct_pdf": "Direct PDF · compatibility gate",
    "browser_pdf": "Browser / compatibility PDF · report only",
    "hancom_print": "Independent Hancom Print",
}
MEMBER = re.compile(r"(?:[a-zA-Z0-9_-][a-zA-Z0-9_.-]*/)*[a-zA-Z0-9_-][a-zA-Z0-9_.-]*")


def flag(value):
    if type(value) is not bool:
        raise ValueError("expected producer boolean")
    return value


def ratio(value):
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError("invalid pixel diff ratio")
    return value


def first_page_rows(report, fixtures):
    if report["config"]["maxPages"] != "1" or len(set(fixtures)) != len(fixtures):
        raise ValueError("expected a first-page fixture selection")
    pages = {}
    for row in report["results"]:
        fixture = row["fixture"]
        if fixture in pages or fixture not in fixtures or integer(row["pageIndex"]) != 0:
            raise ValueError("duplicate or out-of-scope result")
        pages[fixture] = row
    return pages


def import_archive(archive, origin):
    if digest(archive) != match(HASH, origin["artifact_sha256"]):
        raise ValueError("Render Diff artifact SHA-256 mismatch")
    with ZipFile(BytesIO(archive)) as bundle:
        if len(set(bundle.namelist())) != len(bundle.namelist()):
            raise ValueError("duplicate archive member")
        files = {}

        def read_member(name, max_size=8_000_000):
            match(MEMBER, name)
            info = bundle.getinfo(name)
            if info.file_size > max_size:
                raise ValueError("archive member exceeds size limit")
            data = bundle.read(info)
            files[name] = {"sha256": digest(data), "bytes": len(data)}
            return data

        def read_result(name):
            return json.loads(read_member(name))

        build = read_result(BUILD + "build.json")
        if (build["source_sha"] != match(SHA, origin["source_sha"])
                or build["source_dirty"] is not False or build["success"] is not True):
            raise ValueError("build receipt does not identify a clean, successful audited source")
        executables = {}
        for name in ("rhwp.js", "rhwp_bg.wasm"):
            product = build["artifacts"][name]
            executables["pkg/" + name] = {
                "sha256": match(HASH, product["sha256"]),
                "bytes": integer(product["bytes"], 100_000_000),
                "source": BUILD + "build.json",
            }
        wasm = executables["pkg/rhwp_bg.wasm"]["sha256"]
        receipts = sorted(name for name in bundle.namelist()
                          if name.startswith(BUILD + "consumption/") and name.endswith(".json"))
        if not receipts:
            raise ValueError("missing browser consumption receipts")
        for name in receipts:
            receipt = read_result(name)
            if (receipt["source_sha"] != build["source_sha"] or receipt["profile"] != build["profile"]
                    or receipt["expected_sha256"] != wasm or receipt["matched"] is not True
                    or not any(r["status"] == 200 and r["sha256"] == wasm for r in receipt["received"])):
                raise ValueError("browser did not consume the recorded WASM")
        executables["target/debug/rhwp"] = {
            "sha256": None, "bytes": None, "source": ".github/workflows/render-diff.yml",
        }

        canvas = read_result(RESULTS + "results.json")
        pdf = read_result(RESULTS + "pdf-results.json")
        canvas_cfg, pdf_cfg = canvas["config"], pdf["config"]
        canvas_pages = first_page_rows(canvas, canvas_cfg["fixtures"])
        pdf_pages = first_page_rows(pdf, pdf_cfg["fixtures"])
        if (not flag(pdf_cfg["directPdfGate"]) or not flag(pdf_cfg["directPdfEnabled"])
                or not set(pdf_cfg["directPdfFixtures"]) <= set(pdf_cfg["fixtures"])):
            raise ValueError("missing or invalid direct PDF gate selection")
        if set(origin["fixture_blobs"]) != set(canvas_cfg["fixtures"]) | set(pdf_cfg["fixtures"]):
            raise ValueError("fixture list differs from audited source tree")
        for fixture, blob in origin["fixture_blobs"].items():
            match(MEMBER, fixture)
            match(SHA, blob)

        tracks = {}
        for backend, targets, results, comparison, file_map, limit in (
            ("canvas", canvas_cfg["fixtures"], canvas_pages, None, None, canvas_cfg["maxDiffRatio"]),
            ("direct_pdf", pdf_cfg["directPdfFixtures"], pdf_pages, "directComparison",
             "directArtifactFiles", pdf_cfg["directMaxDiffRatio"]),
            ("browser_pdf", pdf_cfg["fixtures"], pdf_pages, "reportComparison",
             "artifactFiles", pdf_cfg["maxDiffRatio"]),
        ):
            pages = []
            for fixture in targets:
                raw = results.get(fixture)
                metrics = (raw.get(comparison) if comparison else raw) if raw is not None else None
                if backend != "canvas" and raw is not None:
                    if flag(raw["directExpected"]) != (fixture in pdf_cfg["directPdfFixtures"]):
                        raise ValueError("PDF result disagrees with direct fixture selection")
                status = "unmeasured"
                if metrics is not None:
                    if backend == "canvas":
                        status = "pass" if flag(raw["pass"]) else "fail"
                    elif backend == "direct_pdf":
                        status = "fail" if flag(raw["directGateFailed"]) else "pass"
                    else:
                        status = "warning" if flag(raw["exceedsReportThreshold"]) else "reported"
                elif raw is not None:
                    status = "error"
                page_files = {}
                if raw and file_map:
                    for role, path in raw.get(file_map, {}).items():
                        member = "rhwp-studio/" + path
                        if not member.startswith(RESULTS):
                            raise ValueError("unexpected PDF evidence path")
                        if member not in files:
                            read_member(member, max_size=32_000_000)
                        page_files[role] = member
                pages.append({"fixture": fixture, "page": 1, "status": status,
                              "diff_ratio": ratio(metrics["diffRatio"]) if metrics else None,
                              "same_size": flag(metrics["sameSize"]) if metrics else None,
                              "files": page_files})
            config = canvas_cfg if backend == "canvas" else pdf_cfg
            tracks[backend] = {
                "source": RESULTS + ("results.json" if backend == "canvas" else "pdf-results.json"),
                "conditions": {"max_pages": 1, "scale": config["scale"],
                               "channel_tolerance": integer(config["channelTolerance"], 255),
                               "max_diff_ratio": ratio(limit) if limit is not None else None,
                               "raster_dpi": config.get("rasterDpi"),
                               "direct_fallback_raster_dpi":
                                   config.get("directFallbackRasterDpi") if backend == "direct_pdf" else None},
                "pages": pages,
            }
    return {"kind": "upstream_render_diff", "origin": origin, "files": files, "tracks": tracks,
            "build": {"profile": build["profile"], "executables": executables,
                      "build_receipt": BUILD + "build.json", "browser_receipts": receipts}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--origin", type=Path,
                        default=ROOT / "corpus/pr-evidence/render-diff-44925877031-1.json")
    args = parser.parse_args()
    if args.archive.stat().st_size > 32_000_000:
        parser.error("archive exceeds size limit")
    origin = read_json(args.origin)
    result = import_archive(args.archive.read_bytes(), origin.get("origin", origin))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
