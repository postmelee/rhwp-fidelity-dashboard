"""Export one numeric status per source path at the pinned inventory revision."""
import os
from statistics import median
from pathlib import Path

from cohort_site import page
from core import digest, read_json, write_json
from corpus_inventory import ROOTS


def scores_for_run(record):
    measured = {}
    for stage in record["stages"].values():
        for backend, result in stage["measurement"]["backends"].items():
            for item in result["documents"]:
                measured.setdefault(item["id"], {})[backend] = item
    scores = {}
    for doc in record["docs"]:
        pair = measured.get(doc["id"], {})
        native, wasm = pair.get("native", {}), pair.get("wasm", {})
        states = [data.get("status", "unmeasured") for data in (native, wasm)]
        if not pair:
            status = "Verified · unmeasured"
        elif states != ["complete", "complete"]:
            status = "Incomplete"
        elif any(data.get("pdf_pages") != doc["pages"] or data.get("rendered_pages") != doc["pages"]
                 for data in (native, wasm)):
            status = "Page count mismatch"
        else:
            status = "Paired"
        values = {}
        for backend, data in (("native", native), ("wasm", wasm)):
            valid = (data.get("status") == "complete" and data.get("scores")
                     and data.get("pdf_pages") == data.get("rendered_pages") == doc["pages"])
            values[backend] = median(p["raw"] for p in data["scores"]) if valid else None
        scores[doc["path_sha256"]] = {"id": doc["id"], "page_median_percent": values,
                                     "status": status, "backend_status": states}
    return scores


def build(out, inventory, archive):
    path = os.environ.get("DASHBOARD_INVENTORY_ROWS")
    if not path:
        return ""
    source = read_json(path)
    rows = source["rows"]
    if source["source_revision"] != inventory["source_revision"] or len(rows) != inventory["source_paths"]:
        raise ValueError("Wrong corpus inventory")
    # Bind scores to one archived run and prefer a scored run for the unfiltered view.
    newest = None
    scopes = []
    selected = {}
    for record in archive:
        if record["corpus_sha"] != source["source_revision"]:
            continue
        key = f'{record["run_id"]}-{record["attempt"]}'
        scores = scores_for_run(record)
        write_json(out / "measured-paths" / (key + ".json"), scores)
        scopes.append({"key": key, "tag": record["tag"], "sha": record["engine_sha"]})
        if newest is None or any(any(v is not None for v in row["page_median_percent"].values())
                                 for row in scores.values()):
            newest, selected = record, scores
    output = []
    for row in rows:
        name = row["path"]
        key = digest(name.encode())
        receipt = any(p["status"] == "verified" for p in row["receipt_pairs"])
        score = selected.get(key, {})
        states = score.get("backend_status", ["unmeasured", "unmeasured"])
        state = score.get("status", "Verified · unmeasured" if receipt else "Outside audited receipt set")
        fidelity = score.get("page_median_percent", {"native": None, "wasm": None})
        output.append({"page_median_percent": fidelity,"path_sha256": key, "id": score.get("id"), "root": next(r for r in ROOTS if name.startswith(r + "/")),
                       "oracle_state": row.get("oracle_state", "unaudited"),
                       "format": name.rsplit(".", 1)[1].lower(), "blob": row["blob"],
                       "paths_with_same_blob": row["paths_with_same_blob"], "resolver_scope": row["resolver_scope"],
                       "page_count_baseline": row["page_count_baseline"], "receipt_verified": receipt,
                       "general_regression_deferred": row["general_regression_deferred"],
                       "visual_deferrals": row["visual_deferrals"], "status": state, "backend_status": states})
    if len({r["path_sha256"] for r in output}) != len(rows) or len({r["blob"] for r in output}) != inventory["unique_blobs"]:
        raise ValueError("Corpus identity count mismatch")
    output.sort(key=lambda r: (r["status"] == "Outside audited receipt set", r["id"] or r["path_sha256"]))
    statuses = {}
    for r in output:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    write_json(out / "corpus-index.json", {"source_revision": source["source_revision"],
               "run_id": newest["run_id"] if newest else None, "attempt": newest["attempt"] if newest else None,
               "status_counts": statuses, "runs": scopes, "rows": output})
    (out / "corpus-index.js").write_bytes((Path(__file__).with_name("site") / "corpus-index.js").read_bytes())
    revision = source["source_revision"][:12]
    body = (f'<p>Inventory {revision} · {len(rows):,} paths · {inventory["unique_blobs"]:,} unique Git blobs</p>'
            '<p>Scope and deferrals are recorded per check. Sources outside this receipt set may have other reference PDFs.</p>'
            '<div class="filters"><label>Measured revision and run <select id="run"></select></label> '
            '<label>Find document ID, hash or upstream path <input type="search" id="query"></label> '
            '<label>Status <select id="state"><option value="">All</option></select></label></div>'
            '<p id="count" aria-live="polite">Loading inventory…</p>'
            '<button id="prev" type="button">Previous</button> <button id="next" type="button">Next</button>'
            '<div class="scroll"><table class="page-grid"><caption>Source paths</caption><thead><tr>'
            + "".join(f'<th scope="col">{h}</th>' for h in ("Path ID", "Root", "Format", "Aliases", "Run status", "Native Skia median (%)", "Canvas2D median (%)", "Print reference", "Resolver", "Deferred axes"))
            + '</tr></thead><tbody></tbody></table></div><p><a href="corpus-index.json">Complete inventory JSON</a></p>')
    (out / "corpus-index.html").write_text(page("Corpus inventory", body, '<script src="corpus-index.js" defer></script>'))
    paired = statuses.get("Paired", 0)
    percent = 100 * paired / len(rows) if rows else 0
    tag = newest["tag"] if newest else "Unmeasured"
    return f'<p>{tag} · <a href="corpus-index.html">Browse all {len(rows):,} source paths</a> · Paired in this run {paired:,}/{len(rows):,} ({percent:.2f}%)</p>'
