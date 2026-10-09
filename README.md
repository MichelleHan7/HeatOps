# HeatOps v2

[![CI](https://github.com/MichelleHan7/HeatOps/actions/workflows/ci.yml/badge.svg)](https://github.com/MichelleHan7/HeatOps/actions/workflows/ci.yml)

**Heat-aware, multi-crew field operations scheduling with reproducible evaluation.**

HeatOps assigns jobs to qualified crews under time windows, shifts, availability
and optional travel constraints using OR-Tools CP-SAT. It compares operational
Heat Load with priority-weighted task delay. Heat Load is a modeled planning
metric, not a medical score or evidence of prevented heat illness.

[Live demo](https://heatops-fortyguard.streamlit.app/) ·
[Architecture](docs/architecture.md) · [Benchmark results](docs/benchmark-results.md) ·
[Reproduction methodology](docs/benchmark-methodology.md)

Core v2 was merged through PR #3. This follow-up branch contains the completed
benchmark artifacts and documentation. Deployment status after that merge has
not been independently checked. The default local page preserves Phoenix; enable
**Multi-crew workspace** in the sidebar to use v2.

## Features

- Multiple heterogeneous crews, exactly-once assignment, skill/shift/deadline and
  service-availability constraints; independently validated returned schedules.
- Operations-first, heat-first, balanced and explicit extra-delay-budget policies.
- Optional depot-to-first / consecutive-task travel using estimated geography or
  directed travel-time overrides. Route lines show order, not road navigation.
- Offline Phoenix snapshot and clearly labeled synthetic scenarios; optional
  FortyGuard and Open-Meteo providers with provenance and visible fallback.
- Per-crew timelines, locations, temperature curves, utilization, status/gap and
  comparison metrics; schedule CSV/JSON and comparison/metrics JSON downloads.
- Seeded scenario generator, fixed benchmark manifest, failure-inclusive reports,
  confidence intervals, build/solve timings and scalability experiments.

## Quick start

Python 3.11 or 3.12:

```bash
git clone https://github.com/MichelleHan7/HeatOps.git
cd HeatOps
git switch feature/heatops-v2-results
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[demo,dev]"
python -m streamlit run app.py
```

No API key is needed. `requirements.txt` installs the dashboard extra for
Streamlit Community Cloud. Dev extras include plotting for benchmark reports.

## CLI and scenarios

```bash
# Historical single-crew behavior is unchanged.
heatops-evaluate --mode heat_first --format json

# Fleet evaluation of bundled Phoenix jobs and both existing crews.
heatops-evaluate --all-workers --policy delay_budget --delay-budget 60 --format json

# Generate an explicitly synthetic 100-job, 10-crew workload.
python scripts/generate_scenarios.py --jobs 100 --crews 10 --seed 42 --output reports/scenario.json
heatops-evaluate --scenario reports/scenario.json --policy balanced --time-limit 30 --format json

# Optional travel on a small workload.
heatops-evaluate --all-workers --policy heat_first --travel
```

The delay budget is **additional priority-weighted minutes**, not minutes on the
wall clock. A v2 scenario bundle contains `jobs`, `workers`, `temperature_matrix`,
`metadata` and an optional independently checked `witness`. Existing separate
JSON input flags also work with `--all-workers`. Legacy `--heat-priority` remains
available on the original single-crew path.

The dashboard accepts scenario JSON or jobs CSV + workers CSV + temperature JSON.
CSV columns match the Job/Worker dataclasses; worker skills use `;` separators and
optional `unavailable` is a JSON array of `[start,end]` pairs. Uploaded temperature
sources are labeled unverified unless declared in bundle metadata. The synthetic
generator rejects workloads too large for its crew capacity rather than silently
dropping jobs. `--settings config.json` configures shifts, duration choices,
priority/intensity ranges, locations, skills, window slack and temperature controls
(see `GeneratorSettings`). Standard sizes are 5, 10, 25, 50 and 100; crews range from 1 to 10.

## Evidence and reproduction

The original five-job Phoenix **Heat-first** case remains **40.3827 → 39.1827
Heat Load (2.9715%)**, using the unchanged 2026-08-24 FortyGuard snapshot. Its raw
delay rises from 4.5 to 10.25 task-hours; this operational cost is disclosed.
The original snapshot lacks API activity IDs; provenance has not been invented.
See `reports/phoenix-baseline.json` and `tests/test_phoenix_demo_scenario.py`.

V2 results are separate synthetic experiments. The preregistered main suite uses
30 seeds for each of five temperature families, plus scaling and travel cohorts.
See [executed results](docs/benchmark-results.md), raw `reports/benchmark_results.csv`,
full assignments in `reports/benchmark_details.jsonl.gz` and environment metadata.

```bash
python scripts/run_benchmarks.py --manifest benchmarks/final.json
python scripts/profile_scheduler.py
```

Full benchmarks take several minutes or longer; they never run on dashboard load
or normal CI. `--resume` only accepts matching source/manifest hashes. Time limits
apply to solves; end-to-end runtime also includes model construction. A time-limit
incumbent is FEASIBLE, never OPTIMAL. Zero-heat baselines produce undefined reduction,
not an invented percentage. See [verified resume claims](docs/resume-metrics.md).

## Verified v2 results

The completed suite contains 165 synthetic instances and 660 policy records:
582 OPTIMAL, 72 FEASIBLE, 5 UNKNOWN, and 1 NOT_RUN. All 654 returned schedules
passed independent validation. For 100 jobs / 10 crews, 11 of 12 policy attempts
returned feasible incumbents; none proved optimal within the 30-second solve cap.

On the main suite, heat-first achieved **8.47% mean reduction** over **117 valid,
nonzero-baseline paired cases** (150 scenarios attempted; exclusions disclosed).
The median was 3.67%. Heat-first also adds scheduling delay; see the full
[implementation report](docs/final-implementation-report.md) for trade-offs.
These synthetic results are separate from the preserved 2.97% Phoenix snapshot.

## Weather

Choose offline data, Open-Meteo or FortyGuard in the fleet workspace. Sources and
actual data dates are displayed and exported; failures visibly retain scenario
data. Open-Meteo historical output is reanalysis, not station measurements.
See [provider contract and terms](docs/weather-providers.md). Keep credentials in
local environment variables or Streamlit secrets; never commit them.
The original [FortyGuard integration](docs/api-integration.md) remains available.

## Quality gates

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m compileall -q src app.py scripts tests
heatops-evaluate --mode heat_first --format json
```

CI runs these checks on Python 3.11/3.12. Tests include independent feasibility,
legacy regression, travel sequencing, weather failures, benchmark smoke tests,
CLI/export checks and Streamlit AppTest. Unit tests require no API credentials.

## Limits

This is a portfolio scheduling system, not a deployed workforce product. Results
on synthetic workloads do not establish real-world heat-risk reduction. Larger
instances can return feasible-but-unproven solutions or no incumbent before timeout.
Travel mode is guarded at 25 jobs, uses approximate straight-line distances, and
does not require return to depot. Availability blocks task execution, not travel.
No cross-midnight jobs, production authentication, persistence or medical advice.
Optional FastAPI/PostgreSQL work is deferred; core optimization and measurement
remain the focus. See [design decisions](docs/v2-design-decisions.md).

## Hackathon history

HeatOps began as a FortyGuard hackathon project in August 2026: one Phoenix crew,
five utility tasks, Streamlit and a saved API temperature matrix. V2 extends that
layered Python codebase, retains the original demonstration, and adds workforce
assignment and reproducible engineering evidence rather than targeting an
arbitrary improvement percentage.
