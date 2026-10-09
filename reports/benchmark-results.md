# Executed benchmark results

All temperatures in this benchmark are synthetic. See benchmark-methodology.md.

| Configuration / policy | Solves / attempts | Mean reduction % | Median seconds | Statuses |
|---|---:|---:|---:|---|
| main/10/2/flat/balanced | 29/30 | 0.076 | 0.668 | {'OPTIMAL': 27, 'FEASIBLE': 2, 'UNKNOWN': 1} |
| main/10/2/flat/delay_budget | 27/30 | 0.167 | 1.027 | {'FEASIBLE': 4, 'OPTIMAL': 23, 'UNKNOWN': 2, 'NOT_RUN': 1} |
| main/10/2/flat/heat_first | 30/30 | 0.301 | 1.205 | {'OPTIMAL': 24, 'FEASIBLE': 6} |
| main/10/2/flat/operations_first | 29/30 | 0.000 | 0.606 | {'OPTIMAL': 29, 'UNKNOWN': 1} |
| main/10/2/hot/balanced | 30/30 | 2.102 | 0.591 | {'OPTIMAL': 26, 'FEASIBLE': 4} |
| main/10/2/hot/delay_budget | 30/30 | 2.558 | 0.872 | {'OPTIMAL': 25, 'FEASIBLE': 5} |
| main/10/2/hot/heat_first | 30/30 | 4.296 | 0.719 | {'OPTIMAL': 26, 'FEASIBLE': 4} |
| main/10/2/hot/operations_first | 30/30 | 0.000 | 0.398 | {'OPTIMAL': 30} |
| main/10/2/mild/balanced | 30/30 | N/A | 0.325 | {'OPTIMAL': 30} |
| main/10/2/mild/delay_budget | 30/30 | N/A | 0.551 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/mild/heat_first | 30/30 | N/A | 0.415 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/mild/operations_first | 30/30 | N/A | 0.310 | {'OPTIMAL': 30} |
| main/10/2/spatial/balanced | 30/30 | 4.113 | 0.462 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/spatial/delay_budget | 30/30 | 4.625 | 0.620 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/spatial/heat_first | 30/30 | 8.530 | 0.414 | {'OPTIMAL': 28, 'FEASIBLE': 2} |
| main/10/2/spatial/operations_first | 30/30 | 0.000 | 0.289 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/variable/balanced | 30/30 | 8.593 | 0.453 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/variable/delay_budget | 30/30 | 10.119 | 0.634 | {'OPTIMAL': 28, 'FEASIBLE': 2} |
| main/10/2/variable/heat_first | 30/30 | 21.334 | 0.333 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| main/10/2/variable/operations_first | 30/30 | 0.000 | 0.431 | {'OPTIMAL': 29, 'FEASIBLE': 1} |
| scaling/100/10/hot/balanced | 3/3 | 0.067 | 30.578 | {'FEASIBLE': 3} |
| scaling/100/10/hot/delay_budget | 2/3 | 0.168 | 30.164 | {'UNKNOWN': 1, 'FEASIBLE': 2} |
| scaling/100/10/hot/heat_first | 3/3 | 0.390 | 30.340 | {'FEASIBLE': 3} |
| scaling/100/10/hot/operations_first | 3/3 | 0.000 | 30.318 | {'FEASIBLE': 3} |
| scaling/25/5/hot/balanced | 3/3 | 0.977 | 30.092 | {'FEASIBLE': 3} |
| scaling/25/5/hot/delay_budget | 3/3 | 0.788 | 30.049 | {'FEASIBLE': 3} |
| scaling/25/5/hot/heat_first | 3/3 | 3.070 | 30.071 | {'FEASIBLE': 3} |
| scaling/25/5/hot/operations_first | 3/3 | 0.000 | 30.053 | {'FEASIBLE': 3} |
| scaling/5/1/hot/balanced | 3/3 | 10.611 | 0.029 | {'OPTIMAL': 3} |
| scaling/5/1/hot/delay_budget | 3/3 | 10.611 | 0.035 | {'OPTIMAL': 3} |
| scaling/5/1/hot/heat_first | 3/3 | 12.338 | 0.030 | {'OPTIMAL': 3} |
| scaling/5/1/hot/operations_first | 3/3 | 0.000 | 0.040 | {'OPTIMAL': 3} |
| scaling/50/5/hot/balanced | 3/3 | 0.314 | 30.158 | {'FEASIBLE': 3} |
| scaling/50/5/hot/delay_budget | 3/3 | 0.293 | 30.099 | {'FEASIBLE': 3} |
| scaling/50/5/hot/heat_first | 3/3 | 0.972 | 30.135 | {'FEASIBLE': 3} |
| scaling/50/5/hot/operations_first | 3/3 | 0.000 | 30.127 | {'FEASIBLE': 3} |
| travel/5/2/hot/balanced | 3/3 | 0.000 | 0.017 | {'OPTIMAL': 3} |
| travel/5/2/hot/delay_budget | 3/3 | 0.227 | 0.012 | {'OPTIMAL': 3} |
| travel/5/2/hot/heat_first | 3/3 | 2.327 | 0.018 | {'OPTIMAL': 3} |
| travel/5/2/hot/operations_first | 3/3 | 0.000 | 0.015 | {'OPTIMAL': 3} |

Reduction statistics condition on valid paired solves and positive baseline heat. All attempts and undefined counts are in benchmark_summary.json. Bounds/gaps use the integer solver objective. No feasible incumbent is labeled optimal.

Reproduce: `python scripts/run_benchmarks.py --manifest benchmarks/final.json`. Detailed assignments, metrics and statuses: `reports/benchmark_details.jsonl.gz`. Raw rows: `reports/benchmark_results.csv`. Environment, versions and source hash: `reports/benchmark_environment.json`.
