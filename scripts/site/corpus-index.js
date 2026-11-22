"use strict";
async function start() {
    const response = await fetch("corpus-index.json");
    if (!response.ok) throw new Error("Inventory unavailable");
    const data = await response.json();
    const query = document.getElementById("query");
    const state = document.getElementById("state");
    const count = document.getElementById("count");
    const body = document.querySelector("tbody");
    const labels = Array.from(document.querySelectorAll("th"), node => node.textContent);
    const run = document.getElementById("run");
    for (const entry of [...data.runs].reverse()) {
        run.add(new Option(entry.tag + " · " + entry.sha.slice(0, 12) + " · " + entry.key, entry.key));
    }
    const requested = new URL(location.href).searchParams.get("run");
    if (requested && !data.runs.some(entry => entry.key === requested)) {
        throw new Error("Unknown measurement run");
    }
    const preferred = data.run_id == null ? null : data.run_id + "-" + data.attempt;
    if (requested || preferred) run.value = requested || preferred;
    let activeRows = [];
    let generation = 0;
    async function selectRun() {
        const current = ++generation;
        const key = run.value;
        const url = new URL(location.href);
        if (key) url.searchParams.set("run", key);
        history.replaceState(null, "", url);
        count.textContent = "Loading measurement…";
        body.replaceChildren();
        activeRows = [];
        let scores = {};
        if (key) {
            const result = await fetch("measured-paths/" + encodeURIComponent(key) + ".json");
            if (!result.ok) throw new Error("Measurement unavailable");
            scores = await result.json();
        }
        if (current !== generation) return;
        activeRows = data.rows.map(row => ({...row, ...(scores[row.path_sha256] || {
            id: null, page_median_percent: {native: null, wasm: null},
            status: row.receipt_verified ? "Verified · unmeasured" : "Outside audited receipt set"
        })}));
        activeRows.sort((a, b) => Number(a.status === "Outside audited receipt set") -
            Number(b.status === "Outside audited receipt set") || (a.id || a.path_sha256).localeCompare(b.id || b.path_sha256));
        state.replaceChildren(new Option("All", ""));
        for (const value of [...new Set(activeRows.map(r => r.status))].sort()) state.add(new Option(value, value));
        offset = 0;
        await render();
    }
    const prev = document.getElementById("prev"), next = document.getElementById("next");
    let offset = 0, revision = 0;
    async function render() {
        const seq = ++revision;
        const input = query.value.trim();
        let needle = input.toLowerCase();
        if (input.includes("/")) {
            const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
            needle = Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
        }
        if (seq !== revision) return;
        const rows = activeRows.filter(r => (!state.value || r.status === state.value) &&
            [r.path_sha256, r.blob, r.id || "", r.root].some(v => v.includes(needle)));
        if (offset >= rows.length) offset = 0;
        body.replaceChildren();
        for (const r of rows.slice(offset, offset + 50)) {
            const tr = body.insertRow();
            const axes = r.visual_deferrals.flatMap(x => x.axes.map(axis => axis + " #" + x.issue)).join(", ");
            const fields = [r.id || r.path_sha256.slice(0, 16), r.root, r.format, r.paths_with_same_blob, r.status, ...["native", "wasm"].map(b => r.page_median_percent[b]?.toFixed(5) ?? "Unmeasured"), (r.id ? "Admitted run reference" : r.oracle_state.replaceAll("_", " ")), r.resolver_scope, axes || "—"];
            fields.forEach((value, i) => {
                const cell = tr.insertCell();
                cell.dataset.label = labels[i];
                cell.textContent = value;
                if (!i) cell.title = r.path_sha256;
            });
        }
        count.textContent = rows.length ? (offset + 1) + "–" + Math.min(offset + 50, rows.length) + " of " + rows.length : "0 paths";
        prev.disabled = offset === 0;
        next.disabled = offset + 50 >= rows.length;
    }
    function reset() { offset = 0; render(); }
    query.addEventListener("input", reset);
    state.addEventListener("change", reset);
    prev.onclick = () => { offset -= 50; render(); };
    next.onclick = () => { offset += 50; render(); };
    run.addEventListener("change", () => selectRun().catch(() => { count.textContent = "Measurement unavailable"; }));
    await selectRun();
}
start().catch(() => { document.getElementById("count").textContent = "Inventory unavailable"; });
