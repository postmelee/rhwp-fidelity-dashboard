"""Presentation of validated immutable records; never combines separate attempts."""
import html
import json
from pathlib import Path
import os
import re
from core import coverage
from presentation import LABELS, number, paired_pages

EVIDENCE_REV = "c198dc3ef167df9b84b6825606e98f618fb628f7"
SITE = Path(__file__).with_name("site")
REPO = "https://github.com/postmelee/rhwp-fidelity-dashboard"
UPSTREAM = "https://github.com/edwardkim/rhwp"
TABS = (
    ("overview", "Overview"),
    ("renderers", "Renderer comparison"),
    ("documents", "Documents & pages"),
    ("history", "Run history"),
    ("methods", "Method & sources"),
)
esc = html.escape


def table(title, headers, rows, *, cards=False):
    head = "".join(
        f'<th scope="col"><button type="button" class="sort" hidden>{esc(h)}</button>'
        f'<span>{esc(h)}</span></th>' for h in headers
    )
    def value_cell(h, value):
        content = esc(str(value))
        if h == "Skia minus Canvas2D (points)" and value != "unavailable":
            delta = float(value)
            side = "positive" if delta >= 0 else "negative"
            content += (f'<span class="gap-track {side}" aria-hidden="true">'
                        f'<i style="width:{min(abs(delta), 100) / 2:.5f}%"></i></span>')
        return f'<td data-label="{esc(h)}">{content}</td>'

    body = "".join(
        '<tr>' + ''.join(value_cell(h, value) for h, value in zip(headers, row)) + '</tr>'
        for row in rows
    )
    if not body:
        body = f'<tr><td colspan="{len(headers)}">No rows</td></tr>'
    return (
        f'<div class="scroll" tabindex="0" role="region" aria-label="{esc(title)}">'
        f'<table class="{"page-grid" if cards else "metric-grid"}"><caption>{esc(title)}</caption><thead><tr>{head}</tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
    )


def label(record):
    if record is None:
        return "Unavailable"
    return (f'{esc(record["source_ref"])} · <code>{record["upstream_sha"][:12]}</code> · '
            f'{esc(record["status"])} · {esc(record["resolved_at"])}')


def record_key(record):
    return f'{record["run_id"]}-{record["attempt"]}'


def run_link(record):
    return f'<a href="#run-{record_key(record)}">{label(record)}</a>'


def status_text(record, evidence):
    job = evidence.get("checkout_contract_job")
    if job:
        return (
            'Checkout contract failed · Scores unavailable · '
            f'<a href="{REPO}/actions/runs/{record["run_id"]}/job/{job}">Measurement log</a>'
        )
    return {
        "complete": "Measurement complete",
        "partial": "Partial measurement",
        "failed": "Measurement failed · no scores",
        "empty": "Empty corpus",
    }.get(record["status"], "Unmeasured")


def publication_text(record, evidence):
    job = evidence.get("pages_job")
    if not job:
        return "Unknown · no audited publish job"
    status = {
        "success": "Published · publish job succeeded",
        "failure": "Pages publish job failed",
    }.get(evidence["pages_result"], "Publish job " + evidence["pages_result"])
    return f'<a href="{REPO}/actions/runs/{record["run_id"]}/job/{job}">{esc(status)}</a>'


