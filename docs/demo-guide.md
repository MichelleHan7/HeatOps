# HeatOps demo guide

This runbook is designed for a reliable live judging demo using the repository
snapshot. It also documents the optional live FortyGuard path and recovery
steps.

## Before presenting

```bash
python -m pip install -e ".[demo,dev]"
pytest -q
streamlit run app.py
```

Use a browser width of at least 1280 px, collapse unrelated tabs, and open the
app before screen sharing. Keep **Refresh from FortyGuard API** off for the main
path: the bundled snapshot is traceable, deterministic, and does not depend on
network latency or quota.

Expected opening state:

- Phoenix Utility Field Operations scenario.
- Crew Alpha and five jobs.
- Balanced preset selected.
- Bundled FortyGuard snapshot status visible above the metrics.
- Heat priority slider disabled until Custom is selected.

## Recommended 3-minute click path

### 1. Frame the problem — 20 seconds

Field dispatch usually optimizes operational timing without seeing how heat
changes block by block and hour by hour. HeatOps adds that missing decision
factor while keeping deadlines, skills, shifts, and non-overlap as hard
constraints.

Point to the visible data-source status. State that temperatures come from a
traceable FortyGuard snapshot; jobs and policy weights are explicit demo
assumptions.

### 2. Establish the baseline — 30 seconds

Select **Operations-first**, then click **Optimize schedule**. Point out:

- it is the earliest feasible, temperature-unaware schedule;
- the baseline and optimized timelines match in this mode;
- the same constraints and solver are used in every mode.

### 3. Show the impact — 60 seconds

Select **Heat-first** and optimize. Lead with the top cards:

- Heat Load changes from **40.38 to 39.18**;
- reduction is **2.97%**;
- **3 of 5 jobs** move.

Then compare the side-by-side timelines. Use the explanations section to show
that each change includes old/new time, temperature change, and Heat Load
change. If delay or idle time rises, call out the warning rather than hiding the
trade-off.

### 4. Prove FortyGuard matters — 35 seconds

Use the temperature curves and location map. Explain that the optimizer sees a
job-by-time matrix, not one citywide forecast. Each field coordinate is matched
to a FortyGuard heatmap tile before scheduling.

### 5. Make the policy interactive — 25 seconds

Select **Custom**. Move the Heat priority slider, for example from 25% to 75%,
and optimize after each choice. Point to the trade-off chart: HeatOps is a
decision-support surface, not a hidden one-size-fits-all policy.

### 6. Close — 10 seconds

“HeatOps turns hyperlocal heat intelligence into an explainable daily action:
which job should move, when, and what operational trade-off that creates.”

## Optional live API moment

Only use this after the deterministic story is complete.

1. Configure `FORTYGUARD_API_KEY` in `.streamlit/secrets.toml` or the
   environment.
2. Enable **Refresh from FortyGuard API**.
3. Click **Optimize schedule**.
4. Point to the data-source banner, which says whether the result is live,
   cached, or the bundled snapshot.

The request may take time because HeatOps creates and polls an asynchronous
heatmap for every time slot. A network or API failure is non-fatal: the app
shows the fallback and continues with validated data.

## Failure recovery

| Symptom | Recovery |
| --- | --- |
| App does not start | Confirm Python 3.11/3.12 and run `python -m pip install -e ".[demo,dev]"` |
| Missing API key | Turn live refresh off, or copy `.streamlit/secrets.toml.example` and add the key |
| Live refresh falls back | Continue the demo and explicitly point out the resilience behavior |
| Scenario load error | Restore all files under `data/scenarios/phoenix-demo/` and run `pytest -q` |
| Chart layout is cramped | Widen the browser and keep Streamlit in wide mode |
| Unexpected evidence numbers | Run `pytest tests/test_submission_artifacts.py -q`; do not quote stale numbers |

## Recording checklist

- Record at 1080p if possible; verify labels are readable.
- Do not expose `.env`, Streamlit secrets, browser developer tools, or API keys.
- Keep the final video between 2 and 5 minutes.
- Show the repository name and FortyGuard data-source banner.
- Show at least one baseline/optimized timeline comparison.
- State the 2.97% result as scenario evidence, not a universal guarantee.
- Include one job-level explanation and the trade-off chart.
- End with the repository URL and a single-sentence impact statement.

The timed narration is in [Video script](video-script.md).
