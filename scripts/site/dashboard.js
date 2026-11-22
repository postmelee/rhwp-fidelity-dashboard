"use strict";

const nav = document.querySelector("nav");
const tabs = Array.from(nav.querySelectorAll("a"));
const panels = tabs.map(tab => document.getElementById(tab.hash.slice(1)));
const filter = document.getElementById("filter");

const allHistory = document.getElementById("all-history");
const releasePicker = document.getElementById("release-picker");
const options = new Set(Array.from(releasePicker.options, option => option.value));
const views = Array.from(document.querySelectorAll(".release-view"));

function filterHistory() {
    if (!filter) return;
    const runs = Array.from(document.querySelectorAll(".history-run"));
    for (const run of runs) {
        const sameRelease = releasePicker.value === "release-" + run.dataset.release;
        run.hidden = (!allHistory.checked && !sameRelease) || Boolean(filter.value && run.dataset.status !== filter.value);
    }
    const count = runs.filter(run => !run.hidden).length;
    document.getElementById("filter-result").textContent = "Visible / total attempts · " + count + "/" + runs.length;
}

function activate(index) {
    for (const [i, tab] of tabs.entries()) {
        tab.setAttribute("aria-selected", String(i === index));
        tab.tabIndex = i === index ? 0 : -1;
        panels[i].hidden = i !== index;
    }
}

function panelHash(id) {
    return "#" + id + "?release=" + releasePicker.value.slice(8);
}

releasePicker.parentElement.hidden = false;
releasePicker.addEventListener("change", () => {
    const active = panels.find(panel => !panel.hidden);
    history.pushState(null, "", panelHash(active.id));
    showHash();
});

function showHash({focus = false} = {}) {
    const [id, query] = location.hash.slice(1).split("?");
    const target = document.getElementById(id);
    const panel = target?.closest("main > section") ?? panels[0];
    const sha = target?.dataset.release ?? new URLSearchParams(query).get("release");
    const requested = target?.classList.contains("release-view") ? target.id : "release-" + sha;
    releasePicker.value = options.has(requested) ? requested : releasePicker.options[0].value;
    for (const view of views) view.hidden = view.id !== releasePicker.value;
    for (const view of document.querySelectorAll("[data-preferred]")) {
        const exact = target?.matches("[data-preferred]") && target.parentElement === view.parentElement;
        view.hidden = "release-" + view.dataset.release !== releasePicker.value ||
            (exact ? view !== target : view.dataset.preferred !== "true");
    }
    for (const [i, tab] of tabs.entries()) tab.href = panelHash(panels[i].id);
    for (const card of revisionCards) {
        if (card.dataset.revision === releasePicker.value.slice(8)) card.setAttribute("aria-current", "true");
        else card.removeAttribute("aria-current");
    }
    for (const link of document.querySelectorAll("[data-panel-link]")) link.href = panelHash(link.dataset.panelLink);
    activate(panels.indexOf(panel));
    if (target?.classList.contains("history-run") && filter.value !== target.dataset.status) filter.value = "";
    filterHistory();
    if (target instanceof HTMLDetailsElement) {
        target.open = true;
        target.scrollIntoView({block: "nearest"});
    }
    if (focus) ((target instanceof HTMLDetailsElement && target.querySelector("summary")) || panel).focus({preventScroll: true});
}
for (const link of document.querySelectorAll('main a[href^="#"], .skip, .brand')) {
    if (panels.some(panel => "#" + panel.id === link.hash)) link.dataset.panelLink = link.hash.slice(1);
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
        showHash();
    });
    tab.addEventListener("keydown", event => {
        const destination = {
            ArrowDown: (i + 1) % tabs.length, ArrowUp: (i + tabs.length - 1) % tabs.length,
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
for (const link of document.querySelectorAll('main a[href^="#"], .skip, .brand')) {
    link.addEventListener("click", event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        if (location.hash !== link.hash) history.pushState(null, "", link.hash);
        showHash({focus: true});
    });
}

const revisionCards = Array.from(document.querySelectorAll("[data-revision-overview]"));
for (const card of revisionCards) {
    card.addEventListener("click", event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const hash = "#overview?release=" + card.dataset.revision;
        if (!options.has("release-" + card.dataset.revision)) return;
        event.preventDefault();
        if (location.hash !== hash) history.pushState(null, "", hash);
        showHash({focus: true});
        window.scrollTo({top: 0});
    });
}

if (filter) {
    filter.hidden = false;
    filter.labels[0].hidden = false;
    filter.addEventListener("change", filterHistory);
    allHistory.parentElement.hidden = false;
    allHistory.addEventListener("change", filterHistory);
}
showHash();

for (const button of document.querySelectorAll(".sort")) {
    button.setAttribute("aria-label", button.textContent);
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