def metric_list(items):
    rows = "".join(f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>" for key, value in items)
    return f'<dl class="metrics">{rows}</dl>'


def decision_card(title, status, items, href, link_text):
    return (
        f'<article class="decision"><h3>{esc(title)}</h3>'
        f'<span class="badge">{esc(status)}</span>{metric_list(items)}'
        f'<a href="{esc(href)}">{esc(link_text)}</a></article>'
    )


def release_panel(sha, tag, attempts, docs):
    last = attempts[-1] if attempts else None
    complete = next((r for r in reversed(attempts) if r["status"] == "complete"), None)
    record = complete or last
    pairs = paired_pages(record, docs) if record else []
    measured = sorted((r for r in pairs if r[4] is not None), key=lambda r: -abs(r[4]))
    target = sum(d["pages"] for d in docs)
    state = {"complete": "Smoke complete", "partial": "Partial measurement",
             "failed": "Attempt failed", "empty": "Empty corpus"}
    heading = state.get(record["status"], "Unavailable") if record else "Unmeasured"
    compare = "#compare-" + record_key(record) if record else "#renderers"
    document = "#document-" + record_key(record) if record else "#documents"
    passing = sum(min(r[2], r[3]) >= 90 for r in measured)
    comparison = [
        ("Paired pages / target", f"{len(measured)}/{target}"),
        ("Both ≥90% / paired pages", f"{passing}/{len(measured)}" if measured else "Unmeasured"),
    ]
    wasm_pages = sum(len(doc["scores"]) for doc in record["measurement"]["backends"]["wasm"]["documents"]) if record else 0
    cards = [
        decision_card("Hancom Print fidelity", heading, comparison, compare, "Renderer scores"),
        decision_card("Browser renderers", "CanvasKit unmeasured", [
            ("WASM Canvas2D pages", f"{wasm_pages}/{target}"),
            ("Skia fidelity protocol", "Native CLI"),
        ], compare, "Backend coverage"),
        decision_card("Canvas tree output parity", "Render Diff unlinked", [
            ("Tree A", "PageRenderTree"), ("Tree B", "PageLayerTree"),
        ], "#methods", "Render Diff source"),
    ]
    source = f'<p>Measurement evidence: {run_link(record)}</p>' if record else ""
    if record:
        counts = []
        for key, name in (("wasm", "Canvas2D"), ("native", "Native Skia")):
            known, equal = page_count_evidence(record["measurement"]["backends"][key])
            counts.append(f"{name} {equal}/{known}" if known else f"{name} unavailable")
        source += ('<h4>Hancom page-count agreement</h4>'
                   f'<p>Matching / known documents · {" · ".join(counts)}</p>')
    if last and last != record:
        source += f'<p>Most recent attempt: {run_link(last)}</p>'
    body = (f'<h3 class="release-title">{esc(tag)} · {heading}</h3>'
            f'<div class="cards decisions">{"".join(cards)}</div>{source}')
    if measured:
        body += '<h4>Lowest page silhouette vs Hancom (%)</h4>'
        for name, index in (("Canvas2D", 2), ("Native Skia", 3)):
            value = min(row[index] for row in measured)
            body += (f'<div class="score-line"><span>{name}</span>'
                     f'<meter aria-label="{name} lowest paired page" min="0" max="100" value="{value}"></meter>'
                     f'<strong>{number(value)}%</strong></div>')
        names = {d["id"]: Path(d.get("document", {}).get("source", d["id"])).name for d in docs}
        rows = [(names[key], page, number(w), number(n), f"{delta:+.5f}") for key,page,w,n,delta in measured[:5]]
        body += table("Largest differences against the same Hancom page", [
            "Document", "Page", "Canvas2D", "Native Skia", "Skia minus Canvas2D (points)",
        ], rows, cards=True)
        body += f'<p>Equal scores / paired pages · {sum(r[4] == 0 for r in measured)}/{len(measured)} · <a href="{document}">All page results</a></p>'
    return f'<div class="release-view" id="release-{esc(sha)}">{body}</div>'


def release_groups(records, release):
    groups = {release["sha"]: []}
    tags = {release["sha"]: release["tag"]}
    stable = {release["sha"]}
    for record in records:
        sha = record["upstream_sha"]
        groups.setdefault(sha, []).append(record)
        if record["source_kind"] == "stable-release":
            stable.add(sha)
        if sha != release["sha"] and (sha not in tags or record["source_kind"] == "stable-release"):
            tags[sha] = record["source_ref"]

    def order(sha):
        version = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tags[sha])
        return (sha == release["sha"], sha in stable, tuple(map(int, version.groups())) if version else (),
                groups[sha][-1]["resolved_at"] if groups[sha] else "", sha)

    ordered = sorted(groups, key=order, reverse=True)
    return [(sha, tags[sha] if sha in stable else "Manual · " + tags[sha], groups[sha]) for sha in ordered]


