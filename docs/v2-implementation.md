# HeatOps v2 implementation log

Starting commit: `0171e58` (Fix architecture formula rendering).
Branch: `feature/heatops-v2`. This implementation initially left main and deployment settings untouched.
On resumption, PR #3 was observed already merged by the repository side;
completed results are delivered through `feature/heatops-v2-results`.

## Audit

The legacy scheduler creates one Boolean and one optional fixed interval per
job/start, uses candidate-wide min-max normalization, and selects one worker.
Its callers include the baseline, comparison service, CLI, and Phoenix dashboard.
The existing Worker already represents skills, shift and depot coordinates.
The bundled snapshot is dated 2026-08-24; original API activity IDs were not
retained. Its provenance is preserved, not strengthened retrospectively.

## Compatibility and scaling decisions

Keep the historical single-worker engine, CLI defaults and dashboard intact.
Add a v2 engine and comparison service with explicit result diagnostics.
Use job/worker/start assignment Booleans but only one optional interval per
eligible job/worker (rather than one interval per candidate). Cache heat by
job/start. Scheduling-only is the scalable default; optional circuit sequencing
models depot-to-first and consecutive travel exactly, with a 25-job safeguard.
Travel estimates are geographic approximations, not road directions.
New v2 policies share a feasible set. Delay budgets use priority-weighted minutes.
The original result remains a regression artifact in reports/phoenix-baseline.json.

## Initial verification

113 existing tests passed (6.32 s). Ruff lint/format and compileall passed.
Timed legacy comparison: 0.200646 s (includes both solves and file I/O).
Baseline and optimized: OPTIMAL, OPTIMAL.
Heat Load: 40.382716 → 39.182749; reduction 2.971485%.
Raw delay hours: 4.500000 → 10.250000.

## Final status

Core phases 0–8 implemented; production deployment remains pending review and
optional phase 9 is deferred. 162 tests and the Python 3.11/3.12 CI matrix pass.
165 scenarios / 660 policy rows completed, including failures and unrun budget
policies; 654 returned schedules independently validated. See
[final implementation report](final-implementation-report.md) for exact results,
all limitations, changed files and resume evidence.
