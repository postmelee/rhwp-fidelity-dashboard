"use strict";
const table = document.querySelector("main .scroll:last-child table");
const search = document.getElementById("query");
const problems = document.getElementById("problems");
const nativeLower = document.getElementById("native-lower");
const handoff = document.getElementById("page-handoff");
const handoffTitle = document.getElementById("page-handoff-title");
const handoffData = document.getElementById("page-handoff-data");
const handoffStatus = document.getElementById("page-handoff-status");
const copyHandoff = document.getElementById("copy-page-handoff");
const recordLink = document.getElementById("cohort-record");
function filterPages() {
    let shown = 0;
    for (const row of table.tBodies[0].rows) {
        const counts = row.cells[5].textContent.split(" / ");
        const incomplete = row.cells[6].textContent !== "complete / complete" ||
            new Set(counts).size > 1 || counts.includes("?");
        row.hidden = !row.cells[0].textContent.includes(search.value.trim().toLowerCase()) ||
            (problems.checked && !incomplete) || (nativeLower.checked && !(Number(row.cells[4].textContent) < 0));
        if (!row.hidden) shown++;
    }
    document.getElementById("count").textContent = shown + " reference pages shown";
}
const order = document.getElementById("order");
const initial = Array.from(table.tBodies[0].rows);
function sortRows() {
    const rows = initial.slice();
    if (order.value === "gap") {
        const gap = r => Number.isFinite(Number(r.cells[4].textContent)) ? Math.abs(Number(r.cells[4].textContent)) : -1;
        rows.sort((a, b) => gap(b) - gap(a));
    } else if (order.value === "page") {
        rows.sort((a, b) => a.cells[0].textContent.localeCompare(b.cells[0].textContent) || Number(a.cells[1].textContent) - Number(b.cells[1].textContent));
    }
    table.tBodies[0].append(...rows);
}
order.addEventListener("change", sortRows);
search.addEventListener("input", filterPages);
nativeLower.addEventListener("change", filterPages);
problems.addEventListener("change", filterPages);
filterPages();

const pageRows = new Map(initial.map(row => ["#" + row.id, row]));
for (const [hash, row] of pageRows) {
    const cell = row.cells[1];
    const link = document.createElement("a");
    link.href = hash;
    link.textContent = cell.textContent;
    link.setAttribute("aria-label", `Reproduce ${row.cells[0].textContent}, reference page ${link.textContent}`);
    cell.replaceChildren(link);
    link.addEventListener("click", event => {
        if (location.hash === hash && !event.ctrlKey && !event.metaKey &&
                !event.shiftKey && !event.altKey) {
            event.preventDefault();
            showPageHandoff();
        }
    });
}

let archive;
function loadArchive() {
    archive ??= fetch(recordLink.href).then(response => {
        if (!response.ok) throw new Error("Numeric record unavailable");
        return response.json();
    }).catch(error => {
        archive = null;
        throw error;
    });
    return archive;
}

function reproduction(record, row, permalink) {
    const id = row.cells[0].textContent;
    const page = Number(row.cells[1].textContent);
    const doc = record.docs.find(item => item.id === id);
    if (!doc || !Number.isInteger(page) || page < 1 || page > doc.pages) {
        throw new Error("Page missing from numeric record");
    }
    const stageName = doc === record.docs[0] ? "pilot" : "expanded";
    const stage = record.stages[stageName];
    const backendResults = {};
    for (const [backend, name] of [["native", "Native Skia"], ["wasm", "WASM Canvas2D"]]) {
        const observed = stage?.measurement.backends[backend].documents.find(item => item.id === id);
        const evidence = stage?.artifacts[backend + "/" + id];
        backendResults[name] = {
            status: observed?.status ?? "unavailable",
            rendered_pages: observed?.rendered_pages ?? null,
            silhouette_percent: observed?.scores.find(score => score.page === page)?.raw ?? null,
            ...evidence,
        };
    }
    return {
        page_permalink: permalink,
        numeric_record: recordLink.href,
        release: record.tag,
        engine_sha: record.engine_sha,
        corpus_sha: record.corpus_sha,
        document_id: id,
        source_path_sha256: doc.path_sha256,
        source_sha256: doc.source_sha256,
        hancom_pdf_sha256: doc.pdf_sha256,
        receipt_sha256: record.receipt_sha256,
        hancom_reference_page: page,
        hancom_pdf_pages: doc.pages,
        protocol: record.protocol,
        profile: "print",
        dpi: 96,
        measurement: stage ? {
            run: `https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/${stage.run_id}/attempts/${stage.attempt}`,
            stage: stageName,
            producer_sha: stage.producer_sha,
            build_sha256: stage.measurement.build_sha256,
            environment_sha256: stage.measurement.environment_sha256,
        } : null,
        backends: backendResults,
    };
}

async function showPageHandoff() {
    const hash = location.hash;
    const row = pageRows.get(hash);
    handoff.hidden = !row;
    if (!row) return;
    if (row.hidden) {
        search.value = "";
        problems.checked = nativeLower.checked = false;
        filterPages();
    }
    handoffTitle.textContent = `${row.cells[0].textContent} · reference page ${row.cells[1].textContent}`;
    handoffTitle.focus();
    document.getElementById("page-permalink").href = hash;
    handoffData.value = "";
    copyHandoff.disabled = true;
    handoffStatus.textContent = "Loading the numeric record…";
    try {
        const record = await loadArchive();
        if (location.hash !== hash) return;
        const details = reproduction(record, row, location.href);
        handoffData.value = JSON.stringify(details, null, 2);
        copyHandoff.disabled = false;
        handoffStatus.textContent = "";
    } catch {
        if (location.hash === hash) handoffStatus.textContent = "The numeric record could not be read.";
    }
}

copyHandoff.addEventListener("click", async () => {
    const hash = location.hash;
    const value = handoffData.value;
    try {
        await navigator.clipboard.writeText(value);
        if (location.hash === hash) handoffStatus.textContent = "Reproduction details copied.";
    } catch {
        if (location.hash !== hash) return;
        handoffData.focus();
        handoffData.select();
        handoffStatus.textContent = "Use your device’s copy command to copy the selected details.";
    }
});
window.addEventListener("hashchange", showPageHandoff);
showPageHandoff();