def release_picker(groups):
    options = "".join(f'<option value="release-{esc(sha)}">{esc(tag)} · {esc(sha[:8])}</option>'
                      for sha, tag, _ in groups)
    return (f'<label class="release-picker" hidden>Release or tested revision '
            f'<select id="release-picker">{options}</select></label>')


def inventory_section(snapshot):
    items = [
        ("HWP / HWPX paths", f'{snapshot["source_paths"]:,}'),
        ("Distinct Git blobs", f'{snapshot["unique_blobs"]:,}'),
        ("Sources verified in audited Print receipt", str(snapshot["receipt_verified_sources"])),
    ]
    revision = snapshot["source_revision"]
    totals = [(root, counts["hwp"], counts["hwpx"]) for root, counts in snapshot["by_root"].items()]
    return (f'<h3>Corpus inventory</h3>{metric_list(items)}'
            f'<details><summary>Inventory by directory</summary>'
            f'{table("Source paths", ["Directory", "HWP", "HWPX"], totals, cards=True)}'
            f'<p><a href="{UPSTREAM}/tree/{revision}">Corpus revision · {revision[:12]}</a> · '
            f'<a href="{UPSTREAM}/blob/{revision}/{esc(snapshot["receipt_file"])}">Audited Print receipt</a></p>'
            '</details>')


def overview(records, docs, release, groups):
    latest_complete = next((r for r in reversed(records) if r["status"] == "complete"), None)
    latest_note = "Unmeasured" if latest_complete is None else run_link(latest_complete)
    if latest_complete and latest_complete["upstream_sha"] != release["sha"]:
        latest_note += f' · <a href="#release-{latest_complete["upstream_sha"]}">Release overview</a>'
    scope = (f'<p class="scope"><strong>Smoke scope</strong> · {len(docs)} approved documents · '
             f'{sum(d["pages"] for d in docs)} target pages</p>')
    return (scope + f'<p>Stable release observed {esc(release["observed_on"])} UTC: '
            f'<a href="{UPSTREAM}/releases/tag/{esc(release["tag"])}">{esc(release["tag"])}</a></p>'
            f'<p>Last recorded complete: {latest_note}</p>'
            + "".join(release_panel(sha, tag, attempts, docs) for sha, tag, attempts in groups))


def page_count_evidence(backend):
    known = [d for d in backend["documents"]
             if d["pdf_pages"] is not None and d["rendered_pages"] is not None]
    return len(known), sum(d["pdf_pages"] == d["rendered_pages"] for d in known)


def renderer_tables(record, docs):
    summary = []
    for key in ("wasm", "native"):
        backend = record["measurement"]["backends"][key]
        totals = coverage(backend, docs)
        known, equal = page_count_evidence(backend)
        rate = f"{equal}/{known} ({100*equal/known:.1f}%)" if known else "unavailable"
        summary.append([
            LABELS[key], backend["status"], f'{totals["measured_docs"]}/{len(docs)}',
            totals["failed_docs"], totals["skipped_docs"],
            f'{totals["measured_pages"]}/{totals["target_pages"]}',
            totals["failed_pages"], totals["skipped_pages"], totals["unmeasured_pages"], rate,
            len(docs)-known, number(totals["min"]), number(totals["p10"]),
            number(totals["median"]), totals["below90"] if totals["measured_pages"] else "unavailable",
            ("yes" if backend["quality_alert"] else "no") if totals["measured_pages"] else "unavailable",
        ])
    metrics = ["Backend", "Status", "Docs complete/target", "Docs failed", "Docs skipped",
               "Pages measured/target", "Pages failed", "Pages skipped", "Pages unmeasured",
               "Page-count equal/known docs", "Count unknown docs", "Lowest silhouette (%)",
               "P10 (%)", "Median (%)", "Pages below 90%", "Quality alert"]
    rows = list(zip(metrics, *summary))
    return table("Backend coverage and silhouette", ["Metric", *[LABELS[k] for k in ("wasm", "native")]], rows[1:])


