# HeatOps — hackathon submission copy

This page is a copy-ready submission package aligned to the deliverables listed
on the [FortyGuard Hackathon 2026 page](https://www.fortyguard.com/hackathon26).
Repository and runnable-demo information are complete. The hosted demo and
video URLs must be added after those artifacts are published.

## Submission links

| Deliverable | Value |
| --- | --- |
| Project | HeatOps |
| Code repository | https://github.com/MichelleHan7/HeatOps |
| Working prototype | `streamlit run app.py` after installing `.[demo]` |
| Hosted demo | Not published yet |
| 2–5 minute video | Not published yet; use [the recording script](video-script.md) |
| API documentation | [FortyGuard API integration](api-integration.md) |

## Tagline

Heat-aware field operations planning powered by FortyGuard hyperlocal
temperature intelligence.

## Short summary

HeatOps converts FortyGuard's location- and time-specific temperature data into
an explainable daily schedule for field teams. A deterministic constraint
solver keeps job windows, crew shifts, skills, and non-overlap as hard rules,
then lets an operator choose the balance between operational Heat Load and
priority-weighted delay. The demo compares every result against a fair,
temperature-unaware baseline and explains exactly which jobs moved and why.

## Problem

Field dispatch decisions are usually driven by deadlines, staffing, and route
feasibility. Heat can vary across nearby work sites and throughout a shift, but
that hyperlocal signal is difficult to translate into a concrete plan. A map
alone tells an operator where heat exists; it does not answer which task should
move, to what time, and at what operational cost.

## Solution

HeatOps closes that last-mile decision gap:

1. It requests FortyGuard heatmaps for the field-work AOI and time horizon.
2. It matches each job coordinate to the returned temperature tiles.
3. It validates and caches a complete job-by-time temperature matrix.
4. It generates feasible schedules with OR-Tools CP-SAT.
5. It compares Operations-first, Balanced, Heat-first, and custom policies.
6. It renders before/after timelines, a map, temperature curves, trade-offs,
   headline metrics, and job-level explanations.

The live path has bounded retries, polling, validation, and cache fallback. The
default demo uses a traceable FortyGuard snapshot so judging remains
reproducible without an API key or network dependency.

## Demonstrated impact

For the bundled Phoenix utility scenario, the Heat-first policy changes the
schedule as follows:

| Metric | Operations-first baseline | HeatOps Heat-first |
| --- | ---: | ---: |
| Operational Heat Load Score | 40.38 | 39.18 |
| Heat Load reduction | — | 2.97% |
| Jobs moved | — | 3 of 5 |

These are deterministic scenario results checked by the automated test suite.
They are evidence for this prototype, not a claim that every schedule or city
will achieve the same reduction. Heat Load is a transparent operational score,
not a medical risk assessment.

## Why it is innovative

- It moves beyond heat visualization to a recommended, constraint-valid action.
- Policy presets and a custom slider expose the heat-versus-delay decision
  instead of burying it in an opaque score.
- The baseline is scientifically fair: both schedules share the same solver and
  constraints, and only the heat objective changes.
- Explanations connect each moved job to its time, temperature, and Heat Load
  delta.
- Source banners, checksums, validation, and fallback make the demo's data
  provenance visible.

## Technical quality evidence

- Layered Python package with domain, integration, optimization, evaluation,
  presentation, CLI, and Streamlit boundaries.
- Deterministic CP-SAT optimization with explicit constraints and stable
  tie-breaking.
- Typed dataclasses and centralized scheduler configuration.
- Resilient asynchronous FortyGuard client and complete-matrix validation.
- Unit, integration, scenario, CLI, presentation, and Streamlit smoke tests.
- GitHub Actions gates on Python 3.11 and 3.12 for lint, format, tests, compile,
  and installed-CLI smoke behavior.

## FortyGuard API usage

HeatOps sends a padded GeoJSON AOI, date, time, and granularity to
`POST /v1/heatmap`, obtains an activity ID, and polls
`GET /v1/status/{activity_id}`. On completion it reads `map_data.features`,
spatially maps temperatures to jobs, and validates every requested job/time
value before scheduling. Full request, response, retry, cache, and provenance
details are in [FortyGuard API integration](api-integration.md).

## Scope and responsible claims

The submission is a single-crew daily-planning prototype. It does not implement
multi-crew routing, real-time travel, medical guidance, or production identity
and persistence. Those omissions keep the hackathon story focused and the demo
fully testable.

## Final submission checklist

- [x] Working demo/prototype is runnable from the repository.
- [x] Public code repository URL is recorded.
- [x] Written project summary, solution, and impact are ready.
- [x] FortyGuard API usage is documented.
- [x] A 2–5 minute recording script and demo runbook are ready.
- [ ] Hosted demo URL is added after deployment.
- [ ] Final video is recorded, uploaded, and linked.
- [ ] Submission form fields and team details are reviewed before sending.

The machine-readable status and evidence values live in
[`submission/heatops-submission.json`](../submission/heatops-submission.json).
