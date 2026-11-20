"use strict";
const table = document.querySelector("main .scroll:last-child table");
const search = document.getElementById("query");
const problems = document.getElementById("problems");
function filterPages() {
    let shown = 0;
    for (const row of table.tBodies[0].rows) {
        const counts = row.cells[5].textContent.split(" / ");
        const incomplete = row.cells[6].textContent !== "complete / complete" ||
            new Set(counts).size > 1 || counts.includes("?");
        row.hidden = !row.cells[0].textContent.includes(search.value.trim().toLowerCase()) ||
            (problems.checked && !incomplete);
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
problems.addEventListener("change", filterPages);
filterPages();
