"""Build release-scoped receipt coverage without mixing smoke runs or PR scores."""
import html
from pathlib import Path

from core import BACKENDS, canonical, coverage, digest, read_json, stats, write_json
from receipt_archive import validate_archive
from receipt_cohort import contract

esc = html.escape


def summarize(record):
    rows = {b: [] for b in BACKENDS}
    for stage in record["stages"].values():
        for b in BACKENDS:
            rows[b].extend(stage["measurement"]["backends"][b]["documents"])
    by_id = {b: {r["id"]: r for r in rows[b]} for b in BACKENDS}
    counts = {b: coverage({"documents": rows[b]}, record["docs"]) for b in BACKENDS}
    paired_docs = 0
    all_pages_above_floor = 0
    lowest = None
    paired_pages = 0
    details = []
    for doc in record["docs"]:
        key = doc["id"]
        pair = [by_id[b].get(key, {}) for b in BACKENDS]
        status = [r.get("status", "unavailable") for r in pair]
        matches = all(r.get("pdf_pages") == r.get("rendered_pages") == doc["pages"] for r in pair)
        complete_pair = status == ["complete", "complete"] and matches
        paired_docs += int(complete_pair)
        scores = [{p["page"]: p["raw"] for p in r.get("scores", [])} for r in pair]
        if complete_pair:
            score, page_number, backend = min((score, page_number, backend)
                                              for backend, page_scores in zip(BACKENDS, scores)
                                              for page_number, score in page_scores.items())
            if score >= 90:
                all_pages_above_floor += 1
            elif lowest is None or score < lowest["score"]:
                lowest = {"document": key, "page": page_number, "backend": backend, "score": score}
        for page in range(1, doc["pages"] + 1):
            n, w = (s.get(page) for s in scores)
            paired = matches and n is not None and w is not None
            paired_pages += int(paired)
            details.append({"document": key, "page": page, "native": n, "wasm": w,
                            "delta": n - w if paired else None, "status": " / ".join(status),
                            "page_counts": [r.get("rendered_pages") for r in pair] + [doc["pages"]],
                            "path_sha256": doc["path_sha256"]})
    return {"by_backend": counts, "paired_docs": paired_docs, "paired_pages": paired_pages,
            "docs_at_or_above_90": all_pages_above_floor, "lowest_below_90": lowest, "pages": details}


