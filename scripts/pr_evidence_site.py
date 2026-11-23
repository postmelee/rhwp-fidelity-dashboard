"""Display historical PR evidence outside the release ledger."""
from html import escape
from pathlib import PurePosixPath
from urllib.parse import quote

from cohort_site import page
from core import HASH, SHA, exact, integer, match, read_json, write_json
from pr_evidence import BACKENDS
from presentation import LABELS
from preview_presentation import UPSTREAM, table

UNKNOWN = "Unknown"
PRINT_CONDITIONS = {"document_sha256", "reference_sha256", "backend", "profile",
                    "dpi", "compat", "settings_sha256"}


def coverage_row(key, label, target, measured, mismatch, unmeasured):
    return {"backend": key, "label": label, "target": target, "measured": measured,
            "page_count_mismatch_docs": mismatch, "unmeasured": unmeasured}


def counts(docs, pages):
    return {"documents": docs, "pages": pages}


def coverage_table(coverage):
    def shown(value):
        return UNKNOWN if value is None else f'{value["documents"]} / {value["pages"]}'

    return table("Coverage · documents / pages",
                 ["Check or backend", "Target", "Measured", "Page count mismatches (docs)", "Unmeasured"],
                 [[r["label"], shown(r["target"]), shown(r["measured"]),
                   UNKNOWN if r["page_count_mismatch_docs"] is None else r["page_count_mismatch_docs"],
                   shown(r["unmeasured"])] for r in coverage], cards=True)


def render_diff(record, ledger):
    o = record["origin"]
    source = match(SHA, o["source_sha"])
    tree = match(SHA, o["source_tree_sha"])
    pr = integer(o["pr"], 10**9)
    run = f'{UPSTREAM}/actions/runs/{integer(o["run_id"], 10**14)}'
    body = (f'<p>PR <a href="{UPSTREAM}/pull/{pr}">#{pr}</a> · '
            f'<a href="{run}/attempts/{integer(o["attempt"])}">Run {o["run_id"]} · attempt {o["attempt"]}</a> · '
            f'<a href="{run}/job/{integer(o["job_id"], 10**14)}">Job {o["job_id"]}</a> · '
            f'<a href="{run}/artifacts/{integer(o["artifact_id"], 10**14)}">Artifact {o["artifact_id"]}</a></p>'
            f'<p>PR head <code>{match(SHA, o["pr_head"])}</code> · Build source '
            f'<a href="{UPSTREAM}/commit/{source}"><code>{source}</code></a> · Tree <code>{tree}</code></p>'
            f'<p>ZIP SHA-256 <code>{match(HASH, o["artifact_sha256"])}</code> · '
            f'<a href="{ledger}">Numeric ledger and file hashes</a></p>')
    if "merge_sha" in o:
        merged = match(SHA, o["merge_sha"])
        merged_tree = match(SHA, o["merge_tree_sha"])
        relation = "Matches tested tree" if merged_tree == tree else "Differs from tested tree"
        body += (f'<p>Merged commit <a href="{UPSTREAM}/commit/{merged}"><code>{merged}</code></a> · '
                 f'Tree <code>{merged_tree}</code> · {relation}</p>')
    coverage = []
    decisions = {}
    details = []
    for backend, label in BACKENDS.items():
        if backend == "hancom_print":
            coverage.append(coverage_row(backend, label, None, counts(0, 0), None, None))
            decisions[backend] = {"no evidence": 0}
            continue
        track = record["tracks"][backend]
        pages = track["pages"]
        measured = sum(p["diff_ratio"] is not None for p in pages)
        missing = len(pages) - measured
        coverage.append(coverage_row(backend, label, counts(len(pages), len(pages)),
                                     counts(measured, measured), None, counts(missing, missing)))
        decisions[backend] = {status: sum(p["status"] == status for p in pages)
                              for status in ("pass", "fail", "warning", "reported", "error", "unmeasured")}
        for p in pages:
            size = UNKNOWN if p["same_size"] is None else "Same" if p["same_size"] else "Different"
            difference = "Unmeasured" if p["diff_ratio"] is None else f'{p["diff_ratio"] * 100:.5f}'
            details.append([label, p["fixture"], p["page"], p["status"], size, difference])
    results = [[BACKENDS[b], status.title(), total] for b, decision in decisions.items()
               for status, total in decision.items() if total or status == "no evidence"]
    executables = table("Build executables", ["File", "SHA-256"],
                        [[name, r["sha256"] or UNKNOWN] for name, r in record["build"]["executables"].items()],
                        cards=True)
    body += (coverage_table(coverage) + table("Producer decisions", ["Check", "Result", "Pages"], results) +
             '<p>The selected scope is page 1 of each target fixture. The JSON reports image dimensions. '
             'Document page counts and an upstream base measurement are unavailable for this run.</p>' +
             table("CI page results", ["Check", "Fixture", "Page", "Result", "Image size",
                                       "Pixel difference (%)"], details, cards=True) +
             '<details><summary>Build and runtime evidence</summary>' + executables +
             f'<p>Matching WASM browser receipts · {len(record["build"]["browser_receipts"])}</p></details>')
    title = f"Upstream Render Diff · PR #{pr}"
    return title, body, {"coverage": coverage, "decisions": decisions,
                         "run_id": o["run_id"], "job_id": o["job_id"],
                         "attempt": o["attempt"], "artifact_id": o["artifact_id"], "pr": pr}


