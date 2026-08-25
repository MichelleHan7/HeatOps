import json
from pathlib import Path

from scheduler import (
    calculate_heat_load,
    time_to_minutes,
    minutes_to_time
)


ROOT = Path(__file__).resolve().parent.parent

JOBS_PATH = ROOT / "data" / "sample_jobs.json"


with open(JOBS_PATH, "r") as f:
    jobs = json.load(f)


def build_baseline_schedule():
    """
    Temperature-unaware Earliest Deadline First (EDF).

    At each point in time:
    1. Find all jobs that are currently available.
    2. Among them, choose the job with the earliest deadline.
    3. If no job is available, advance to the next release time.

    The scheduler does NOT use temperature information.
    """

    unscheduled = jobs.copy()

    current_time = min(
        time_to_minutes(job["earliest_start"])
        for job in unscheduled
    )

    schedule = []

    while unscheduled:

        available_jobs = [
            job
            for job in unscheduled
            if time_to_minutes(job["earliest_start"]) <= current_time
        ]

        if not available_jobs:
            current_time = min(
                time_to_minutes(job["earliest_start"])
                for job in unscheduled
            )
            continue

        job = min(
            available_jobs,
            key=lambda job: (
                time_to_minutes(job["deadline"]),
                -job["priority"]
            )
        )

        start = current_time
        end = start + job["duration_minutes"]

        deadline = time_to_minutes(job["deadline"])

        if end > deadline:
            raise RuntimeError(
                f'Baseline cannot schedule {job["id"]} '
                f'before its deadline.'
            )

        heat_load, average_temperature = calculate_heat_load(
            job,
            start
        )

        schedule.append({
            "id": job["id"],
            "name": job["name"],
            "start": minutes_to_time(start),
            "end": minutes_to_time(end),
            "average_temperature": average_temperature,
            "heat_load": heat_load
        })

        current_time = end
        unscheduled.remove(job)

    return schedule

if __name__ == "__main__":

    schedule = build_baseline_schedule()

    print("\nTEMPERATURE-UNAWARE BASELINE SCHEDULE")
    print("=" * 80)

    total_heat_load = 0

    for item in schedule:

        total_heat_load += item["heat_load"]

        print(
            f'{item["start"]}-{item["end"]} | '
            f'{item["id"]} | '
            f'{item["name"]:<25} | '
            f'{item["average_temperature"]:.2f}°C | '
            f'Heat Load: {item["heat_load"]:.2f}'
        )

    print("=" * 80)

    print(
        f"Total Heat Load Score: "
        f"{total_heat_load:.2f}"
    )