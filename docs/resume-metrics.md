# Verified resume metrics

These claims concern synthetic experiments or verified software functionality, not real deployments or injury reduction.

1. Built a Python/OR-Tools multi-crew scheduler supporting 100-job, 10-crew synthetic workloads under skill, shift and deadline constraints, with independently validated outputs and a separate travel-aware mode.
2. Evaluated four scheduling policies across 165 seeded synthetic scenarios; achieved 8.47% mean modeled Heat Load reduction on 117 valid, nonzero-baseline heat-first pairs, with explicit timeout and delay reporting.
3. Integrated provenance-aware weather providers, offline fallback, Streamlit/CLI workflows and CSV/JSON exports, backed by 162 automated tests and Python 3.11/3.12 CI.

## Evidence and caveats

| Claim | Evidence |
|---|---|
| 100 jobs / 10 crews | `reports/benchmark_results.csv`, jobs=100; `reports/benchmark_details.jsonl.gz` |
| 8.47% mean reduction | Main heat_first rows with defined reduction, n=117 out of 150 attempted scenarios; zero-baseline and unsuccessful pairs excluded explicitly |
| 165 scenarios / four policies | `benchmarks/final.json`; 660 rows include NOT_RUN/UNKNOWN where applicable |
| 162 tests; two Python versions | `python -m pytest -q`; GitHub Actions run 37857898141 passed both Python 3.11 and 3.12 |
| Build-time microbenchmark | `reports/profiling.csv`: median 0.679558 → 0.510717 s (24.85% reduction), five paired development trials; not total solver speedup |

All 100-job solved results were feasible incumbents, not proven-optimal schedules. Valid large-case solves: 11/12 planned policy rows. Do not claim 100% solve success.
Heat-first can add substantial weighted scheduling delay. The original real-snapshot Phoenix result remains 2.971485%; the synthetic mean is a separate experiment and does not replace it.

## Reproduction

```bash
python scripts/run_benchmarks.py --manifest benchmarks/final.json
python scripts/profile_scheduler.py
python -m pytest -q
python -m heatops.cli --mode heat_first --format json
```