def common_pages(base, head):
    """Deltas require the same input, oracle, backend and measurement settings."""
    if (set(base["conditions"]) != PRINT_CONDITIONS or not all(base["conditions"].values())
            or base["conditions"] != head["conditions"]
            or base["counts"]["pdf"] != head["counts"]["pdf"]
            or any(s["counts"]["rhwp"] != s["counts"]["pdf"] for s in (base, head))):
        return set()
    return {p for p in base["scores"].keys() & head["scores"].keys()
            if 1 <= int(p) <= base["counts"]["pdf"]
            and all(type(s["scores"][p]) in (int, float) and 0 <= s["scores"][p] <= 100
                    for s in (base, head))}


def visual_sweep(record, ledger):
    revision = match(SHA, record["revision"])
    pr = integer(record["pr"], 10**9)
    body = (f'<p>Historical <a href="{UPSTREAM}/pull/{pr}">PR #{pr}</a> · {escape(record["document"])} · '
            'Independent Hancom Print · 96 DPI</p>'
            f'<p><a href="{UPSTREAM}/blob/{revision}/{quote(record["comparison_tsv"])}">Upstream comparison TSV</a> · '
            f'<a href="{ledger}">Numeric ledger and file hashes</a></p>')
    coverage, lows, comparisons, detail_tables, low_links = [], [], {}, [], []
    for backend, label in LABELS.items():
        base, head = (record["series"][side][backend] for side in ("base", "head"))
        common = common_pages(base, head)
        comparisons[backend] = len(common)
        for side, series in (("base", base), ("head", head)):
            scores = {p: raw for p, raw in series["scores"].items() if raw is not None}
            count = len(scores)
            target = series["counts"]["pdf"]
            absent = target - count
            key = f"{backend}-{side}"
            name = f"{label} · {side}"
            coverage.append(coverage_row(key, name, counts(1, target), counts(int(count > 0), count),
                                         int(series["counts"]["rhwp"] != target), counts(int(absent > 0), absent)))
            below = sorted((int(p) for p, raw in scores.items() if raw < 90))
            low = {"backend": backend, "side": side, "below_90_documents": int(bool(below)),
                   "below_90_pages": len(below), "page_numbers": below, "lowest": None}
            if scores:
                pg = min(scores, key=lambda p: (scores[p], int(p)))
                low["lowest"] = {"page": int(pg), "raw": scores[pg], "anchor": f"{backend}-page-{pg}"}
                low_links.append(f'<li>{name} · <a href="#{backend}-page-{pg}">page {pg} · '
                                 f'{scores[pg]:.5f}%</a></li>')
            lows.append(low)
        page_keys = sorted(base["scores"].keys() | head["scores"].keys(), key=int)
        detail = []
        for p in page_keys:
            left, right = base["scores"].get(p), head["scores"].get(p)
            detail.append([p, "Unmeasured" if left is None else f"{left:.5f}",
                           "Unmeasured" if right is None else f"{right:.5f}",
                           f"{right - left:+.5f}" if p in common else "Unavailable"])
        detail_tables.append(
            f"<h2>{label}</h2><p>Comparable base/head pages · {len(common)}</p>" +
            table("HWPX page scores", ["Page", "Base raw (%)", "Head raw (%)", "Head minus base (pp)"],
                  detail, cards=True, row_ids=[f"{backend}-page-{p}" for p in page_keys]))
    low_rows = [[f'{LABELS[r["backend"]]} · {r["side"]}', r["below_90_documents"],
                 r["below_90_pages"], ", ".join(map(str, r["page_numbers"])) or "—"] for r in lows]
    body += (coverage_table(coverage) + table("Raw silhouette below 90%",
             ["Backend", "Documents", "Pages", "Page numbers"], low_rows, cards=True) +
             "<h2>Lowest raw scores</h2><ul>" + "".join(low_links) + "</ul>" + "".join(detail_tables))
    return f"Hancom Visual Sweep · PR #{pr}", body, {"pr": pr, "coverage": coverage,
                                                     "raw": lows, "common_pages": comparisons}


def pinned_link(revision, name, suffix):
    path = PurePosixPath(name)
    if (path.as_posix() != name or ".." in path.parts or not path.is_relative_to("mydocs/pr/assets")
            or path.suffix != suffix):
        raise ValueError("Invalid historical evidence path")
    return f"{UPSTREAM}/blob/{revision}/{quote(name)}"


