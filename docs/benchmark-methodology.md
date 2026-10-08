# Benchmark methodology (registered before final evaluation)

The immutable input manifest is `benchmarks/final.json`. Main configurations:
10 jobs / 2 crews × five temperature families × 30 seeds (10000–10029).
Scaling configurations: 5/1, 25/5, 50/5, 100/10 (jobs/crews), hot family,
three seeds (20000–20002). Travel: 5 jobs / 2 crews, three seeds (30000–30002).
All four policies run on each instance with identical constraints. Total planned:
165 instances and 660 policy attempts. No unsuccessful attempt is dropped.
Development seeds are below 10000. Main configurations use a five-second per-policy limit to bound the 600-run suite;
scaling and travel use the initial thirty-second limit. The solve limit excludes
model construction; reported end-to-end runtime includes both. Single search
thread, seed 0. Constructive feasibility hints are supplied to scheduling-only baselines; baseline
incumbent hints are supplied to all alternative policies. A baseline
incumbent can be unproven; this is recorded and delay budgets then reference that
incumbent rather than a proven operational optimum.

Generator v1 uses 12-hour shifts, 15/30/45/60 minute jobs, priorities 1–3,
heterogeneous two-skill crews, seeded task windows containing a feasibility
witness, and sinusoidal synthetic temperature curves. The witness guarantees
scheduling-only feasibility, not feasibility with travel. These are software
experiments, not calibrated workforce or measured weather datasets. Workloads
with insufficient crew capacity are rejected rather than silently modified.

Heat Load is the legacy integral approximation of temperature above 32°C,
weighted by duration and physical intensity. It is not a medical score.
Delay is minutes from earliest start, weighted by priority. Delay-budget policy
allows 60 extra **priority-weighted crew-task minutes** over the baseline.
Normalization uses min/max over all eligible job/worker/start candidates. The
operations baseline minimizes exact integer weighted delay. Other policies use
rounded 1e-4 normalized costs and a strictly subordinate tie preference. Bounds
and relative gaps concern that exact integer objective, not raw Heat Load.

Reduction is undefined (null) for zero baseline heat or unsuccessful paired
runs. Summary denominators explicitly record these cases. Reduction summaries
condition on successful, independently valid paired schedules; solve rates use
all planned attempts. A seeded 2000-resample percentile bootstrap estimates a
95% CI of the paired mean; it is descriptive across generated instances, not
clinical evidence or a population guarantee. Small scaling samples have weak
statistical precision. Reports include minimum/maximum, sample SD, median and
p95 runtime, exact status counts, failures and baseline optimality.

Service time / available shift minutes defines utilization; travel is excluded
from that numerator and reported separately. Travel uses ceil(Haversine × 1.3 /
30 km/h × 60), from depot to first task and between consecutive tasks. No return
to depot is required. User-supplied directed travel times override individual
legs; distances remain geographic estimates. Worker unavailability blocks work,
not travel. Never interpret route lines as road navigation.

Reproduction: `python scripts/run_benchmarks.py --manifest benchmarks/final.json`.
CSV, detailed JSONL and summary JSON retain all attempts. Checkpoint resume checks
the manifest hash and implementation source hash to prevent mixing experiments.
