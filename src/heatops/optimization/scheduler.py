from ortools.sat.python import cp_model

from heatops.domain.models import (
    Job,
    OptimizationWeights,
    ScheduleAssignment,
    TemperatureMatrix,
)
from heatops.domain.time_utils import time_to_minutes

SLOT_MINUTES = 15
HEAT_THRESHOLD = 32.0


def get_temperature(
    job_id: str,
    minute: int,
    temperature_matrix: TemperatureMatrix,
) -> float:
    """
    Linearly interpolate temperature between hourly FortyGuard observations.
    """

    temperatures = temperature_matrix[job_id]["temperatures"]

    hour = minute // 60
    minute_in_hour = minute % 60

    current_hour = f"{hour:02d}:00"

    if current_hour not in temperatures:
        raise ValueError(
            f"Temperature data is missing for {job_id} at {current_hour}."
        )

    if minute_in_hour == 0:
        return temperatures[current_hour]

    next_hour = f"{hour + 1:02d}:00"

    if next_hour not in temperatures:
        raise ValueError(
            f"Temperature data is missing for {job_id} at {next_hour}."
        )

    t1 = temperatures[current_hour]
    t2 = temperatures[next_hour]

    fraction = minute_in_hour / 60

    return t1 + fraction * (t2 - t1)


def calculate_heat_load(
    job: Job,
    start_minute: int,
    temperature_matrix: TemperatureMatrix,
) -> tuple[float, float]:
    """
    Calculate the project-specific operational Heat Load Score.

    For each time period:

        heat load =
            degrees above threshold
            × exposure duration in hours

    This is NOT a medical risk score.
    It is an operational optimization metric.
    """

    total_load = 0.0
    temperatures = []

    remaining_minutes = job.duration_minutes
    offset = 0

    while remaining_minutes > 0:
        interval_minutes = min(
            SLOT_MINUTES,
            remaining_minutes,
        )

        minute = start_minute + offset

        temperature = get_temperature(
            job.id,
            minute,
            temperature_matrix,
        )

        temperatures.append(temperature)

        heat_above_threshold = max(
            temperature - HEAT_THRESHOLD,
            0.0,
        )

        total_load += (
            heat_above_threshold
            * interval_minutes
            / 60
        )

        offset += interval_minutes
        remaining_minutes -= interval_minutes

    average_temperature = (
        sum(temperatures) / len(temperatures)
    )

    return total_load, average_temperature


def optimize_schedule(
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
    weights: OptimizationWeights | None = None,
    worker_id: str = "CREW-001",
    shift_start: str = "08:00",
    shift_end: str = "19:00",
) -> list[ScheduleAssignment]:
    """
    Build a single-crew heat-aware schedule.

    Each job:
    - is scheduled exactly once,
    - stays inside its allowed time window,
    - stays inside the crew shift,
    - cannot overlap another job.

    The objective balances heat exposure and operational delay.
    """

    if not jobs:
        return []

    if weights is None:
        weights = OptimizationWeights()

    model = cp_model.CpModel()

    shift_start_minute = time_to_minutes(shift_start)
    shift_end_minute = time_to_minutes(shift_end)

    variables: dict[
        tuple[str, int],
        cp_model.IntVar,
    ] = {}

    costs: dict[
        tuple[str, int],
        float,
    ] = {}

    # --------------------------------
    # Create possible start decisions
    # --------------------------------

    for job in jobs:
        job_earliest = max(
            time_to_minutes(job.earliest_start),
            shift_start_minute,
        )

        job_latest_end = min(
            time_to_minutes(job.deadline),
            shift_end_minute,
        )

        latest_start = (
            job_latest_end
            - job.duration_minutes
        )

        if latest_start < job_earliest:
            raise RuntimeError(
                f"{job.id} cannot fit inside its "
                "time window and crew shift."
            )

        possible_starts = range(
            job_earliest,
            latest_start + 1,
            SLOT_MINUTES,
        )

        job_variables = []

        for start in possible_starts:
            variable = model.NewBoolVar(
                f"{job.id}_{start}"
            )

            variables[(job.id, start)] = variable
            job_variables.append(variable)

            heat_load, _ = calculate_heat_load(
                job,
                start,
                temperature_matrix,
            )

            delay_hours = (
                start
                - time_to_minutes(job.earliest_start)
            ) / 60

            operational_cost = (
                weights.heat * heat_load
                + weights.delay * delay_hours
            )

            costs[(job.id, start)] = operational_cost

        # Every job must be scheduled exactly once.
        model.Add(sum(job_variables) == 1)

    # --------------------------------
    # One crew: jobs cannot overlap
    # --------------------------------

    for minute in range(
        shift_start_minute,
        shift_end_minute,
        SLOT_MINUTES,
    ):
        active_variables = []

        for job in jobs:
            for (
                job_id,
                start,
            ), variable in variables.items():
                if job_id != job.id:
                    continue

                if (
                    start
                    <= minute
                    < start + job.duration_minutes
                ):
                    active_variables.append(variable)

        if active_variables:
            model.Add(
                sum(active_variables) <= 1
            )

    # --------------------------------
    # Objective
    # --------------------------------

    scale = 1000

    model.Minimize(
        sum(
            round(costs[key] * scale) * variable
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
        cp_model.FEASIBLE,
    ):
        raise RuntimeError(
            "No feasible schedule found."
        )

    schedule = []

    for job in jobs:
        for (
            job_id,
            start,
        ), variable in variables.items():
            if (
                job_id == job.id
                and solver.Value(variable)
            ):
                heat_load, average_temperature = (
                    calculate_heat_load(
                        job,
                        start,
                        temperature_matrix,
                    )
                )

                schedule.append(
                    ScheduleAssignment(
                        job_id=job.id,
                        worker_id=worker_id,
                        start_minute=start,
                        end_minute=(
                            start
                            + job.duration_minutes
                        ),
                        temperature_c=average_temperature,
                        heat_load=heat_load,
                    )
                )

    schedule.sort(
        key=lambda assignment: (
            assignment.start_minute
        )
    )

    return schedule