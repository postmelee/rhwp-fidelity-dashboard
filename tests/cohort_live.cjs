"use strict";
const assert = require("node:assert/strict");
const {chromium} = require("playwright-core");
const base = "https://postmelee.github.io/rhwp-fidelity-dashboard/";
async function run() {
    const browser = await chromium.launch({executablePath: process.env.CHROME_BIN, args: ["--no-sandbox"]});
    try {
        const page = await browser.newPage({viewport: {width: 360, height: 800}});
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        const runs = await (await page.request.get(base + "cohort-runs.json")).json();
        const index = await (await page.request.get(base + "corpus-index.json")).json();
        await page.goto(base + "corpus-index.html");
        await page.getByText("1–50 of " + index.rows.length, {exact: true}).waitFor();
        for (const run of runs.slice(-1)) {
            const record = await (await page.request.get(base + run.record)).json();
            const key = run.run_id + "-" + run.attempt;
            await page.goto(base + "cohort-" + key + ".html");
            await page.getByText(run.target_pages + " reference pages shown", {exact: true}).waitFor();
            await page.locator("#query").fill(record.docs[0].id);
            await page.getByText(record.docs[0].pages + " reference pages shown", {exact: true}).waitFor();
            await page.locator("#order").selectOption("page");
            const pilot = record.stages.pilot;
            if (pilot) {
                for (const [i, b] of ["native", "wasm"].entries()) {
                    const first = pilot.measurement.backends[b].documents.find(d => d.id === record.docs[0].id);
                    const score = first?.scores.find(s => s.page === 1)?.raw;
                    if (score != null) assert.equal(await page.locator("main .scroll:last-child tbody tr:visible").first()
                        .locator("td").nth(2 + i).innerText(), score.toFixed(5));
                }
            }
            await page.locator("#problems").check();
            await page.setViewportSize({width: 320, height: 720});
            assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        }
        assert.deepEqual(errors, []);
    } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
