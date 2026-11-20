"use strict";
(async function showMeasurementStatus() {
    const status = document.getElementById("receipt-run-state");
    if (!status) return;
    const endpoint = "https://api.github.com/repos/postmelee/rhwp-fidelity-dashboard/actions/workflows/receipt-cohort.yml/runs?per_page=20";
    const active = new Set(["queued", "in_progress", "waiting", "pending", "requested"]);
    const failed = new Set(["failure", "timed_out", "cancelled", "action_required", "startup_failure"]);
    async function update() {
        try {
            const response = await fetch(endpoint, {credentials: "omit", signal: AbortSignal.timeout(8000)});
            if (!response.ok) throw new Error("Status lookup failed");
            const {workflow_runs: runs} = await response.json();
            const own = runs.filter(r => r.head_repository?.full_name === "postmelee/rhwp-fidelity-dashboard" &&
                Number.isSafeInteger(r.id) && Number.isSafeInteger(r.run_attempt));
            const current = own.find(r => active.has(r.status));
            const failure = own.find(r => failed.has(r.conclusion));
            status.replaceChildren();
            function link(run, label) {
                const a = document.createElement("a");
                a.href = "https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/" + run.id + "/attempts/" + run.run_attempt;
                a.textContent = label;
                status.append(a);
            }
            if (current) link(current, "Measurement " + current.status.replaceAll("_", " ") + " · " + current.id);
            else status.append("No measurement currently queued or running in the latest 20 attempts.");
            if (failure) {
                status.append(" · ");
                link(failure, "Recent " + failure.conclusion + " · " + failure.id);
            }
            if (current) setTimeout(() => { if (!document.hidden) update(); }, 120000);
        } catch {
            status.textContent = "Live measurement status unavailable. Archived coverage is shown below.";
        }
    }
    await update();
})();
