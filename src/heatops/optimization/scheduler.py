import json
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[3]

JOBS_PATH = ROOT / "data" / "sample_jobs.json"
TEMPERATURE_PATH = ROOT / "data" / "temperature_matrix.json"

SLOT_MINUTES = 15
HEAT_THRESHOLD = 32.0
DELAY_PENALTY_PER_HOUR = 0.15


def time_to_minutes(time_string):
    hour, minute = map(int, time_string.split(":"))
    return hour * 60 + minute


def minutes_to_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


with open(JOBS_PATH, "r") as f:
    jobs = json.load(f)

with open(TEMPERATURE_PATH, "r") as f:
    temperature_matrix = json.load(f)


def get_temperature(job_id, minute):
    """
    Linearly interpolate temperature between hourly FortyGuard observations.
    """

    hour = minute // 60
    minute_in_hour = minute % 60

    current_hour = f"{hour:02d}:00"

    temperatures = temperature_matrix[job_id]["temperatures"]

    if minute_in_hour == 0:
        return temperatures[current_hour]

    next_hour = f"{hour + 1:02d}:00"

    t1 = temperatures[current_hour]
    t2 = temperatures[next_hour]

    fraction = minute_in_hour / 60

    return t1 + fraction * (t2 - t1)


def calculate_heat_load(job, start_minute):
    """
    Project-specific Heat Load Score.

    For each 15-minute period:
        heat load = degrees above threshold × duration

    This is NOT a medical risk score.
    It is an operational optimization metric.
    """

    duration = job["duration_minutes"]

    total_load = 0.0
    temperatures = []

    for offset in range(0, duration, SLOT_MINUTES):
        minute = start_minute + offset

        temperature = get_temperature(
            job["id"],
            minute
        )

        temperatures.append(temperature)

        heat_above_threshold = max(
            temperature - HEAT_THRESHOLD,
            0
        )

        total_load += (
            heat_above_threshold
            * SLOT_MINUTES / 60
        )

    average_temperature = (
        sum(temperatures) / len(temperatures)
    )

    return total_load, average_temperature


def optimize_schedule():
    model = cp_model.CpModel()

    variables = {}
    costs = {}

    # --------------------------------
    # Create possible start decisions
    # --------------------------------

    for job in jobs:
        earliest = time_to_minutes(
            job["earliest_start"]
        )

        deadline = time_to_minutes(
            job["deadline"]
        )

        latest_start = (
            deadline - job["duration_minutes"]
        )

        possible_starts = range(
            earliest,
            latest_start + 1,
            SLOT_MINUTES
        )

        job_variables = []

        for start in possible_starts:
            variable = model.NewBoolVar(
                f'{job["id"]}_{start}'
            )

            variables[(job["id"], start)] = variable
            job_variables.append(variable)

            heat_load, _ = calculate_heat_load(
                job,
                start
            )

            earliest_start = time_to_minutes(
                job["earliest_start"]
            )

            delay_hours = (
                start - earliest_start
            ) / 60

            operational_cost = (
                heat_load
                + DELAY_PENALTY_PER_HOUR * delay_hours
            )

            costs[(job["id"], start)] = operational_cost

        # Every job must be scheduled exactly once
        model.Add(sum(job_variables) == 1)

    # --------------------------------
    # One crew: jobs cannot overlap
    # --------------------------------

    shift_start = 8 * 60
    shift_end = 19 * 60

    for minute in range(
        shift_start,
        shift_end,
        SLOT_MINUTES
    ):

        active_variables = []

        for job in jobs:
            duration = job["duration_minutes"]

            for (job_id, start), variable in variables.items():

                if job_id != job["id"]:
                    continue

                if start <= minute < start + duration:
                    active_variables.append(variable)

        if active_variables:
            model.Add(
                sum(active_variables) <= 1
            )

    # --------------------------------
    # Objective: minimize heat load
    # --------------------------------

    SCALE = 1000

    model.Minimize(
        sum(
            round(costs[key] * SCALE) * variable
            for key, variable in variables.items()
        )
    )

    # --------------------------------
    # Solve
    # --------------------------------

    solver = cp_model.CpSolver()

    status = solver.Solve(model)

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE
    ):
        raise RuntimeError(
            "No feasible schedule found."
        )

    schedule = []

    for job in jobs:

        for (job_id, start), variable in variables.items():

            if (
                job_id == job["id"]
                and solver.Value(variable)
            ):

                heat_load, average_temperature = (
                    calculate_heat_load(
                        job,
                        start
                    )
                )

                schedule.append({
                    "id": job["id"],
                    "name": job["name"],
                    "start": minutes_to_time(start),
                    "end": minutes_to_time(
                        start + job["duration_minutes"]
                    ),
                    "average_temperature": average_temperature,
                    "heat_load": heat_load
                })

    schedule.sort(
        key=lambda x: x["start"]
    )

    return schedule


if __name__ == "__main__":

    schedule = optimize_schedule()

    print("\nHEAT-AWARE OPTIMIZED SCHEDULE")
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