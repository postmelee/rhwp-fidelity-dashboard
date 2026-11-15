"""Presentation of validated immutable records; never combines separate attempts."""
import html
from core import coverage

LABELS = {"native": "Native Skia", "wasm": "WASM Canvas2D"}
def number(value):
    return "unavailable" if value is None else f"{value:.5f}".rstrip("0").rstrip(".")

def paired_pages(record, docs):
    """Pair only complete, count-matched pages within the SAME validated run."""
    backends = record["measurement"]["backends"]
    maps = {b: {d["id"]: d for d in backends[b]["documents"]} for b in LABELS}
    rows = []
    for doc in docs:
        pair = [maps[b].get(doc["id"]) for b in ("wasm", "native")]
        valid = all(d and d["status"] == "complete" and
                    d["pdf_pages"] == doc["pages"] == d["rendered_pages"] for d in pair)
        values = [{s["page"]: s["raw"] for s in d["scores"]} if d else {} for d in pair]
        for page in range(1, doc["pages"] + 1):
            comparable = valid and all(page in v for v in values)
            w, n = (values[0][page], values[1][page]) if comparable else (None, None)
            rows.append((doc["id"], page, w, n, None if w is None else n-w))
    return rows

def table(headers, rows):
    head = "".join('<th><button type="button" class="sort">'+html.escape(h)+"</button></th>" for h in headers)
    body = "".join("<tr>"+"".join("<td>"+html.escape(str(v))+"</td>" for v in row)+"</tr>" for row in rows)
    return '<div class="scroll"><table class="sortable"><thead><tr>'+head+'</tr></thead><tbody>'+(
        body or '<tr><td colspan="'+str(len(headers))+'">unavailable</td></tr>')+'</tbody></table></div>'

def comparison_html(records, docs):
    parts = ['<h2>Canvas2D and Skia against the same Hancom golden</h2>',
        '<p>WASM Canvas2D is the browser Canvas2D path built fresh from the tested source. Native Skia is the native CLI built with native-skia. These are distinct runtime paths, not an isolated swap of one browser renderer. Font supply and runtime differences may affect the result.</p>',
        '<p>Each comparison below uses one immutable attempt: identical engine SHA, document/PDF hashes, page, compatibility, corpus/font contract and protocol. Runtime/build fingerprints belong to that attempt. Skia minus Canvas2D is a difference between two golden scores, NOT a direct pixel similarity between renderers or a maturity percentage. Count-mismatched or incomplete documents are excluded from paired scores.</p>']
    selected = next((r for r in reversed(records) if r["status"] == "complete"), None)
    for r in reversed(records):
        esc = html.escape
        name = f'{r["run_id"]}-{r["attempt"]}'
        parts.append('<details'+(' open' if r is selected else '')+'><summary>'+esc(
            r["resolved_at"]+' / '+r["source_ref"]+' / '+r["upstream_sha"][:12]+' / '+r["status"])+'</summary>')
        summary = []
        for b in ("wasm", "native"):
            backend = r["measurement"]["backends"][b]
            c = coverage(backend, docs)
            known = [d for d in backend["documents"] if d["pdf_pages"] is not None and d["rendered_pages"] is not None]
            equal = sum(d["pdf_pages"] == d["rendered_pages"] for d in known)
            rate = "unavailable" if not known else f"{equal}/{len(known)} ({100*equal/len(known):.1f}%)"
            summary.append([LABELS[b], backend["status"], f'{c["measured_docs"]}/{c["target_docs"]}',
                c["failed_docs"], c["skipped_docs"], f'{c["measured_pages"]}/{c["target_pages"]}',
                c["failed_pages"], c["skipped_pages"], c["unmeasured_pages"], rate,
                len(docs)-len(known), number(c["min"]), number(c["p10"]), number(c["median"]), c["below90"]])
        parts.append(table(["Backend","Status","Docs complete/target","Docs failed","Docs skipped",
            "Pages measured/target","Pages failed","Pages skipped","Pages unmeasured",
            "Page-count equal/known docs","Count unknown docs","Min","P10","Median","Below 90"], summary))
        parts.append('<p>Page-count equality is a document-level count check, not pixel fidelity. Its denominator excludes unknown counts, which are shown separately.</p>')
        parts.append(table(["Document ID","Page","Canvas2D vs Hancom","Skia vs Hancom","Skia minus Canvas2D (points)"],
            [(key,page,number(w),number(n),number(delta)) for key,page,w,n,delta in paired_pages(r,docs)]))
        details = []
        for b in ("wasm","native"):
            for doc in docs:
                d = next((x for x in r["measurement"]["backends"][b]["documents"] if x["id"] == doc["id"]), None)
                values = {s["page"]:s["raw"] for s in d["scores"]} if d else {}
                for p in range(1,doc["pages"]+1):
                    details.append([doc["id"],p,LABELS[b],d["status"] if d else "unavailable",
                        doc["pages"], d["rendered_pages"] if d and d["rendered_pages"] is not None else "unavailable",
                        number(values.get(p))])
        parts.append('<details><summary>Document and page details (including unpaired results)</summary>'+table(
            ["Document ID","Page","Backend","Document status","Golden pages","Rendered pages","Raw silhouette"],details)+'</details>')
        parts.append('<details><summary>Reproduction and provenance</summary><dl>')
        for k in ("upstream_sha","dashboard_sha","source_ref","source_kind","resolved_at","protocol",
                  "corpus_sha256","font_sha256","adapter_sha256"):
            parts.append('<dt>'+esc(k)+'</dt><dd><code>'+esc(str(r[k]))+'</code></dd>')
        for k in ("environment_sha256","build_sha256"):
            parts.append('<dt>'+k+'</dt><dd><code>'+esc(str(r["measurement"][k] or "unavailable"))+'</code></dd>')
        parts.append('</dl><p><a href="records/'+name+'.json">Immutable numeric record</a> · <a href="https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/'+str(r["run_id"])+'">Actions run</a> · <a href="https://github.com/postmelee/rhwp-fidelity-dashboard/blob/'+r["dashboard_sha"]+'/corpus/manifest.json">Exact document, golden and font contracts</a></p></details></details>')
    if not records:
        parts.append('<p>unavailable — no measured attempts</p>')
    parts.append("""<script>document.querySelectorAll('.sort').forEach(button=>button.addEventListener('click',()=>{
const th=button.parentElement,table=th.closest('table'),index=Array.from(th.parentElement.children).indexOf(th);
const direction=button.dataset.direction==='asc'?-1:1;button.dataset.direction=direction===1?'asc':'desc';
const rows=Array.from(table.tBodies[0].rows);rows.sort((a,b)=>{
const x=a.cells[index]?.textContent||'',y=b.cells[index]?.textContent||'';
const nx=Number(x),ny=Number(y);return direction*(x!==''&&y!==''&&Number.isFinite(nx)&&Number.isFinite(ny)?nx-ny:x.localeCompare(y));});
rows.forEach(row=>table.tBodies[0].appendChild(row));}));</script>""")
    return "".join(parts)