def historical_page_preview(record, ledger):
    exact(record, "schema_version kind pr revision engine_sha producer_sha256 document source_sha256 "
          "pdf_sha256 reference_page hancom_pages native_pages raw_percent dpi hancom_build png evidence")
    if record["schema_version"] != 1:
        raise ValueError("Unsupported historical page preview")
    revision = match(SHA, record["revision"])
    engine = match(SHA, record["engine_sha"])
    producer = match(HASH, record["producer_sha256"])
    source_sha = match(HASH, record["source_sha256"])
    pdf_sha = match(HASH, record["pdf_sha256"])
    pr = integer(record["pr"], 10**9)
    reference_page = integer(record["reference_page"])
    hancom_pages = integer(record["hancom_pages"])
    native_pages = integer(record["native_pages"])
    dpi = integer(record["dpi"], 2400)
    raw = record["raw_percent"]
    if (not 1 <= reference_page <= min(hancom_pages, native_pages) or native_pages == hancom_pages
            or not dpi or type(raw) not in (int, float) or not 0 <= raw <= 100):
        raise ValueError("Historical preview requires one scored page from a page-count mismatch")

    exact(record["png"], "hancom native comparison")
    exact(record["evidence"], "intake manifest path_migration partial_tsv later_validation")
    cards = []
    for key, title in (("hancom", "Hancom Print"), ("native", "Native Skia"),
                       ("comparison", "Side-by-side review")):
        asset = record["png"][key]
        exact(asset, "path sha256 width height")
        url = pinned_link(revision, asset["path"], ".png")
        checksum = match(HASH, asset["sha256"])
        width, height = integer(asset["width"]), integer(asset["height"])
        if not width or not height:
            raise ValueError("Invalid historical PNG size")
        cards.append(f'<article><h3>{title}</h3><p>{width} × {height} px</p>'
                     f'<p><a href="{url}">Open {title} PNG at upstream</a></p>'
                     f'<p>SHA-256 <code>{checksum}</code></p></article>')
    evidence_links = []
    for key, label, suffix in (("intake", "Original review and synthetic fixture", ".md"),
                               ("manifest", "Producer and Print evidence", ".json"),
                               ("path_migration", "Reference PDF path and byte identity", ".json"),
                               ("partial_tsv", "Partial one-page TSV", ".tsv"),
                               ("later_validation", "Later complete upstream validation", ".md")):
        asset = record["evidence"][key]
        exact(asset, "path sha256")
        match(HASH, asset["sha256"])
        url = pinned_link(revision, asset["path"], suffix)
        evidence_links.append(f'<li><a href="{url}">{label}</a></li>')

    body = (f'<p>Historical <a href="{UPSTREAM}/pull/{pr}">PR #{pr}</a> · {escape(record["document"])}</p>'
            f'<section id="reference-page-{reference_page}"><h2>Reference page {reference_page}</h2>'
            f'<p><strong>Partial result · page-count mismatch</strong>. Hancom Print has {hancom_pages} pages '
            f'and Native Skia produced {native_pages}. The recorded raw silhouette score for this reference page is '
            f'{raw:.2f}%. WASM Canvas2D is unmeasured for this capture.</p>'
            f'<p>Initial review checkout <a href="{UPSTREAM}/commit/{engine}"><code>{engine}</code></a> · '
            f'Hancom {escape(record["hancom_build"])} · Print · {dpi} DPI</p>'
            '<div class="cards">' + "".join(cards) + '</div></section>'
            '<h2>Run provenance</h2><dl>'
            f'<dt>Native binary SHA-256</dt><dd><code>{producer}</code></dd>'
            f'<dt>Source SHA-256</dt><dd><code>{source_sha}</code></dd>'
            f'<dt>Print PDF SHA-256</dt><dd><code>{pdf_sha}</code></dd></dl>'
            '<p>This early review is documented in the PR evidence history. Release coverage uses its own measurement records.</p>'
            f'<p><a href="{ledger}">Evidence index and hashes</a></p><ul>' + "".join(evidence_links) + "</ul>")
    return f"Historical page preview · PR #{pr}", body, {"pr": pr, "reference_page": reference_page}


def build(folder, out):
    index = []
    links = []
    presenters = {"upstream_render_diff": render_diff, "submitted_visual_sweep": visual_sweep,
                  "historical_page_preview": historical_page_preview}
    for source in sorted(folder.glob("*.json")):
        record = read_json(source)
        ledger = f"pr-evidence/{source.name}"
        view = f"pr-evidence-{source.stem}.html"
        title, body, summary = presenters[record["kind"]](record, ledger)
        section, label = (("history", "Run history") if record["kind"] == "historical_page_preview"
                          else ("renderers", "Renderer comparison"))
        (out / view).write_text(page(title, body, section=section, section_label=label), encoding="utf-8")
        write_json(out / ledger, record)
        index.append({"kind": record["kind"], "record": ledger, "view": view, **summary})
        links.append(f'<li><a href="{escape(view)}">{escape(title)}</a></li>')
    return index, ('<h3>Pull request evidence</h3><ul>' + "".join(links) + "</ul>") if links else ""
