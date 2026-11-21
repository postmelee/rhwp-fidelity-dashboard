"""Runner-local cache experiment on two receipt-backed, two-page inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from receipt_cohort import contract, verify_receipt
from core import canonical, digest

UPSTREAM = "2480af27df441ffd199cc24602afddbd2d13dcfe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(repo, binary):
    assert subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip() == UPSTREAM
    sys.path.insert(0, str(repo / "scripts"))
    import visual_sweep as sweep
    from visual_sweep_pdf import rasterize
    config, _ = contract()
    verify_receipt(config)
    original, alternate = [d for d in config["documents"] if d["pages"] == 2][:2]
    for d in (original, alternate):
        assert sha(repo / d["input"]) == d["source_sha256"]
        assert sha(repo / d["pdf"]) == d["pdf_sha256"]
    source = repo / original["input"]
    pdf = repo / original["pdf"]
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        reference = work / "upstream"
        subprocess.run([sys.executable, "scripts/visual_sweep.py", "--silhouette-only", "--key", "sample",
                        "--hwp", str(source), "--pdf", str(pdf), "--rhwp-bin", str(binary),
                        "--dpi", "96", "--compat", "2022", "--page-workers", "1",
                        "--font-path", "/usr/share/fonts/truetype/dejavu", "--out", str(reference)], cwd=repo, check=True)
        root = reference / "sample"
        manifest = json.loads((root / "silhouette_manifest.json").read_text())
        assert manifest["run_state"] == "complete" and manifest["completed_pages"] == [1, 2]
        assert manifest["dpi"] == 96 and manifest["tsv_sha256"] == sha(root / "silhouette.tsv")
        provenance = manifest["provenance"]
        assert provenance["hwp"]["sha256"] == sha(source) and provenance["pdf"]["sha256"] == sha(pdf)
        assert provenance["raster_backend"] == "native-skia" and provenance["comparison_profile"] == "print"
        # A second runnable ELF with different bytes and identical rendering behavior.
        marker = work / "marker"
        marker.write_bytes(b"cache-pilot")
        changed = work / "rhwp-marked"
        subprocess.run(["objcopy", "--add-section", ".cachepilot=" + str(marker), binary, changed], check=True)
        assert sha(binary) != sha(changed)

        def experiment(cache, executable, golden, exact_rgb):
            trace = {}
            def stage(name, inputs, produce):
                key = digest(canonical(inputs))
                path = cache / name / key
                receipt = path / "outputs.json"
                if receipt.is_file():
                    outputs = json.loads(receipt.read_text())
                    assert outputs and all(sha(path / n) == h for n, h in outputs.items())
                    trace[name] = "reused"
                else:
                    path.mkdir(parents=True)
                    files = produce(path)
                    outputs = {f.name: sha(f) for f in files}
                    receipt.write_bytes(canonical(outputs))
                    trace[name] = "executed"
                return path, outputs

            def render(path):
                result = subprocess.check_output([executable, "export-png", source, "--profile", "print",
                        "--compat", "2022", "--dpi", "96", "--scale", "1", "--json", "-o", path], cwd=repo)
                meta = json.loads(result)
                assert meta["backend"] == "native-skia" and meta["comparisonProfile"] == "print"
                assert sorted(p["page"] for p in meta["pages"]) == [0, 1]
                files = []
                for item in meta["pages"]:
                    dest = path / f'page-{item["page"]+1}.png'
                    Path(item["path"]).replace(dest)
                    files.append(dest)
                return files

            def raster(path):
                rasterize(golden, 96, path / "pdf")
                files = sorted(path.glob("pdf-*.png"))
                assert len(files) == 2
                return files

            images, rendered = stage("render", [sha(source), sha(executable), "native-skia", "print", "2022", 96], render)
            refs, reference_hashes = stage("reference", [sha(golden), 96, UPSTREAM], raster)
            def score(path):
                pairs = [(i, images / f"page-{i}.png", refs / f"pdf-{i:03d}.png") for i in (1, 2)]
                if exact_rgb:
                    # Diagnostic second metric: exact RGB channel difference over a common white canvas.
                    from PIL import Image, ImageChops
                    lines = ["page\tdiffering_rgb_channels\ttotal_rgb_channels"]
                    for page, left, right in pairs:
                        with Image.open(left) as a, Image.open(right) as b:
                            size = tuple(map(max, zip(a.size, b.size)))
                            canvases = [Image.new("RGB", size, "white") for _ in range(2)]
                            for canvas, img in zip(canvases, (a, b)):
                                canvas.paste(img.convert("RGB"))
                            histogram = ImageChops.difference(*canvases).histogram()
                            diff = sum(n for channel, n in enumerate(histogram) if channel % 256)
                            lines.append(f"{page}\t{diff}\t{3 * size[0] * size[1]}")
                    tsv = path / "channel-difference.tsv"
                    tsv.write_text("\n".join(lines) + "\n")
                    return [tsv]
                m = sweep.write_silhouette_tsv(pairs, path, "sample")
                assert m["dpi"] is None and m["tsv_sha256"] == sha(path / "silhouette.tsv")
                return [path / "silhouette.tsv"]
            _, scores = stage("compare", [rendered, reference_hashes, UPSTREAM, exact_rgb], score)
            return trace, [rendered, reference_hashes, scores]

        report = {"upstream_sha": UPSTREAM, "document_tsv_sha256": manifest["tsv_sha256"], "dpi": 96,
                  "native_sha256": sha(binary), "marked_native_sha256": sha(changed),
                  "document_id": original["id"], "alternate_pdf_sha256": sha(repo / alternate["pdf"]),
                  "source_sha256": sha(source), "pdf_sha256": sha(pdf), "cases": {}}
        for name, exe, ref, mask, expected in [
                ("cold", binary, pdf, False, (1,1,1)), ("warm", binary, pdf, False, (0,0,0)),
                ("different-pdf", binary, repo / alternate["pdf"], False, (0,1,1)),
                ("different-metric", binary, pdf, True, (0,0,1)),
                ("different-executable", changed, pdf, False, (1,0,0))]:
            trace, actual = experiment(work / "cache", exe, ref, mask)
            clean_trace, clean = experiment(work / ("clean-" + name), exe, ref, mask)
            assert actual == clean and all(v == "executed" for v in clean_trace.values())
            assert [v == "executed" for v in trace.values()] == list(expected), (name, trace)
            report["cases"][name] = {"stages": trace, "clean_match": True, "output_hashes": actual}
        print("CACHE_PILOT " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    upstream = Path(sys.argv[1]).resolve()
    main(upstream, upstream / "target/release/rhwp")
