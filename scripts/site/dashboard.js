"use strict";

const nav = document.querySelector("nav");
const tabs = Array.from(nav.querySelectorAll("a"));
const panels = tabs.map(tab => document.getElementById(tab.hash.slice(1)));
const filter = document.getElementById("filter");

function filterHistory() {
    if (!filter) return;
    const runs = Array.from(document.querySelectorAll(".history-run"));
    for (const run of runs) {
        run.hidden = Boolean(filter.value && run.dataset.status !== filter.value);
    }
    const count = runs.filter(run => !run.hidden).length;
    document.getElementById("filter-result").textContent = count + " of " + runs.length + " attempts shown.";
}

function activate(index) {
    for (const [i, tab] of tabs.entries()) {
        tab.setAttribute("aria-selected", String(i === index));
        tab.tabIndex = i === index ? 0 : -1;
        panels[i].hidden = i !== index;
    }
}

function showHash({focus = false} = {}) {
    const target = document.getElementById(location.hash.slice(1));
    const panel = target?.closest("main > section") ?? panels[0];
    activate(panels.indexOf(panel));
    if (target instanceof HTMLDetailsElement) {
        if (filter && target.classList.contains("history-run") && target.hidden) {
            filter.value = "";
            filterHistory();
        }
        target.open = true;
        target.scrollIntoView({block: "nearest"});
    }
    if (focus) {
        (target?.querySelector("summary") ?? panel).focus({preventScroll: true});
    }
}

nav.setAttribute("role", "tablist");
for (const [i, tab] of tabs.entries()) {
    const panel = panels[i];
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panel.id);
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    panel.tabIndex = 0;
    tab.addEventListener("click", event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (location.hash !== tab.hash) history.pushState(null, "", tab.hash);
        activate(i);
    });
    tab.addEventListener("keydown", event => {
        const destination = {
            ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i + tabs.length - 1) % tabs.length,
            Home: 0, End: tabs.length - 1,
        }[event.key];
        if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            tab.click();
        } else if (destination !== undefined) {
            event.preventDefault();
            tabs[destination].focus();
            tabs[destination].click();
        }
    });
}
window.addEventListener("hashchange", () => showHash());
for (const link of document.querySelectorAll('main a[href^="#"], .skip')) {
    link.addEventListener("click", event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (location.hash !== link.hash) history.pushState(null, "", link.hash);
        showHash({focus: true});
    });
}

if (filter) {
    filter.hidden = false;
    filter.labels[0].hidden = false;
    filter.addEventListener("change", filterHistory);
    filterHistory();
}
showHash();

for (const button of document.querySelectorAll(".sort")) {
    button.hidden = false;
    button.nextElementSibling.hidden = true;
    button.addEventListener("click", () => {
        const header = button.closest("th");
        const column = header.cellIndex;
        const table = header.closest("table");
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        if (rows.some(row => row.cells.length <= column)) return;
        const ascending = header.getAttribute("aria-sort") !== "ascending";
        for (const cell of table.tHead.rows[0].cells) cell.removeAttribute("aria-sort");
        header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        rows.sort((a, b) => {
            const left = a.cells[column].textContent.trim();
            const right = b.cells[column].textContent.trim();
            if (left === "unavailable") return right === "unavailable" ? 0 : 1;
            if (right === "unavailable") return -1;
            const isNumeric = left !== "" && right !== "" && Number.isFinite(Number(left)) && Number.isFinite(Number(right));
            const order = isNumeric ? Number(left) - Number(right) : left.localeCompare(right, undefined, {numeric: true});
            return ascending ? order : -order;
        });
        for (const row of rows) tbody.appendChild(row);
    });
}