def document_table(record, docs):
    backends = record["measurement"]["backends"]
    names = {d["id"]: Path(d.get("document", {}).get("source", d["id"])).name for d in docs}
    expected_pages = {d["id"]: d["pages"] for d in docs}
    results = {key: {d["id"]: d for d in backends[key]["documents"]} for key in ("wasm", "native")}
    pairs = sorted(paired_pages(record, docs), key=lambda row: (row[4] is None, -abs(row[4] or 0)))
    rows = []
    for doc_id, page, _, _, delta in pairs:
        values = []
        for key in ("wasm", "native"):
            result = results[key].get(doc_id)
            if result is None:
                values.append("unavailable")
                continue
            score = next((entry["raw"] for entry in result["scores"] if entry["page"] == page), None)
            if delta is None:
                rendered = result["rendered_pages"]
                expected = expected_pages[doc_id]
                values.append(f'{number(score)} · {result["status"]} · {rendered if rendered is not None else "?"}/{expected} pages')
            else:
                values.append(number(score))
        rows.append((names[doc_id], page, *values, f"{delta:+.5f}" if delta is not None else "unavailable"))
    return table("Document and page details", [
        "Document", "Page", "Canvas2D vs Hancom (%)", "Native Skia vs Hancom (%)", "Skia minus Canvas2D (points)",
    ], rows, cards=True)


def run_views(groups, docs, prefix, render):
    parts = []
    for sha, tag, attempts in groups:
        if not attempts:
            parts.append(f'<p data-release="{sha}" data-preferred="true">{esc(tag)} · Unmeasured</p>')
            continue
        preferred = next((r for r in reversed(attempts) if r["status"] == "complete"), attempts[-1])
        for record in reversed(attempts):
            key = record_key(record)
            current = record is preferred
            parts.append(
                f'<details id="{prefix}-{key}" data-release="{sha}" data-preferred="{str(current).lower()}"'
                f'{" open" if current else ""}><summary>{label(record)}</summary>'
                f'<p><a href="#run-{key}">Attempt {key} and provenance</a></p>{render(record, docs)}'
                + (f'<p><a href="#document-{key}">Document and page details</a></p>' if prefix == "compare" else "")
                + '</details>'
            )
    return "".join(parts)


def history_view(records, observations):
    if not records:
        return '<p>Recorded attempts · 0</p>'
    parts = [
        '<label for="filter" hidden>Measurement status</label> '
        '<select id="filter" hidden><option value="">All</option>'
        '<option value="complete">Complete</option><option value="partial">Partial</option>'
        '<option value="failed">Failed</option><option value="empty">Empty</option></select>'
        '<label hidden><input type="checkbox" id="all-history"> Show all releases</label>'
        '<p id="filter-result" role="status"></p>'
    ]
    for record in reversed(records):
        key = record_key(record)
        audit = observations.get((record["run_id"], record["attempt"]), {})
        fields = {
            "Engine SHA": record["upstream_sha"], "Measurement revision": record["dashboard_sha"],
            "Source": record["source_kind"], "Protocol": record["protocol"],
            "Corpus SHA-256": record["corpus_sha256"], "Font SHA-256": record["font_sha256"],
            "Adapter SHA-256": record["adapter_sha256"],
            "Environment SHA-256": record["measurement"]["environment_sha256"],
            "Build SHA-256": record["measurement"]["build_sha256"],
        }
        hashes = "".join(f'<dt>{name}</dt><dd><code>{esc(value or "unavailable")}</code></dd>'
                         for name, value in fields.items())
        parts.append(
            f'<details class="history-run" id="run-{key}" data-release="{record["upstream_sha"]}" data-status="{record["status"]}">'
            f'<summary>{label(record)}</summary><dl class="outcomes">'
            f'<dt>Measurement</dt><dd>{status_text(record, audit)}</dd>'
            f'<dt>Publication</dt><dd>{publication_text(record, audit)}</dd></dl>'
            f'<p><a href="#compare-{key}">Renderer comparison</a> · '
            f'<a href="#document-{key}">Documents &amp; pages</a> · '
            f'<a href="records/{key}.json">Numeric record {key}</a> · '
            f'<a href="{REPO}/actions/runs/{record["run_id"]}/attempts/{record["attempt"]}">Actions attempt</a> · '
            f'<a href="{REPO}/blob/{record["dashboard_sha"]}/corpus/manifest.json">Exact corpus contract</a></p>'
            f'<h3>Reproduction and provenance</h3><dl>{hashes}</dl></details>'
        )
    return "".join(parts)


