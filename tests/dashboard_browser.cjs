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
    await page.goto(base);
    await expectTab(page, "overview");
    assert.match(await page.locator("#overview").innerText(), /4 approved documents · 4 target pages/);
    assert.match(await page.locator("#overview").innerText(), /v0\.9\.1 · Unmeasured/);
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
    assert.equal(new URL(page.url()).hash, "#methods");
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
    assert.match(await page.locator("#filter-result").innerText(), /3 of 16 attempts/);
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
    const table = comparison.getByRole("table", {name: "Matched pages in this attempt"});
    const scoreHeader = table.getByRole("button", {name: "Canvas2D vs Hancom"});
    await scoreHeader.click();
    assert.equal(await scoreHeader.locator("..").getAttribute("aria-sort"), "ascending");
    const cells = await table.locator("tbody tr:first-child td").allTextContents();
    const wasm = numeric.measurement.backends.wasm.documents.find(doc => doc.id === cells[0]);
    const native = numeric.measurement.backends.native.documents.find(doc => doc.id === cells[0]);
    assert.equal(Number(cells[2]), wasm.scores[0].raw);
    assert.equal(Number(cells[3]), native.scores[0].raw);
    assert.equal(Number(cells[2]), Math.min(...numeric.measurement.backends.wasm.documents.map(d => d.scores[0].raw)));
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const region = comparison.getByRole("region", {name: "Matched pages in this attempt"});
    assert.ok(await region.evaluate(node => node.scrollWidth > node.clientWidth));
    await page.goto(base + "#document-" + failedRun);
    await expectTab(page, "documents");
    assert.match(await page.locator("#document-" + failedRun).innerText(), /unavailable/);
    assert.deepEqual(errors, []);

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
