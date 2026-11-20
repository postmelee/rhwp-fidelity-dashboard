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
        body = f'<tr><td colspan="{len(headers)}">No rows available.</td></tr>'
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
            'Checkout contract failed · no scores. '
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


def decision_card(title, status, description, href, link_text):
    return (
        f'<article class="decision"><h3>{esc(title)}</h3>'
        f'<span class="badge">{esc(status)}</span><p>{esc(description)}</p>'
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
    summary = f"{len(measured)}/{target} pages with paired golden scores."
    if measured:
        passing = sum(min(r[2], r[3]) >= 90 for r in measured)
        summary += f" Both renderers reached 90% raw silhouette on {passing}/{len(measured)} compared pages."

    cards = [
        decision_card("Hancom Print fidelity", heading, summary, compare, "Compare renderers"),
        decision_card("Browser rendering · Canvas2D / CanvasKit", "CanvasKit unmeasured",
                      "The smoke run measures browser Canvas2D. Its Skia score comes from the native CLI.",
                      compare, "Inspect measured backends"),
        decision_card("Canvas tree output parity", "Render Diff evidence unavailable",
                      "PageRenderTree and PageLayerTree draw the same page. Render Diff compares their pixels under the same browser configuration.",
                      "#methods", "Method and evidence sources"),
    ]
    source = f'<p>Measurement evidence: {run_link(record)}</p>' if record else ""
    if record:
        counts = []
        for key, name in (("wasm", "Canvas2D"), ("native", "Native Skia")):
            known, equal = page_count_evidence(record["measurement"]["backends"][key])
            counts.append(f"{name} {equal}/{known}" if known else f"{name} unavailable")
        source += (f'<p><strong>Documents matching Hancom page count</strong> · {" · ".join(counts)} '
                   '(among documents with both counts known).</p>')
    if last and last != record:
        source += f'<p>Most recent attempt: {run_link(last)}</p>'
    body = (f'<h3 class="release-title">{esc(tag)} · {heading}</h3>'
            f'<div class="cards decisions">{"".join(cards)}</div>{source}')
    if measured:
        for name, index in (("Canvas2D", 2), ("Native Skia", 3)):
            value = min(row[index] for row in measured)
            body += (f'<div class="score-line"><span>{name} · lowest paired page</span>'
                     f'<meter aria-label="{name} lowest paired page" min="0" max="100" value="{value}"></meter>'
                     f'<strong>{number(value)}%</strong></div>')
        names = {d["id"]: Path(d.get("document", {}).get("source", d["id"])).name for d in docs}
        rows = [(names[key], page, number(w), number(n), f"{delta:+.5f}") for key,page,w,n,delta in measured[:5]]
        body += table("Largest differences against the same Hancom page", [
            "Document", "Page", "Canvas2D", "Native Skia", "Skia minus Canvas2D (points)",
        ], rows, cards=True)
        body += f'<p>{sum(r[4] == 0 for r in measured)} of {len(measured)} paired pages tied. <a href="{document}">All page results</a></p>'
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


def overview(records, docs, release, groups):
    latest_complete = next((r for r in reversed(records) if r["status"] == "complete"), None)
    latest_note = "No measurements available." if latest_complete is None else run_link(latest_complete)
    if latest_complete and latest_complete["upstream_sha"] != release["sha"]:
        latest_note += f' · <a href="#release-{latest_complete["upstream_sha"]}">See this release overview</a>'
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
            parts.append(f'<p data-release="{sha}" data-preferred="true">{esc(tag)} · No measurements available.</p>')
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
        return '<p>No attempts recorded.</p>'
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
    return f"""
<p>Independent Hancom Print PDF is the golden for fresh WASM Canvas2D and Native Skia.
Raw silhouette measures shape overlap at 96 dpi, using an RGB 232 ink threshold and 2 px dilation.
P10 is nearest rank. A complete run can carry quality alerts, including page-count mismatches.</p>
<p>Native and browser runtime/font behavior can differ under the same declared font contract.
The score difference compares each backend to Hancom. Direct backend parity, CanvasKit,
tree-path parity and PR regression are currently unavailable.</p>
<p>Stored scores and fingerprints belong to the original immutable measurement attempt.
Redeployment displays historical results. Run history lists only the active smoke corpus.
Publication labels reflect audited jobs for specific attempts. Later attempts without an audited
job are marked unknown.</p>
<p>Page build revision: {revision_label}</p>
<ul>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/.github/workflows/oracle-public-advisory.yml">Oracle Public Advisory</a> compares document page counts. Its completed verdict and match, mismatch, error and unpaired counts are needed for coverage beyond this smoke corpus.</li>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/mydocs/manual/verification/visual_verification_governance.md">Upstream visual review policy</a> flags a drop greater than 2 percentage points from a comparable base on any page and backend. Matched base/head runs and human review evidence are unavailable here.</li>
  <li><a href="{UPSTREAM}/blob/{EVIDENCE_REV}/tools/fidelity_compare/README.md">Document structure checks</a> identify possible missing or misplaced text for review. These diagnostics are currently unmeasured here.</li>
  <li><a href="{REPO}/blob/main/docs/METHODOLOGY.md">Measurement methodology</a></li>
  <li><a href="{REPO}/blob/main/docs/CORPUS.md">Smoke corpus and source approvals</a></li>
  <li><a href="{REPO}/tree/data/records">Durable numeric ledger</a></li>
  <li><a href="{UPSTREAM}/blob/197ce19e99438c2cba452c654ae1af504dab85ec/rhwp-studio/e2e/canvas-render-diff.test.mjs">Upstream Canvas tree comparison and pixel tolerances</a></li>
  <li><a href="summary.json">Machine-readable current snapshot</a></li>
</ul>
"""


def render_site(out, records, docs):
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
    panes = {
        "overview": overview(records, docs, snapshot["release"], groups),
        "renderers": (
            '<p>Canvas2D and Skia against the same Hancom golden. A matched row requires '
            'both outputs to be complete, from the same attempt, and to agree with the golden page count. '
            'Page-count equality uses documents with known counts. Score summaries use measured pages.</p>'
            + run_views(groups, docs, "compare", renderer_tables)
        ),
        "documents": (
            '<p>Each attempt lists the approved smoke pages and any available scores by backend. '
            'Rows start with the largest absolute gap. The gap uses percentage points on a −100 to +100 scale.</p>'
            + run_views(groups, docs, "document", document_table)
        ),
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
<footer>Public output contains numeric results and approved metadata.</footer>
</body>
</html>
""", encoding="utf-8")
    for asset in ("dashboard.css", "dashboard.js"):
        (out / asset).write_bytes((SITE / asset).read_bytes())
