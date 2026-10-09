"""Checkpointed, paired evaluation with explicit failure rows."""

import csv
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from heatops.benchmark.scenario_generator import generate_scenario
from heatops.benchmark.scenario_validation import validate_scenario
from heatops.domain.config import SchedulerConfig
from heatops.evaluation.fleet import compare_fleet
from heatops.optimization.multi_crew import POLICIES
from heatops.optimization.travel import TravelConfig


def source_hash():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_benchmarks(manifest, output_dir="reports", *, resume=False):
    manifest = (
        json.loads(Path(manifest).read_text())
        if not isinstance(manifest, dict)
        else manifest
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    identity = {
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "source_sha256": source_hash(),
    }
    metadata = {
        **identity,
        "manifest": manifest,
        "started_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "solver_threads": 1,
        "execution_workers": manifest.get("execution_workers", 1),
        "cgroup_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip()
        if Path("/sys/fs/cgroup/cpu.max").exists()
        else None,
        "packages": {
            p: importlib.metadata.version(p) for p in ("ortools", "numpy", "heatops")
        },
    }
    try:
        metadata["cpu_model"] = next(
            x.split(":", 1)[1].strip()
            for x in Path("/proc/cpuinfo").read_text().splitlines()
            if x.startswith("model name")
        )
    except (OSError, StopIteration):
        metadata["cpu_model"] = platform.processor()
    meta_path, log_path = (
        out / "benchmark_environment.json",
        out / "benchmark_details.jsonl",
    )
    completed, details = set(), []
    if resume and meta_path.exists():
        previous = json.loads(meta_path.read_text())
        if any(previous[k] != identity[k] for k in identity):
            raise ValueError("Cannot resume after changing manifest or source code")
        for line in log_path.read_text().splitlines() if log_path.exists() else []:
            entry = json.loads(line)
            details.append(entry)
            completed.add(entry["instance_id"])
    else:
        meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
        log_path.write_text("")
    tasks = []
    for spec in manifest["configurations"]:
        for family in spec["families"]:
            for seed in range(
                spec["seed_start"], spec["seed_start"] + spec["instances"]
            ):
                key = f"{spec['label']}-{spec['jobs']}-{spec['crews']}-{family}-{seed}"
                if key not in completed:
                    tasks.append((spec, family, seed, manifest))
    workers = manifest.get("execution_workers", 1)
    if not isinstance(workers, int) or not 1 <= workers <= 8:
        raise ValueError("execution_workers must be between 1 and 8")
    if workers == 1:
        entries = map(_run_instance, tasks)
        executor = None
    else:
        executor = ProcessPoolExecutor(max_workers=workers)
        entries = executor.map(_run_instance, tasks)
    try:
        for entry in entries:
            with log_path.open("a") as f:
                f.write(json.dumps(entry, allow_nan=False) + "\n")
            details.append(entry)
            print(
                entry["instance_id"],
                {p: x["result"]["status"] for p, x in entry["policies"].items()},
                entry["error"] or "",
                flush=True,
            )
    finally:
        if executor is not None:
            executor.shutdown(cancel_futures=True)
    with gzip.open(out / "benchmark_details.jsonl.gz", "wb") as f:
        f.write(log_path.read_bytes())
    rows = flatten(details)
    with (out / "benchmark_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    from heatops.benchmark.reporting import write_reports

    write_reports(rows, out)
    return rows


def _run_instance(task):
    spec, family, seed, manifest = task
    key = f"{spec['label']}-{spec['jobs']}-{spec['crews']}-{family}-{seed}"
    try:
        scenario = generate_scenario(spec["jobs"], spec["crews"], seed, family)
        validate_scenario(scenario)
        config = SchedulerConfig(
            solver_time_limit_seconds=spec.get(
                "solver_time_limit_seconds", manifest["solver_time_limit_seconds"]
            )
        )
        result = compare_fleet(
            scenario.jobs,
            scenario.workers,
            scenario.temperature_matrix,
            config=config,
            travel=TravelConfig(enabled=spec["travel"]),
            initial_schedule=scenario.witness if not spec["travel"] else (),
            additional_delay_minutes=manifest["additional_weighted_delay_minutes"],
        )
        error = None
    except (ValueError, TypeError, RuntimeError, KeyError, OSError) as exc:
        result, error = {}, f"{type(exc).__name__}: {exc}"
    return {
        "instance_id": key,
        "label": spec["label"],
        "jobs": spec["jobs"],
        "crews": spec["crews"],
        "family": family,
        "seed": seed,
        "travel": spec["travel"],
        "source": "synthetic",
        "policies": result,
        "error": error,
    }


def flatten(details):
    rows = []
    for entry in details:
        baseline = entry["policies"].get("operations_first", {}).get("result", {})
        for policy in POLICIES:
            p = entry["policies"].get(policy, {})
            r, m = p.get("result", {}), p.get("metrics", {})
            row = {
                k: entry[k]
                for k in (
                    "instance_id",
                    "label",
                    "jobs",
                    "crews",
                    "family",
                    "seed",
                    "travel",
                    "source",
                )
            }
            row.update(
                policy=policy,
                status=r.get("status", "ERROR" if entry["error"] else "NOT_RUN"),
                error=entry["error"]
                or (
                    r.get("message")
                    if r.get("status") not in ("OPTIMAL", "FEASIBLE")
                    else ""
                ),
                baseline_status=baseline.get("status"),
                baseline_heat=baseline.get("total_heat_load"),
                heat=r.get("total_heat_load"),
                reduction_percent=p.get("heat_reduction_percent"),
                weighted_delay_minutes=r.get("weighted_delay_minutes"),
                baseline_delay_minutes=baseline.get("weighted_delay_minutes"),
                raw_delay_hours=r.get("total_delay_hours"),
                runtime_seconds=r.get("runtime_seconds"),
                build_seconds=r.get("build_seconds"),
                solve_seconds=r.get("solve_seconds"),
                objective=r.get("objective_value"),
                bound=r.get("objective_bound"),
                gap=r.get("relative_gap"),
                candidates=r.get("candidate_count"),
                variables=r.get("variable_count"),
                constraints=r.get("constraint_count"),
                scheduled_jobs=m.get("scheduled_jobs", 0),
                deadline_satisfaction=m.get("deadline_satisfaction"),
                constraint_violations=m.get("constraint_violations"),
                travel_km=m.get("estimated_travel_km"),
                travel_minutes=m.get("estimated_travel_minutes"),
                utilization_mean=sum(m.get("crew_utilization", {}).values())
                / entry["crews"]
                if m
                else None,
            )
            if row["constraint_violations"]:
                row["reduction_percent"] = None
            rows.append(row)
    return rows
