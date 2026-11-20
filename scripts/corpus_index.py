"""Export one numeric status per source path at the pinned inventory revision."""
import os
from pathlib import Path

from cohort_site import page
from core import digest, read_json, write_json
from corpus_inventory import ROOTS


def build(out, inventory, archive):
    path = os.environ.get("DASHBOARD_INVENTORY_ROWS")
    if not path:
        return ""
    source = read_json(path)
    rows = source["rows"]
    if source["source_revision"] != inventory["source_revision"] or len(rows) != inventory["source_paths"]:
        raise ValueError("Wrong corpus inventory")
    # Bind scores to exactly one archived run. Historical releases stay accessible by run.
    newest = next((r for r in reversed(archive) if r["corpus_sha"] == source["source_revision"]), None)
    measured = {}
    if newest:
        for stage in newest["stages"].values():
            for backend, result in stage["measurement"]["backends"].items():
                for d in result["documents"]:
                    measured.setdefault(d["id"], {})[backend] = d
    docs = {d["path_sha256"]: d for d in newest["docs"]} if newest else {}
    output = []
    for row in rows:
        name = row["path"]
        key = digest(name.encode())
        doc = docs.get(key, {})
        pair = measured.get(doc.get("id"), {})
        n, w = pair.get("native", {}), pair.get("wasm", {})
        states = [n.get("status", "unmeasured"), w.get("status", "unmeasured")]
        receipt = any(p["status"] == "verified" for p in row["receipt_pairs"])
        if not pair:
            state = "Verified · unmeasured" if receipt else "Outside audited receipt set"
        elif states != ["complete", "complete"]:
            state = "Incomplete"
        elif any(p.get("rendered_pages") != doc.get("pages") for p in (n, w)):
            state = "Page count mismatch"
        else:
            state = "Paired"
        output.append({"path_sha256": key, "id": doc.get("id"), "root": next(r for r in ROOTS if name.startswith(r + "/")),
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
               "status_counts": statuses, "rows": output})
    (out / "corpus-index.js").write_bytes((Path(__file__).with_name("site") / "corpus-index.js").read_bytes())
    revision = source["source_revision"][:12]
    body = (f'<p>Inventory {revision} · {len(rows):,} paths · {inventory["unique_blobs"]:,} unique Git blobs</p>'
            '<p>Scope and deferrals are recorded per check. Sources outside this receipt set may have other reference PDFs.</p>'
            '<label>Find document ID, hash or upstream path <input type="search" id="query"></label> '
            '<label>Status <select id="state"><option value="">All</option></select></label> '
            '<p id="count" aria-live="polite">Loading inventory…</p>'
            '<button id="prev" type="button">Previous</button> <button id="next" type="button">Next</button>'
            '<div class="scroll"><table class="page-grid"><caption>Source paths</caption><thead><tr>'
            + "".join(f'<th scope="col">{h}</th>' for h in ("Path ID", "Root", "Format", "Aliases", "Release status", "Resolver", "Deferred axes"))
            + '</tr></thead><tbody></tbody></table></div><p><a href="corpus-index.json">Complete inventory JSON</a></p>')
    (out / "corpus-index.html").write_text(page("Corpus inventory", body, '<script src="corpus-index.js" defer></script>'))
    return f'<p><a href="corpus-index.html">Browse all {len(rows):,} source paths</a> · Paired in this release run {statuses.get("Paired", 0):,}/{len(rows):,}</p>'
