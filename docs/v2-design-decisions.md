# V2 design decisions

1. **Keep the historical solver.** `optimize_schedule` and its default CLI retain
   their original behavior and 2.971485% Phoenix result. `optimize_multi_crew`
   returns explicit status/diagnostic objects instead of raising for infeasibility.
   New fleet callers use `compare_fleet`, not single-crew idle-time metrics.
2. **All jobs required.** Binary x(job, worker, start) picks exactly one assignment.
   Ineligible skills, impossible windows and unavailable service intervals are
   eliminated before model construction. Global start expressions and one
   optional interval per job/eligible worker feed per-worker NoOverlap.
3. **Normalize once per common feasible candidate set.** Baseline minimizes exact
   integer priority-weighted delay. Heat/balanced costs use candidate-wide min-max
   normalization, rounded at 1e-4, plus bounded secondary start/worker preference.
   The secondary objective never overrides one integer primary unit. Equal-cost
   solutions can still exist; one thread, sorted IDs and fixed seed stabilize
   search. Wall-clock cutoffs do not guarantee identical FEASIBLE incumbents.
4. **Delay budget.** Heat minimization with an explicit upper bound in priority-
   weighted minutes. Compare against the same instance's baseline incumbent and
   disclose whether that baseline was proven optimal. Raw delay hours are separate.
5. **Travel is optional sequencing, not a route planner.** AddCircuit creates an
   empty route or depot/task/task route for each crew. Only successive tasks incur
   transition constraints, supporting directed nonmetric duration overrides.
   The final depot arc has zero cost/time: no required return journey. Geographic
   distance and time are estimates; 25-job default guard prevents routing blowup.
   Unavailability blocks service, not transit. Travel is enforced, not minimized.
6. **Independent checking.** Recompute required-job membership, durations, skills,
   shifts, windows, start grid, availability, chronological travel, heat and budget
   outside the solver. Benchmark invalid schedules receive no improvement metric.
7. **Data boundaries.** Bundled snapshot provenance remains unchanged. Seeded
   synthetic data includes an independently checked witness. Open-Meteo forecasts
   and historical reanalysis are model products; original timestamps, retrieval
   times and hourly values are retained. No implicit stale-date relabeling.
8. **Performance evidence.** Cache heat by job/start across workers; preserve a
   cache-off experiment switch. `scripts/profile_scheduler.py` pairs five development
   runs per setting and alternates order. It measures construction, not solver
   speedup. Final benchmark manifest is fixed before held-out evaluation.
9. **UI and deployment.** Legacy dashboard is the default. Fleet work runs only
   on a button, shows last-run provenance and exports the actual solver payload.
   No full benchmarks run during app loading. Default data is offline. This work does
   not operate deployment settings; deployment status after repository-side
   merges must be checked separately.
10. **Scope limits.** Deterministic same-day work only; no uncertainty model,
    breaks policy, overtime cost, precedence between jobs, road routing or
    risk/health inference. Acclimatization remains legacy metadata and does not
    rescale Heat Load. No FastAPI/database was added: optional phase 9 is deferred.
