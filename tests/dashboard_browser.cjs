"use strict";
const assert = require("node:assert/strict");
const {chromium} = require("playwright-core");

const base = "http://127.0.0.1:8001/";
const failedRun = "44694231379-1";
const completeRun = "43756652815-1";

async function expectTab(page, id) {
    const tab = page.locator("#tab-" + id);
    assert.equal(await tab.getAttribute("aria-selected"), "true");
    assert.equal(await page.locator("main > section:visible").count(), 1);
    assert.ok(await page.locator("#" + id).isVisible());
}

async function test(browser) {
    const page = await browser.newPage({viewport: {width: 360, height: 800}});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("https://api.github.com/**/track-cohort.yml/runs?*", route => route.fulfill({
        json: {workflow_runs: []}
    }));
    await page.route("https://api.github.com/**/receipt-cohort.yml/runs?*", route => route.fulfill({
        json: {workflow_runs: [{id: 123, run_attempt: 2, status: "in_progress", conclusion: null,
            head_repository: {full_name: "postmelee/rhwp-fidelity-dashboard"}}]}
    }));
    await page.goto(base);
    await page.locator("#receipt-run-state").getByRole("link", {name: "Measurement in progress · 123"}).waitFor();
    await expectTab(page, "overview");
    assert.match(await page.locator("#overview").innerText(), /4 approved documents · 4 target pages/);
    assert.match(await page.locator("#overview").innerText(), /v0\.9\.1 · Unmeasured/);
    const picker = page.locator("#release-picker");
    await picker.selectOption({label: "v0.9.0 · c9095c5f"});
    const selected = page.locator(".release-view:visible");
    assert.equal(await selected.locator("dt", {hasText: "Paired pages / target"}).locator("+ dd").innerText(), "4/4");
    assert.match(await selected.innerText(), /CanvasKit unmeasured/);
    assert.match(await selected.innerText(), /Render Diff unlinked/);
    const largest = selected.locator("tbody tr:first-child td");
    assert.deepEqual(await largest.allTextContents(), ["pic-crop-01.hwp","1","94.65178","99.99756","+5.34578"]);
    await page.reload();
    assert.match(await selected.innerText(), /v0\.9\.0 · Smoke complete/);
    const v090 = await picker.inputValue();
    await page.locator("#tab-renderers").click();
    assert.equal(await picker.inputValue(), v090);
    assert.equal(await page.locator("#renderers details:visible").count(), 1);
    assert.match(await page.locator("#renderers").innerText(), /94.65178/);
    await page.locator("#tab-documents").click();
    await page.reload();
    assert.equal(await picker.inputValue(), v090);
    assert.equal(await page.locator("#documents details:visible").count(), 1);
    assert.match(await page.locator("#documents").innerText(), /pic-crop-01.hwp/);
    await picker.selectOption({index: 0});
    assert.match(await page.locator("#documents").innerText(), /Unmeasured/);
    await page.goBack();
    assert.equal(await picker.inputValue(), v090);
    await page.locator("#tab-overview").click();
    assert.equal(await selected.locator("dt", {hasText: "Both ≥90% / paired pages"}).locator("+ dd").innerText(), "4/4");
    assert.ok(await selected.getByRole("heading", {name: "Hancom page-count agreement"}).isVisible());
    assert.ok(await selected.getByRole("heading", {name: "Lowest page silhouette vs Hancom (%)"}).isVisible());
    await picker.selectOption({index: 0});
    assert.equal(await selected.locator("table").count(), 0);
    await page.locator("#tab-overview").focus();
    await page.keyboard.press("ArrowRight");
    await expectTab(page, "renderers");
    assert.equal(await page.evaluate(() => document.activeElement.id), "tab-renderers");
    await page.keyboard.press("End");
    await expectTab(page, "methods");
    await page.keyboard.press("Home");
    await expectTab(page, "overview");
    await page.keyboard.press("ArrowLeft");
    await expectTab(page, "methods");
    assert.ok(new URL(page.url()).hash.startsWith("#methods?release="));
    await page.goBack();
    await expectTab(page, "overview");
    await page.goForward();
    await expectTab(page, "methods");

    await page.goto(base + "#run-" + failedRun);
    await expectTab(page, "history");
    const failed = page.locator("#run-" + failedRun);
    assert.equal(await failed.getAttribute("open"), "");
    assert.match(await failed.innerText(), /Checkout contract failed/);
    assert.match(await failed.innerText(), /Pages publish job failed/);
    await page.locator("#filter").selectOption("complete");
    assert.ok(!(await failed.isVisible()));
    assert.match(await page.locator("#filter-result").innerText(), /0\/16/);
    await page.locator("#all-history").check();
    assert.match(await page.locator("#filter-result").innerText(), /3\/16/);
    await page.evaluate(id => { location.hash = "#run-" + id; }, completeRun);
    await page.locator("#run-" + completeRun + "[open]").waitFor();
    const complete = page.locator("#run-" + completeRun);
    assert.match(await complete.innerText(), /Measurement complete/);
    assert.match(await complete.innerText(), /Published/);
    await complete.getByRole("link", {name: "Renderer comparison"}).click();
    await expectTab(page, "renderers");
    const comparison = page.locator("#compare-" + completeRun);
    assert.equal(await comparison.getAttribute("open"), "");
    assert.equal(await page.evaluate(() => document.activeElement.tagName), "SUMMARY");
    const numeric = await (await page.request.get(base + "records/" + completeRun + ".json")).json();
    const snapshot = await (await page.request.get(base + "summary.json")).json();
    assert.deepEqual(snapshot.last_complete, numeric);
    const inventory = snapshot.corpus_inventory;
    assert.equal(inventory.source_paths, 3800);
    assert.equal(inventory.unique_blobs, 3651);
    assert.equal(inventory.receipt_verified_sources, 34);
    const overview = page.locator("#overview");
    assert.match(await overview.textContent(), /3,800/);
    assert.match(await overview.textContent(), /3,651/);
    const metrics = comparison.getByRole("table", {name: "Backend coverage and silhouette"});
    assert.deepEqual(await metrics.locator("thead th button").allTextContents(), ["Metric", "WASM Canvas2D", "Native Skia"]);
    await comparison.getByRole("link", {name: "Document and page details"}).click();
    const table = page.locator("#document-" + completeRun + " table");
    const scoreHeader = table.getByRole("button", {name: "Canvas2D vs Hancom (%)", exact: true});
    await scoreHeader.click();
    assert.equal(await scoreHeader.locator("..").getAttribute("aria-sort"), "ascending");
    const cells = await table.locator("tbody tr:first-child td").allTextContents();
    assert.equal(cells[0], "pic-crop-01.hwp");
    assert.equal(Number(cells[2]), Math.min(...numeric.measurement.backends.wasm.documents.map(d => d.scores[0].raw)));
    assert.equal(Number(cells[4]), +(Number(cells[3]) - Number(cells[2])).toFixed(5));
    for (const width of [320, 360, 1024]) {
        await page.setViewportSize({width, height: 800});
        for (const id of ["overview", "renderers", "documents", "history", "methods"]) {
            await page.locator("#tab-" + id).click();
            assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
            for (const region of await page.locator(".scroll:visible").all()) {
                assert.ok(await region.evaluate(node => node.scrollWidth <= node.clientWidth));
            }
        }
    }
    await page.goto(base + "#document-" + failedRun);
    await expectTab(page, "documents");
    assert.match(await page.locator("#document-" + failedRun).innerText(), /unavailable/);
    assert.deepEqual(errors, []);

    await page.goto(base + "#history");
    await page.getByRole("link", {name: /Historical PR #9024/}).click();
    const pageRows = page.locator("tbody tr");
    assert.equal(await pageRows.count(), 763);
    assert.deepEqual(await pageRows.filter({has: page.getByRole("cell", {name: "18", exact: true})}).locator("td").allTextContents(),
        ["18", "96.35", "100.00", "-3.65"]);
    await page.setViewportSize({width: 320, height: 720});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

    await page.goto(base + "corpus-index.html");
    await page.getByText("1–50 of 3800", {exact: true}).waitFor();
    await page.getByRole("button", {name: "Next", exact: true}).click();
    await page.getByText("51–100 of 3800", {exact: true}).waitFor();
    await page.locator("#query").fill("samples/issue8573/empty-host-split-table.hwp");
    await page.getByText("1–1 of 1", {exact: true}).waitFor();
    assert.equal(await page.locator("tbody tr").count(), 1);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth
        ? [...document.querySelectorAll("main *")].filter(node => node.getBoundingClientRect().right > innerWidth)
            .map(node => node.tagName + "#" + node.id).slice(0, 12)
        : []);
    assert.deepEqual(overflow, []);

    await page.goto(base);
    const coverage = page.locator("#overview .coverage-main:visible");
    assert.equal(await coverage.getByRole("progressbar").getAttribute("max"), "3800");
    assert.equal(await coverage.getByRole("progressbar").getAttribute("value"), "34");
    assert.match(await coverage.innerText(), /0\.89%/);
    await page.getByRole("link", {name: /Latest archived devel/}).click();
    await expectTab(page, "overview");
    assert.match(await picker.locator("option:checked").textContent(), /devel · 1a27faac/);
    assert.match(await coverage.innerText(), /0\.95%/);
    await page.reload();
    assert.equal(await coverage.getByRole("progressbar").getAttribute("value"), "36");
    const scope = page.locator("#overview .surface:visible").first();
    assert.equal(await scope.getByRole("link", {name: "Browse corpus paths"}).getAttribute("href"),
        "corpus-index.html?run=44967062895-1");
    const rendererRows = scope.locator("tbody tr");
    assert.deepEqual((await rendererRows.nth(0).locator("td").allTextContents()).slice(0, 3), ["Native Skia", "36", "50"]);
    assert.deepEqual((await rendererRows.nth(1).locator("td").allTextContents()).slice(0, 3), ["WASM Canvas2D", "41", "763"]);

    const noScript = await browser.newPage({javaScriptEnabled: false});
    await noScript.goto(base + "#methods");
    assert.ok(await noScript.locator("#overview").isVisible());
    assert.ok(await noScript.locator("#methods").isVisible());
    console.log("Browser smoke passed: tabs, keyboard, history, deep links, mobile, sorting, numeric JSON and no-JS.");
}

(async () => {
    const browser = await chromium.launch({executablePath: process.env.CHROME_BIN, args: ["--no-sandbox"]});
    try {
        await test(browser);
    } finally {
        await browser.close();
    }
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
