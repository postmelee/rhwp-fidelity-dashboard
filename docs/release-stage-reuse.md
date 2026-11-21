# Reusing a measured stage for a stable release

The stable tag keeps its own ledger record. A release maintainer can provide reviewed target expectations in `corpus/release-stage-locks.json`, keyed first by exact stable tag and then by `pilot` or `expanded`. Each entry identifies the original numeric ledger by integer `run_id` and `attempt` and supplies four SHA-256 fields.

- `build_sha256` and `environment_sha256` identify the required measured build and runtime. Establish these from independent release build/environment evidence and link that evidence in the change introducing the lock.
- `scope_sha256` pins the canonical JSON digest of the selected document/page scope, backend names, print profile, DPI, protocol, font supplies, engine, producer, corpus and Print receipt.
- `stage_sha256` pins the canonical JSON digest of the complete original stage. Its archived producer identity stays attached to that stage.

The planner validates the original ledger and both file hash lists. A matching engine SHA alone cannot establish release build, runtime or font identity. Without a compatible lock the stage runs fresh. Introduce a lock only when the target conditions are independently known. The initial implementation ships without release locks.
