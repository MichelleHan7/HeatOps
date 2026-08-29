import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, shape

from heatops.domain.loaders import load_jobs, load_temperature_matrix, load_workers
from heatops.evaluation.service import compare_schedules
from heatops.integrations.aoi import build_aoi_from_jobs
from heatops.integrations.temperature_service import validate_temperature_matrix
from heatops.optimization.presets import PRESETS

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "data" / "scenarios" / "phoenix-demo"


def _load_scenario():
    jobs = load_jobs(SCENARIO / "jobs.json")
    workers = load_workers(SCENARIO / "workers.json")
    matrix = load_temperature_matrix(SCENARIO / "temperature_matrix.json")
    metadata = json.loads((SCENARIO / "metadata.json").read_text(encoding="utf-8"))
    return jobs, workers, matrix, metadata


def test_phoenix_demo_temperature_snapshot_has_traceable_provenance():
    _, _, scenario_matrix, metadata = _load_scenario()
    source_path = ROOT / metadata["temperature_data"]["source_file"]
    scenario_path = SCENARIO / "temperature_matrix.json"

    assert scenario_matrix == load_temperature_matrix(source_path)
    assert (
        hashlib.sha256(source_path.read_bytes()).hexdigest()
        == metadata["temperature_data"]["source_sha256"]
    )
    assert scenario_path.read_bytes() == source_path.read_bytes()
    assert metadata["temperature_data"]["provider"] == "FortyGuard"


def test_phoenix_demo_has_complete_valid_jobs_temperatures_and_aoi():
    jobs, workers, matrix, metadata = _load_scenario()
    slots = metadata["temperature_data"]["time_slots"]
    selected_worker = next(
        worker
        for worker in workers
        if worker.id == metadata["operational_assumptions"]["selected_worker_id"]
    )

    assert len({job.id for job in jobs}) == len(jobs) == 5
    assert all(job.required_skill in selected_worker.skills for job in jobs)
    validate_temperature_matrix(matrix, jobs, slots)

    aoi = build_aoi_from_jobs(
        jobs,
        padding=metadata["aoi"]["padding_degrees"],
    )
    polygon = shape(aoi["features"][0]["geometry"])
    assert all(polygon.covers(Point(job.longitude, job.latitude)) for job in jobs)


def test_all_demo_presets_are_feasible_and_heat_first_improves_heat_load():
    jobs, workers, matrix, metadata = _load_scenario()
    worker = next(
        worker
        for worker in workers
        if worker.id == metadata["operational_assumptions"]["selected_worker_id"]
    )
    comparisons = {
        name: compare_schedules(jobs, matrix, worker=worker, weights=weights)
        for name, weights in PRESETS.items()
    }

    assert all(
        len(comparison.optimized_result.assignments) == len(jobs)
        for comparison in comparisons.values()
    )
    assert all(
        comparison.optimized_result.status in {"OPTIMAL", "FEASIBLE"}
        for comparison in comparisons.values()
    )
    assert (
        comparisons["heat_first"].optimized_metrics.total_heat_load
        < comparisons["operations_first"].optimized_metrics.total_heat_load
    )
    assert comparisons["heat_first"].moved_jobs > 0
