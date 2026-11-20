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
search.addEventListener("input", filterPages);
problems.addEventListener("change", filterPages);
filterPages();