def methods():
    revision = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", revision):
        revision_label = f'<a href="{REPO}/commit/{revision}"><code>{revision}</code></a>'
    else:
        revision_label = "Unavailable (local build)"
    contract = metric_list([
        ("Reference", "Independent Hancom Print PDF"),
        ("Score", "Raw silhouette overlap · %"),
        ("Raster / ink / dilation", "96 dpi · min(R,G,B) < 232 · 2 px"),
        ("P10", "Nearest-rank 10th percentile"),
        ("Page pair", "Same attempt · complete documents · matching counts"),
        ("Score gap", "Native Skia − WASM Canvas2D · percentage points"),
        ("Runtime / fonts", "Native CLI / browser WASM · backend-specific font selection"),
        ("Quality alerts", "Below 90% · page-count mismatch"),
        ("History", "Active smoke corpus · original measurement timestamps"),
        ("Publication evidence", "Audited job per attempt · unknown otherwise"),
        ("Direct backend parity / PR regression", "Unmeasured"),
    ])
    return f"""
{contract}
<p>Page build revision: {revision_label}</p>
<h3>PR Visual Sweep</h3>
<ul>
  <li><a href="{UPSTREAM}/pull/9024">rhwp #9024</a> · HWPX · Candidate · 763 pages per backend</li>
  <li><a href="https://github.com/edwardkim/rhwp/blob/39a3774de60c81a3b803d158c044ddc195733eb6/mydocs/pr/assets/issue8946/stage10-20261114/original/head/hwpx-native.tsv">Native TSV</a> · <a href="https://github.com/edwardkim/rhwp/blob/39a3774de60c81a3b803d158c044ddc195733eb6/mydocs/pr/assets/issue8946/stage10-20261114/original/head/hwpx-wasm.tsv">WASM TSV</a> · <a href="https://github.com/edwardkim/rhwp/blob/39a3774de60c81a3b803d158c044ddc195733eb6/mydocs/pr/assets/issue8946/stage10-20261114/README.md">Measurement record</a></li>
</ul>
<h3>Upstream evidence</h3>
<ul>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/.github/workflows/oracle-public-advisory.yml">Oracle Public Advisory</a> · Page counts · Match / mismatch / error / unpaired</li>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/mydocs/manual/verification/visual_verification_governance.md">Visual review policy</a> · Comparable base/head drop &gt;2 pp · Human review</li>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/mydocs/pr/assets/visual-protected-baseline/final.tsv">Protected page floors (TSV)</a> · Historical thresholds · Per page / backend · Two decimals</li>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/tools/fidelity_compare/README.md">Document structure checks</a> · Missing / misplaced text candidates</li>
</ul>
<h3>Sources</h3>
<ul>
  <li><a href="{REPO}/blob/main/docs/METHODOLOGY.md">Measurement methodology</a></li>
  <li><a href="{REPO}/blob/main/docs/CORPUS.md">Smoke corpus and source approvals</a></li>
  <li><a href="{REPO}/tree/data/records">Durable numeric ledger</a></li>
  <li><a href="{UPSTREAM}/blob/197ce19e99438c2cba452c654ae1af504dab85ec/rhwp-studio/e2e/canvas-render-diff.test.mjs">Upstream Canvas tree comparison and pixel tolerances</a></li>
  <li><a href="summary.json">Machine-readable current snapshot</a></li>
</ul>
"""


