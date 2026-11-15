"""Runs only in the credential-free measurement job. Raw outputs never leave it."""
import ast
import json
import os
import platform
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from core import *

REQUIRED = {"--file-target", "--font-environment", "--out", "--silhouette-only",
            "--rasterizer", "--wasm-pkg", "--compat", "--rhwp-bin", "--dpi", "--page"}

def probe(root):
    source = (root / "scripts/visual_sweep.py").read_text()
    tree = ast.parse(source)
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    if not REQUIRED <= strings:
        raise ValueError("unsupported sweep CLI contract")
    for name in ("visual_sweep_workers.py", "visual_sweep_images.py",
                 "visual_sweep_pdf.py", "visual_sweep_resume.py"):
        if not (root / "scripts" / name).is_file():
            raise ValueError("incomplete upstream checkout")
    return digest(source.encode())

def command(args, cwd, log=None, timeout=3600):
    # Never use a shell or print supplied document paths into public output.
    with open(log or os.devnull, "wb") as stream:
        return subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                              timeout=timeout, check=False).returncode

def inventory(extra_font_root=None):
    values = {"platform": platform.platform(), "python": sys.version,
              "image": os.environ.get("ImageVersion", "unavailable")}
    for name, args in {
        "rust": ["rustc", "--version"], "node": ["node", "--version"],
        "cargo": ["cargo", "--version"], "wasm_pack": ["wasm-pack", "--version"],
        "python_packages": [sys.executable, "-m", "pip", "freeze"],
        "chrome": ["google-chrome", "--version"],
    }.items():
        try:
            p = subprocess.run(args, capture_output=True, timeout=30, check=False)
            values[name] = digest(p.stdout + p.stderr)
        except (OSError, subprocess.TimeoutExpired):
            values[name] = None
    fonts = []
    for directory in (Path("/usr/share/fonts"), Path.home()/".local/share/fonts",
                      Path(extra_font_root) if extra_font_root else Path("/nonexistent")):
        if directory.exists():
            fonts += sorted(digest(p.read_bytes()) for p in directory.rglob("*")
                            if p.is_file() and p.suffix.lower() in (".ttf", ".otf", ".ttc"))
    values["installed_font_hashes"] = sorted(fonts)
    return digest(canonical(values))

def runtime_environment_digest(font_root, receipts):
    return digest(canonical({"inventory_sha256":inventory(font_root), "runtime_receipts":receipts}))

def consume(base, document, selected=False, backend=None):
    raw = read_json(base / "silhouette_manifest.json")
    if backend is not None:
        p = raw.get("provenance", {})
        run_metadata = read_json(base / "run_manifest.json")
        if (p.get("hwp", {}).get("sha256") != document["document"]["sha256"]
                or p.get("pdf", {}).get("sha256") != document["golden"]["sha256"]
                or p.get("layout_generation") != document["compat"]
                or p.get("raster_backend") != {"native":"native-skia","wasm":"wasm-canvas2d"}[backend]
                or p.get("comparison_profile") != "print" or run_metadata.get("dpi") != 96
                or raw.get("excluded_regions")):
            raise ValueError("output input/backend/protocol provenance mismatch")
    counts = raw.get("pr_review_gate", {}).get("document_page_counts") or {}
    metrics = raw.get("metrics", [])
    row = {"id": document["id"], "status": "failed",
           "pdf_pages": counts.get("pdf"), "rendered_pages": counts.get("rhwp"), "scores": []}
    # Never publish diagnostic strings, image paths, HTML, render trees or source text.
    for item in metrics:
        row["scores"].append({"page": item["page"], "raw": item["silhouette_raw_match_percent"]})
    expected = {1} if selected else set(range(1, document["pages"]+1))
    if raw.get("radius_px") != 2 or raw.get("silhouette_method") != "threshold_boundary_color_support_v1":
        raise ValueError("unsupported metric protocol")
    if (raw.get("run_state") == "complete" and set(raw.get("completed_pages", [])) == expected
            and {p["page"] for p in row["scores"]} == expected
            and counts.get("pdf") == document["pages"]):
        row["status"] = "partial" if selected else "complete"
    return row


