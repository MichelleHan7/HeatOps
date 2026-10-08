import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from heatops.domain.loaders import load_jobs, load_temperature_matrix, load_workers
from heatops.domain.models import OptimizationWeights, Worker
from heatops.domain.time_utils import minutes_to_time
from heatops.evaluation.models import ScheduleComparison
from heatops.evaluation.service import compare_schedules
from heatops.optimization.presets import PRESETS, get_preset, weights_from_heat_priority

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCENARIO = ROOT / "data" / "scenarios" / "phoenix-demo"
INSTALLED_SCENARIO = (
    Path(sys.prefix) / "share" / "heatops" / "data" / "scenarios" / "phoenix-demo"
)
DEFAULT_SCENARIO = SOURCE_SCENARIO if SOURCE_SCENARIO.is_dir() else INSTALLED_SCENARIO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare a HeatOps schedule with the operations-first baseline."
    )
    parser.add_argument(
        "--jobs",
        type=Path,
        default=DEFAULT_SCENARIO / "jobs.json",
        help="Path to a jobs JSON file.",
    )
    parser.add_argument(
        "--workers",
        type=Path,
        default=DEFAULT_SCENARIO / "workers.json",
        help="Path to a workers JSON file.",
    )
    parser.add_argument(
        "--temperatures",
        type=Path,
        default=DEFAULT_SCENARIO / "temperature_matrix.json",
        help="Path to a temperature matrix JSON file.",
    )
    parser.add_argument(
        "--worker-id",
        default="CREW-001",
        help="Worker or crew id to schedule.",
    )
    parser.add_argument(
        "--mode",
        choices=tuple(PRESETS),
        default="balanced",
        help="Optimization preset (ignored when --heat-priority is supplied).",
    )
    parser.add_argument(
        "--heat-priority",
        type=float,
        help="Custom heat priority from 0 to 100; delay receives the remainder.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--all-workers", action="store_true", help="Use the v2 fleet engine"
    )
    parser.add_argument("--scenario", type=Path, help="V2 scenario JSON bundle")
    parser.add_argument(
        "--policy",
        choices=("operations_first", "heat_first", "balanced", "delay_budget"),
    )
    parser.add_argument(
        "--travel", action="store_true", help="Enforce estimated travel (v2)"
    )
    parser.add_argument("--time-limit", type=float, default=10)
    parser.add_argument(
        "--delay-budget", type=int, default=60, help="Extra priority-weighted minutes"
    )
    return parser


def _select_worker(workers: list[Worker], worker_id: str) -> Worker:
    for worker in workers:
        if worker.id == worker_id:
            return worker

    available = ", ".join(worker.id for worker in workers) or "none"
    raise ValueError(f"Unknown worker {worker_id!r}. Available workers: {available}.")


def _render_text(
    comparison: ScheduleComparison,
    worker: Worker,
    mode: str,
    job_names: dict[str, str],
) -> str:
    lines = [
        "HEATOPS EVALUATION",
        "=" * 60,
        f"Crew                : {worker.name} ({worker.id})",
        f"Optimization mode   : {mode}",
        f"Baseline Heat Load  : {comparison.baseline_metrics.total_heat_load:.2f}",
        f"HeatOps Heat Load   : {comparison.optimized_metrics.total_heat_load:.2f}",
        f"Heat Load Reduction : {comparison.heat_load_reduction_percent:.1f}%",
        f"Jobs moved          : {comparison.moved_jobs}",
        "=" * 60,
    ]

    for heading, result in (
        ("BASELINE SCHEDULE", comparison.baseline_result),
        ("HEATOPS SCHEDULE", comparison.optimized_result),
    ):
        lines.extend(("", heading))

        for item in result.assignments:
            lines.append(
                f"{minutes_to_time(item.start_minute)}-"
                f"{minutes_to_time(item.end_minute)} | "
                f"{item.job_id} | "
                f"{job_names[item.job_id]:<25} | "
                f"{item.temperature_c:.2f} C | "
                f"Heat Load {item.heat_load:.2f}"
            )

    return "\n".join(lines)


def _render_json(
    comparison: ScheduleComparison,
    worker: Worker,
    mode: str,
    weights: OptimizationWeights,
) -> str:
    heat_weight, delay_weight = weights.normalized()
    payload = {
        "mode": mode,
        "weights": {"heat": heat_weight, "delay": delay_weight},
        "worker": asdict(worker),
        "comparison": asdict(comparison),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.all_workers or args.scenario or args.policy or args.travel:
            return _fleet_main(args)
        jobs = load_jobs(args.jobs)
        workers = load_workers(args.workers)
        temperature_matrix = load_temperature_matrix(args.temperatures)
        worker = _select_worker(workers, args.worker_id)

        if args.heat_priority is None:
            weights = get_preset(args.mode)
            mode = args.mode
        else:
            weights = weights_from_heat_priority(args.heat_priority)
            mode = f"custom ({args.heat_priority:g}% heat priority)"

        comparison = compare_schedules(
            jobs,
            temperature_matrix,
            worker=worker,
            weights=weights,
        )

        if args.format == "json":
            output = _render_json(comparison, worker, mode, weights)
        else:
            output = _render_text(
                comparison,
                worker,
                mode,
                {job.id: job.name for job in jobs},
            )

        print(output)
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"HeatOps evaluation failed: {error}", file=sys.stderr)
        return 2


def _fleet_main(args):
    from heatops.benchmark.scenario_generator import scenario_from_dict
    from heatops.domain.config import SchedulerConfig
    from heatops.evaluation.fleet import compare_fleet
    from heatops.optimization.travel import TravelConfig

    if args.scenario:
        scenario = scenario_from_dict(json.loads(args.scenario.read_text()))
        jobs, workers, matrix = (
            scenario.jobs,
            scenario.workers,
            scenario.temperature_matrix,
        )
        metadata = scenario.metadata
        hints = scenario.witness if not args.travel else ()
    else:
        jobs, workers = load_jobs(args.jobs), load_workers(args.workers)
        matrix, hints = load_temperature_matrix(args.temperatures), ()
        metadata = {"source": "file", "path": str(args.temperatures)}
    policy = args.policy or args.mode
    comparison = compare_fleet(
        jobs,
        workers,
        matrix,
        policies=(policy,),
        config=SchedulerConfig(solver_time_limit_seconds=args.time_limit),
        travel=TravelConfig(enabled=args.travel),
        additional_delay_minutes=args.delay_budget,
        initial_schedule=hints,
    )
    payload = {"source": metadata, "comparison": comparison}
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        for name, entry in comparison.items():
            result = entry["result"]
            print(
                f"{name}: {result['status']} | jobs={len(result['assignments'])} | Heat Load={result['total_heat_load']} | weighted delay={result['weighted_delay_minutes']} min"
            )
            for row in result["assignments"]:
                print(
                    f"  {row['worker_id']} {row['job_id']} {minutes_to_time(row['start_minute'])}-{minutes_to_time(row['end_minute'])}"
                )
    return (
        0
        if all(
            p["result"]["status"] in ("OPTIMAL", "FEASIBLE")
            and not p["metrics"]["constraint_violations"]
            for p in comparison.values()
        )
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
