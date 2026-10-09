"""Aggregates retain failures and undefined reductions in denominators."""

import json
from collections import Counter, defaultdict

import numpy as np


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[
            f"{row['label']}/{row['jobs']}/{row['crews']}/{row['family']}/{row['policy']}"
        ].append(row)
    summary = {}
    rng = np.random.default_rng(20261008)
    for key, data in sorted(groups.items()):
        reductions = [
            r["reduction_percent"] for r in data if r["reduction_percent"] is not None
        ]
        times = [r["runtime_seconds"] for r in data if r["runtime_seconds"] is not None]
        valid = sum(
            r["status"] in ("OPTIMAL", "FEASIBLE") and r["constraint_violations"] == 0
            for r in data
        )
        ci = None
        if len(reductions) >= 2:
            boot = rng.choice(reductions, (2000, len(reductions)), replace=True).mean(
                axis=1
            )
            ci = np.percentile(boot, [2.5, 97.5]).tolist()
        summary[key] = {
            "attempts": len(data),
            "valid_schedules": valid,
            "successful_solve_rate": valid / len(data),
            "statuses": dict(Counter(r["status"] for r in data)),
            "reduction_n": len(reductions),
            "undefined_or_failed_pairs": len(data) - len(reductions),
            "mean_reduction_percent": float(np.mean(reductions))
            if reductions
            else None,
            "median_reduction_percent": float(np.median(reductions))
            if reductions
            else None,
            "sd_reduction_percent": float(np.std(reductions, ddof=1))
            if len(reductions) > 1
            else None,
            "mean_reduction_ci95": ci,
            "worst_reduction_percent": min(reductions) if reductions else None,
            "best_reduction_percent": max(reductions) if reductions else None,
            "median_runtime_seconds": float(np.median(times)) if times else None,
            "p95_runtime_seconds": float(np.percentile(times, 95)) if times else None,
            "baseline_optimal_n": sum(r["baseline_status"] == "OPTIMAL" for r in data),
        }
    return summary


def write_reports(rows, output):
    summary = summarize(rows)
    (output / "benchmark_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {"figure.dpi": 160, "axes.spines.top": False, "axes.spines.right": False}
    )
    policies = ("operations_first", "heat_first", "balanced", "delay_budget")
    fig, ax = plt.subplots(figsize=(9, 5))
    labels, values = [], []
    for p in policies[1:]:
        subset = [
            r["reduction_percent"]
            for r in rows
            if r["label"] == "main"
            and r["policy"] == p
            and r["reduction_percent"] is not None
        ]
        if subset:
            labels.append(f"{p}\nn={len(subset)}")
            values.append(subset)
    if values:
        ax.boxplot(values, tick_labels=labels, showmeans=True)
    ax.set(
        ylabel="Heat Load reduction (%)",
        title="Synthetic main workloads · valid nonzero-baseline pairs",
    )
    fig.tight_layout()
    fig.savefig(output / "heat_reduction.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    for p in policies:
        grouped = defaultdict(list)
        for r in rows:
            if (
                r["label"] == "scaling"
                and r["policy"] == p
                and r["runtime_seconds"] is not None
            ):
                grouped[r["jobs"]].append(r["runtime_seconds"])
        xs = sorted(grouped)
        ax.plot(xs, [np.median(grouped[x]) for x in xs], marker="o", label=p)
    ax.set(
        xlabel="Jobs (crew count varies; see manifest)",
        ylabel="Median end-to-end runtime (s)",
        title="Synthetic scaling attempts · failures included",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "scalability.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    for p in policies:
        subset = [
            r
            for r in rows
            if r["label"] == "main"
            and r["policy"] == p
            and r["reduction_percent"] is not None
        ]
        ax.scatter(
            [
                (r["weighted_delay_minutes"] - r["baseline_delay_minutes"]) / 60
                for r in subset
            ],
            [r["reduction_percent"] for r in subset],
            label=p,
            alpha=0.5,
            s=20,
        )
    ax.set(
        xlabel="Additional priority-weighted delay (hours)",
        ylabel="Heat Load reduction (%)",
        title="Synthetic policy trade-offs · not a proven Pareto frontier",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "tradeoff.png")
    plt.close(fig)
    lines = [
        "# Executed benchmark results",
        "",
        "All temperatures in this benchmark are synthetic. See benchmark-methodology.md.",
        "",
        "| Configuration / policy | Solves / attempts | Mean reduction % | Median seconds | Statuses |",
        "|---|---:|---:|---:|---|",
    ]
    for key, s in summary.items():
        mean = (
            "N/A"
            if s["mean_reduction_percent"] is None
            else f"{s['mean_reduction_percent']:.3f}"
        )
        runtime = (
            "N/A"
            if s["median_runtime_seconds"] is None
            else f"{s['median_runtime_seconds']:.3f}"
        )
        lines.append(
            f"| {key} | {s['valid_schedules']}/{s['attempts']} | {mean} | {runtime} | {s['statuses']} |"
        )
    lines.extend(
        [
            "",
            "Reduction statistics condition on valid paired solves and positive baseline heat. All attempts and undefined counts are in benchmark_summary.json. Bounds/gaps use the integer solver objective. No feasible incumbent is labeled optimal.",
            "",
            "Reproduce: `python scripts/run_benchmarks.py --manifest benchmarks/final.json`. Detailed assignments, metrics and statuses: `reports/benchmark_details.jsonl.gz`. Raw rows: `reports/benchmark_results.csv`. Environment, versions and source hash: `reports/benchmark_environment.json`.",
        ]
    )
    (output / "benchmark-results.md").write_text("\n".join(lines) + "\n")
