import argparse
import json
import sys
from pathlib import Path

from heatops.domain.loaders import load_jobs
from heatops.domain.time_utils import minutes_to_time, time_to_minutes
from heatops.integrations.temperature_service import (
    TemperatureServiceError,
    fetch_temperature_data,
)

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and cache a validated FortyGuard temperature matrix."
    )
    parser.add_argument(
        "--jobs",
        type=Path,
        default=ROOT / "data" / "sample_jobs.json",
    )
    parser.add_argument("--date", default="2026-08-24")
    parser.add_argument("--start-time", default="08:00")
    parser.add_argument("--end-time", default="19:00")
    parser.add_argument("--granularity", type=int, default=100)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "data" / "cache",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "temperature_matrix.json",
    )
    parser.add_argument("--no-cache-fallback", action="store_true")
    return parser


def _hourly_slots(start_time: str, end_time: str) -> list[str]:
    start = time_to_minutes(start_time)
    end = time_to_minutes(end_time)

    if start % 60 or end % 60:
        raise ValueError("start-time and end-time must be on the hour.")

    if start > end:
        raise ValueError("start-time must not be after end-time.")

    return [minutes_to_time(minute) for minute in range(start, end + 1, 60)]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        jobs = load_jobs(args.jobs)
        time_slots = _hourly_slots(args.start_time, args.end_time)
        result = fetch_temperature_data(
            jobs,
            args.date,
            time_slots,
            cache_dir=args.cache_dir,
            granularity=args.granularity,
            allow_cache_fallback=not args.no_cache_fallback,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.matrix, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"Saved {result.metadata.source} temperature matrix to {args.output} "
            f"(data date: {result.metadata.data_date})."
        )
        return 0
    except (KeyError, OSError, TemperatureServiceError, TypeError, ValueError) as error:
        print(f"Temperature fetch failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