def materialize(root, documents):
    """Fetch only hash-pinned approved assets into ignored, disposable corpus/cache."""
    assets = {}
    for d in documents:
        for asset in [d["document"], d["golden"], *d["fonts"]]:
            if asset["path"] in assets and assets[asset["path"]] != asset:
                raise ValueError("conflicting asset contract")
            assets[asset["path"]] = asset
        if d["font_environment"]["path"] is not None:
            assets[d["font_environment"]["path"]] = d["font_environment"]
    for asset in assets.values():
        target = safe_path(root, asset["path"])
        if target.is_file() and digest(target.read_bytes()) == asset["sha256"]:
            continue
        source = asset["source"]
        parsed = urllib.parse.urlsplit(source)
        if parsed.hostname not in {"raw.githubusercontent.com", "cdn.jsdelivr.net"} or parsed.username or parsed.port:
            raise ValueError("asset origin rejected")
        if not (re.fullmatch(r"https://raw.githubusercontent.com/edwardkim/rhwp/[0-9a-f]{40}/(?:samples|pdf|mydocs)/[^?#]+", source)
                or re.fullmatch(r"https://cdn.jsdelivr.net/gh/(?:fonts-archive/(?:KoPubBatang|KoPubDotum)@[0-9a-f]{40}/KoPub[A-Za-z-]+\.ttf|projectnoonnu/noonfonts_2104@1\.0/HANBatang\.woff)", source)):
            raise ValueError("asset source outside allowed immutable origins")
        with urllib.request.urlopen(source, timeout=60) as response:
            data = response.read(32*1024*1024+1)
        if len(data) > 32*1024*1024 or digest(data) != asset["sha256"]:
            raise ValueError("downloaded asset hash mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    # Match upstream's deterministic WOFF container conversion; never publish either font.
    for asset in assets.values():
        if asset["path"].endswith(".woff"):
            from fontTools.ttLib import TTFont
            source = safe_file(root, asset["path"])
            font = TTFont(source, recalcTimestamp=False)
            try:
                font.flavor = None
                font.save(str(source)+".ttf", reorderTables=False)
            finally:
                font.close()

def run(upstream, corpus, destination, expected_sha):
    upstream, corpus, destination = map(lambda p: Path(p).resolve(), (upstream, corpus, destination))
    documents = manifest(corpus, verify=False)["documents"]
    result = {"schema_version": 1, "environment_sha256": None, "build_sha256": None,
              "backends": {b: empty_backend() for b in BACKENDS}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = destination.parent / "private"
    work.mkdir(exist_ok=True)
    runtime_receipts = []
    stage = "checkout-contract"
    try:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
        if actual != match(SHA, expected_sha):
            raise ValueError("upstream SHA mismatch")
        probe(upstream)
        result["environment_sha256"] = inventory()
        if not documents:
            for b in BACKENDS:
                result["backends"][b]["status"] = "empty"
            return result
        stage = "approved-asset-verification"
        materialize(corpus, documents)
        manifest(corpus)  # Verify actual bytes before any renderer receives inputs.
        # Exact approved files only; builds and raw captures remain in this disposable job.
        builds = [
            ["cargo", "build", "--locked", "--release", "--bin", "rhwp", "--features", "native-skia"],
            ["sh", "scripts/wasm-pack-locked.sh", "--target", "web", "--release"],
            ["npm", "ci", "--prefix", "rhwp-studio"],
        ]
        for i, args in enumerate(builds):
            stage = ("native-build", "wasm-build", "browser-dependencies")[i]
            log = work/f"build-{i}.log"
            if command(args, upstream, log) != 0:
                for line in log.read_text(errors="replace").splitlines()[-60:]:
                    print("build diagnostic: " + repr(line), flush=True)
                raise ValueError("producer build failed")
        help_result = subprocess.run([sys.executable, "scripts/visual_sweep.py", "--help"],
                                     cwd=upstream, capture_output=True, timeout=60)
        if help_result.returncode or not all(f.encode() in help_result.stdout for f in REQUIRED):
            raise ValueError("runtime CLI contract failed")
        binary = upstream/"target/release/rhwp"
        package = upstream/"pkg"
        result["build_sha256"] = digest(canonical({
            name: digest(path.read_bytes()) for name, path in {
                "native": binary, "wasm": package/"rhwp_bg.wasm", "javascript": package/"rhwp.js",
                "cargo_lock": upstream/"Cargo.lock",
                "npm_lock": upstream/"rhwp-studio/package-lock.json",
            }.items()}))
        result["environment_sha256"] = inventory(corpus/"cache/fonts")
        for backend in BACKENDS:
            rows, codes = [], []
            for d in documents:
                def invoke(smoke):
                    manifest(corpus)  # Recheck inputs after build and before each comparison.
                    out = work/backend/("smoke" if smoke else "full")/d["id"]
                    args = [sys.executable, "scripts/visual_sweep.py",
                            "--silhouette-only", "--rasterizer", "png", "--dpi", "96",
                            "--compat", d["compat"], "--rhwp-bin", str(binary),
                            "--out", str(out), "--file-target", d["id"],
                            str(safe_file(corpus, d["document"]["path"])),
                            str(safe_file(corpus, d["golden"]["path"]))]
                    if d["font_environment"]["path"] is not None:
                        args += ["--font-environment", str(safe_file(corpus, d["font_environment"]["path"]))]
                    for directory in sorted({str(safe_file(corpus, f["path"]).parent) for f in d["fonts"]}):
                        args += ["--font-path", directory]
                    if backend == "wasm":
                        args += ["--wasm-pkg", str(package)]
                    if smoke:
                        args += ["--page", "1"]
                    code = command(args, upstream, work/f"{backend}-{d['id']}-{'smoke' if smoke else 'full'}.log")
                    base = out/d["id"]
                    row = consume(base, d, selected=smoke, backend=backend)
                    if not smoke:
                        raw = read_json(base/"silhouette_manifest.json")
                        metadata = base/("native-export.json" if backend == "native" else "wasm-export-complete.json")
                        runtime_receipts.append({"id":d["id"], "backend":backend,
                            "upstream_provenance":raw.get("provenance"),
                            "export_receipt_sha256":digest(metadata.read_bytes())})
                    return code, row
                try:
                    smoke_code, smoke_row = invoke(True)
                    if smoke_code not in (0, 1) or smoke_row["status"] != "partial":
                        raise ValueError("smoke failed")
                    code, row = invoke(False)
                    # Exit 1 is a quality warning only when complete manifests prove coverage.
                    if code not in (0, 1):
                        row["status"] = "failed"
                    codes.append(code)
                    rows.append(row)
                except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                    codes.append(2)
                    rows.append({"id": d["id"], "status": "failed", "pdf_pages": None,
                                 "rendered_pages": None, "scores": []})
            complete = all(r["status"] == "complete" for r in rows)
            result["backends"][backend] = {
                "status": "complete" if complete else "partial" if any(r["scores"] for r in rows) else "failed",
                "exit_code": max(codes), "quality_alert": any(c == 1 for c in codes) or
                    any(s["raw"] < 90 for r in rows for s in r["scores"]) or
                    any(r["pdf_pages"] != r["rendered_pages"] for r in rows),
                "documents": rows}
        # Includes upstream font_supply/native_webfont_fallback and actual export receipts,
        # not only the declared pre-run font files.
        result["environment_sha256"] = runtime_environment_digest(corpus/"cache/fonts", runtime_receipts)
        validate_measurement(result, documents)
        return result
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("Measurement stage failed: " + stage + " (" + type(error).__name__ + ")", flush=True)
        for b in BACKENDS:
            result["backends"][b]["status"] = "failed"
        return result
    finally:
        write_json(destination, result)

if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: adapter.py UPSTREAM CORPUS RESULT SHA")
    run(*sys.argv[1:])
