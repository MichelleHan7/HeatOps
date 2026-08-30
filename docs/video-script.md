# HeatOps 2–5 minute video script

Target length: approximately 3 minutes 20 seconds. The speaker notes are
written for a screen recording of `streamlit run app.py`.

## 0:00–0:20 — Hook

**On screen:** HeatOps title and Phoenix scenario.

**Narration:**

“Heat conditions can change by location and hour, but field schedules are still
usually planned around deadlines alone. HeatOps turns FortyGuard's hyperlocal
temperature intelligence into an explainable daily action: which job should
move, when, and what trade-off that creates.”

## 0:20–0:50 — Inputs and trust

**On screen:** Data-source banner, controls, and temperature curves.

**Narration:**

“This demo schedules five Phoenix utility jobs for Crew Alpha. The temperature
matrix comes from a traceable FortyGuard snapshot covering each job location
from 8 a.m. through 7 p.m. Jobs, priorities, physical intensity, and crew skills
are explicit demo assumptions. The banner always shows whether data is live,
cached, or the bundled snapshot.”

## 0:50–1:20 — Fair baseline

**Action:** Select **Operations-first** and click **Optimize schedule**.

**Narration:**

“First, here is the operations-first baseline. It uses the same OR-Tools solver,
time windows, shift, skills, and non-overlap constraints as HeatOps, but it does
not use temperature to choose the schedule. That makes the comparison fair: we
change one decision factor, not the rules.”

## 1:20–2:05 — Heat-aware result

**Action:** Select **Heat-first**, optimize, then point to metrics and timelines.

**Narration:**

“Now I switch to Heat-first. On this scenario, HeatOps reduces the operational
Heat Load Score from 40.38 to 39.18—a 2.97 percent reduction—by moving three of
five jobs. The timelines make the schedule change visible. Heat Load is a
transparent planning score based on temperature above a 32-degree threshold,
duration, and job intensity; it is not a medical risk assessment.”

## 2:05–2:35 — Explainability

**On screen:** Operational warning, map, and “Why the schedule changed.”

**Narration:**

“HeatOps does not hide the cost. It reports delay and idle-time trade-offs, and
every job gets a plain-language explanation with its old and new time,
temperature change, and Heat Load change. The location map and curves show why
one citywide forecast would not be enough.”

## 2:35–3:00 — Interactive policy

**Action:** Select **Custom**, set Heat priority to 75%, optimize, and point to
the trade-off chart.

**Narration:**

“Different operators have different constraints, so Custom mode exposes the
policy. Here, 75 percent of the objective favors Heat Load and the remainder
favors priority-weighted delay. The trade-off chart lets a dispatcher compare
policies instead of accepting a black-box answer.”

## 3:00–3:20 — Technical close

**On screen:** Return to the headline metrics, then show the repository README.

**Narration:**

“Under the hood, HeatOps has a resilient asynchronous FortyGuard integration,
complete data validation, cache and snapshot fallback, deterministic CP-SAT
optimization, and automated tests across Python 3.11 and 3.12. HeatOps turns a
heatmap into an operational decision that teams can inspect and act on.”

## Recording notes

- Keep the final export between 2 and 5 minutes.
- Pause briefly after each optimization so charts finish rendering.
- Do not show API keys, `.env`, Streamlit secrets, or browser developer tools.
- If a live API call is included, record it after the deterministic main take
  and keep the source banner visible.
- Replace the missing video URL in `docs/submission.md` and
  `submission/heatops-submission.json` only after upload succeeds.
