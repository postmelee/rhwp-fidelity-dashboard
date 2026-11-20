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
    for (const s of Object.keys(data.status_counts).sort()) state.add(new Option(s, s));
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
        const rows = data.rows.filter(r => (!state.value || r.status === state.value) &&
            [r.path_sha256, r.blob, r.id || "", r.root].some(v => v.includes(needle)));
        if (offset >= rows.length) offset = 0;
        body.replaceChildren();
        for (const r of rows.slice(offset, offset + 50)) {
            const tr = body.insertRow();
            const axes = r.visual_deferrals.flatMap(x => x.axes.map(axis => axis + " #" + x.issue)).join(", ");
            const fields = [r.id || r.path_sha256.slice(0, 16), r.root, r.format, r.paths_with_same_blob, r.status, r.resolver_scope, axes || "—"];
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
    await render();
}
start().catch(() => { document.getElementById("count").textContent = "Inventory unavailable"; });