def page(title, body, script="", *, section="documents", section_label="Documents & pages"):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<link rel="stylesheet" href="dashboard.css">{script}</head><body><main>
<a href="index.html#{esc(section)}">{esc(section_label)}</a><h1>{esc(title)}</h1>{body}</main></body></html>"""


def family_table(record, config, details):
    from preview_presentation import table
    if record["cohort_sha256"] != digest(canonical(config)):
        return ""
    families = {
        "issue8573": "Table and picture anchors (#8573)",
        "issue8664": "Zero-size paragraph (#8664)",
        "issue8665": "Title pagination (#8665)",
        "issue8678": "Chart value axes (#8678)",
        "issue8680": "Wingdings symbols (#8680)",
        "issue8690": "Lines in split table cells (#8690)",
    }
    members = {d["id"]: families.get(Path(d["input"]).parent.name, "Unclassified") for d in config["documents"]}
    grouped = {}
    for row in details:
        grouped.setdefault(members[row["document"]], []).append(row)
    rows = []
    for name, pages in sorted(grouped.items()):
        paired = [r for r in pages if r["delta"] is not None]
        values = [stats([r[b] for r in paired])["median"] for b in BACKENDS]
        rows.append([name, len({r["document"] for r in pages}), f"{len(paired)}/{len(pages)}",
                     *[f"{v:.5f}" if v is not None else "Unmeasured" for v in values]])
    return table("Upstream fixture families · median on paired pages", ["Case family", "Documents",
                 "Paired / target pages", "Native Skia (%)", "WASM Canvas2D (%)"], rows, cards=True)


def build(folder, out, inventory):
    config, docs = contract()
    archive = []
    records = []
    for source in folder.glob("*.json"):
        record = validate_archive(read_json(source))
        records.append(record)
        run_key = f'{record["run_id"]}-{record["attempt"]}'
        if source.stem != run_key:
            raise ValueError("Mislabeled archived measurement")
        summary = summarize(record)
        name = "cohorts/" + run_key + ".json"
        write_json(out / name, record)
        headline = {k: v for k, v in summary.items() if k != "pages"}
        archive.append({"tag": record["tag"], "engine_sha": record["engine_sha"],
                        "documents": len(record["docs"]), "target_pages": sum(d["pages"] for d in record["docs"]),
                        "run_id": record["run_id"], "attempt": record["attempt"],
                        "record": name, **headline})
        from preview_presentation import table
        def shown(score):
            return "Unmeasured" if score is None else f"{score:.5f}"
        ordered = sorted(summary["pages"], key=lambda r: min((v for v in (r["native"], r["wasm"]) if v is not None), default=-1))
        rows = [[r["document"], r["page"], shown(r["native"]), shown(r["wasm"]), shown(r["delta"]),
                 " / ".join("?" if p is None else str(p) for p in r["page_counts"]), r["status"]] for r in ordered]
        caption = table("Reference pages · lowest score first", ["Document", "Page", "Native Skia (%)",
            "WASM Canvas2D (%)", "Native minus WASM (pp)", "Native / WASM / PDF pages", "Native / WASM status"],
            rows, cards=True, row_ids=[f"page-{r['document']}-{r['page']}" for r in ordered])
        stats = table("Page-weighted silhouette (%)", ["Renderer", "Measured pages", "Median", "P10", "Minimum", "Below 90", "Page count mismatches"],
                      [[label, x["measured_pages"], shown(x["median"]), shown(x["p10"]), shown(x["min"]),
                        x["below90"], x["page_count_mismatch"]] for label, x in zip(("Native Skia", "WASM Canvas2D"), (summary["by_backend"][b] for b in BACKENDS))], cards=True)
        links = "".join(
            f'<p>{esc(stage)} · Reused from {esc(s["tag"])} · '
            f'<a href="https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/{s["run_id"]}/attempts/{s["attempt"]}">'
            f'original run {s["run_id"]}, attempt {s["attempt"]}</a></p>'
            for stage, s in record.get("stage_sources", {}).items())
        registry = "tests/fixtures/oracle_page_count_verified_references.json"
        registry_url = f'https://github.com/edwardkim/rhwp/blob/{record["corpus_sha"]}/{registry}'
        tag = esc(record["tag"])
        body = (f'<p>{("Development branch" if tag == "devel" else "Release")} {tag} · <code>{record["engine_sha"][:12]}</code> · Hancom Print · 96 DPI · 2 px</p>'
                f'<p>Paired documents {summary["paired_docs"]}/{len(record["docs"])} · '
                f'Paired pages {summary["paired_pages"]}/{len(rows)}. Matching page counts required for score differences.</p>'
                f'<p><a id="cohort-record" href="{name}">Numeric record and producer hashes</a> · '
                f'<a href="https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/{record["run_id"]}/attempts/{record["attempt"]}">Measurement run</a> · '
                f'<a href="https://github.com/edwardkim/rhwp/blob/{record["corpus_sha"]}/{config["receipt"]}">Print receipts</a> · <a href="{registry_url}">Registered reference provenance</a></p>'
                '<p>Each renderer is compared to its Hancom PDF. Direct backend pixel parity and the original Print font environment are unmeasured.</p>' +
                links + stats + family_table(record, config, summary["pages"]) +
                '<div class="filters"><label>Find a document <input type="search" id="query"></label> '
                '<label><input type="checkbox" id="problems"> Failures, missing scores or page count mismatches</label>'
                '<label><input type="checkbox" id="native-lower"> Native Skia scores below Canvas2D</label> '
                '<label> Sort <select id="order"><option value="low">Lowest score</option><option value="gap">Largest gap</option>'
                '<option value="page">Document and page</option></select></label></div><p id="count" aria-live="polite"></p>'
                '<article id="page-handoff" aria-labelledby="page-handoff-title" hidden>'
                '<h2 id="page-handoff-title" tabindex="-1"></h2>'
                '<label for="page-handoff-data">Reproduction details</label>'
                '<textarea id="page-handoff-data" readonly rows="8" style="display:block;width:100%"></textarea>'
                '<button id="copy-page-handoff" type="button" disabled>Copy reproduction details</button>'
                ' <a id="page-permalink">Page permalink</a>'
                '<p id="page-handoff-status" role="status"></p></article>' + caption)
        (out / ("cohort-" + run_key + ".html")).write_text(page("Print measurement · " + tag, body,
            '<script src="cohort.js" defer></script>'))
    archive.sort(key=lambda r: (r["run_id"], r["attempt"]))
    (out / "cohort.js").write_bytes((Path(__file__).with_name("site") / "cohort.js").read_bytes())
    (out / "receipt-status.js").write_bytes((Path(__file__).with_name("site") / "receipt-status.js").read_bytes())
    write_json(out / "cohort-runs.json", archive)
    overview = ('<h3>Receipt-backed measurements</h3>'
                f'<p>Original receipt bundle · {esc(config["tag"])} · {len(docs)} documents · {sum(d["pages"] for d in docs)} reference pages</p>')
    for r in reversed(archive):
        key = f'{r["run_id"]}-{r["attempt"]}'
        overview += (f'<p><a href="cohort-{key}.html">{esc(r["tag"])} · {r["paired_docs"]}/{r["documents"]} paired documents · '
                     f'{r["paired_pages"]}/{r["target_pages"]} paired pages</a> · Run {key}</p>')
    if not archive:
        overview += '<p>No archived receipt-backed release measurements.</p>'
    from corpus_index import build as build_index
    overview += build_index(out, inventory, sorted(records, key=lambda r: (r["run_id"], r["attempt"])))
    return archive, overview