def historical_pr_pages(out):
    rows = json.loads((SITE / "pr-9024-pages.json").read_text())
    by_gap = sorted(rows, key=lambda row: (-abs(round(row[1] - row[2], 2)), row[0]))
    headers = ["Page", "Native Skia (%)", "WASM Canvas2D (%)", "Skia minus Canvas2D (pp)"]
    body = "".join(
        "<tr>" + "".join(f'<td data-label="{header}">{value}</td>' for header, value in zip(
            headers, [p, f"{native:.2f}", f"{wasm:.2f}", f"{native - wasm:+.2f}"])) + "</tr>"
        for p, native, wasm in by_gap
    )
    labels = "".join(f'<th scope="col">{header}</th>' for header in headers)
    source = f"{UPSTREAM}/blob/39a3774de60c81a3b803d158c044ddc195733eb6/mydocs/pr/assets/issue8946/stage10-20261114/"
    (out / "pr-9024.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>rhwp PR #9024 · HWPX pages</title><link rel="stylesheet" href="dashboard.css"></head>
<body><main><a href="index.html#renderers">Renderer comparison</a><h1>PR #9024 · HWPX</h1>
<p>Historical PR measurement · 763 paired pages · Hancom Print · 96 DPI</p>
<p>Supplied font files · Native 75 / WASM 71 · Different font sets</p>
<p>Reference PDF · Local-only · <a href="{source}input-commit-audit.json">Input hashes</a></p>
<p><a href="{source}original/head/hwpx-native.tsv">Native TSV</a> ·
<a href="{source}original/head/hwpx-wasm.tsv">WASM TSV</a> ·
<a href="{source}visual-provenance.json">TSV provenance</a> ·
<a href="{source}producer.json">Measured build</a> · <a href="{UPSTREAM}/pull/9024">PR</a></p>
<div class="scroll"><table class="page-grid"><caption>Raw silhouette · Absolute score gap ↓</caption>
<thead><tr>{labels}</tr></thead><tbody>{body}</tbody></table></div></main></body></html>
""", encoding="utf-8")


def render_site(out, records, docs, inventory):
    snapshot = json.loads((SITE / "evidence.json").read_text())
    if os.environ.get("REFRESH_RELEASE") == "1":
        from datetime import datetime, timezone
        from pipeline import stable_releases, resolve_ref
        try:
            releases = stable_releases()
            if releases:
                tag = releases[-1]["tag_name"]
                sha, _ = resolve_ref(tag)
                snapshot["release"] = {"sha": sha, "tag": tag, "observed_on": datetime.now(timezone.utc).date().isoformat()}
        except (OSError, ValueError, KeyError):
            print("Release lookup unavailable; displaying dated observation.")
    observations = {(e["run_id"], e["attempt"]): e for e in snapshot["attempts"]}
    groups = release_groups(records, snapshot["release"])
    historical_pr_pages(out)
    panes = {
        "overview": inventory_section(inventory) + overview(records, docs, snapshot["release"], groups),
        "renderers": (run_views(groups, docs, "compare", renderer_tables) +
                      '<p><a href="pr-9024.html">Historical PR #9024 · HWPX · 763 paired pages</a></p>'),
        "documents": ('<p>Default order · Absolute score gap ↓ &nbsp;|&nbsp; Gap scale · −100 to +100 pp</p>'
                      + run_views(groups, docs, "document", document_table)),
        "history": history_view(records, observations),
        "methods": methods() + "".join(
            f'<p data-release="{sha}" data-preferred="true">Selected revision · {esc(tag)} · '
            + (run_link(next((r for r in reversed(attempts) if r["status"] == "complete"), attempts[-1]))
               if attempts else "No recorded attempt") + "</p>" for sha, tag, attempts in groups
        ),
    }
    nav = "".join(f'<a id="tab-{key}" href="#{key}">{esc(title)}</a>' for key, title in TABS)
    sections = "".join(
        f'<section id="{key}" aria-labelledby="heading-{key}"><h2 id="heading-{key}">'
        f'{esc(title)}</h2>{panes[key]}</section>' for key, title in TABS
    )
    (out / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>rhwp fidelity dashboard</title>
<link rel="stylesheet" href="dashboard.css">
<script src="dashboard.js" defer></script>
</head>
<body>
<a class="skip" href="#overview">Skip to dashboard content</a>
<header><h1>rhwp fidelity dashboard</h1><p>Rendering coverage and fidelity against Hancom Print PDF</p>{release_picker(groups)}</header>
<nav aria-label="Dashboard views">{nav}</nav>
<main id="content">{sections}</main>
<footer>Public data · Numeric results &amp; approved metadata</footer>
</body>
</html>
""", encoding="utf-8")
    for asset in ("dashboard.css", "dashboard.js"):
        (out / asset).write_bytes((SITE / asset).read_bytes())
