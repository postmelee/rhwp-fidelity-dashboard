# Dashboard preview

The five views support direct links. Use `#overview`, `#renderers`, `#documents`, `#history` or `#methods`. Link to one immutable attempt with `#run-<run_id>-<attempt>`, or use `#compare-…` and `#document-…` to open its results directly. The navigation supports Left, Right, Home and End. With JavaScript disabled it works as an ordinary section index.

The PR Checks workflow builds a downloadable `dashboard-preview` artifact from the existing public numeric ledger at `17e6e4463c950c988c93b3ddb1afa09d8e556634`. Extract it, then run `python3 -m http.server 8001 --directory /path/to/extracted-preview` and open `http://127.0.0.1:8001/`. The preview uses `python3 scripts/build_preview.py --ledger PATH --out preview`. The production and review workflows share the same site renderer. The review reads the pinned example ledger, while production reads the current durable ledger. The preview and its tests have no measurement or Pages job.

The ledger stays authoritative for scores and measurement outcome. `scripts/site/evidence.json` records separately audited Actions jobs for particular attempts and an observed release tag/SHA. Pages status applies to the listed job, and an unaudited job remains unknown. The release check is dated; a later build can show a matching ledger record by SHA. The approved four documents form a smoke corpus.

## Production rollout

Main pushes run the Pages workflow, which reads the validated ledger and deploys the static site. Fidelity handles scheduled or manual measurements and calls the same publisher after recording the result. Pages publication has no ledger write permission. The public response is checked against the generated HTML, CSS, JavaScript and every numeric record.

Run [44694231379](https://github.com/postmelee/rhwp-fidelity-dashboard/actions/runs/44694231379) selected v0.7.10 and stopped in the checkout contract probe. Its Pages artifact was visible through REST but the deploy action failed to find it through its own artifact listing. The new workflow uses the pinned official Pages upload and deploy actions, with a separate ledger-only rerun path. The cause of the earlier listing discrepancy remains unconfirmed.
