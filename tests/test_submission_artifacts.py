import json
from pathlib import Path

import pytest

from heatops.domain.config import SchedulerConfig
from heatops.domain.loaders import load_jobs, load_temperature_matrix, load_workers
from heatops.evaluation.service import compare_schedules
from heatops.optimization.presets import HEAT_FIRST

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "data" / "scenarios" / "phoenix-demo"
MANIFEST = ROOT / "submission" / "heatops-submission.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_submission_package_has_every_local_artifact():
    manifest = _manifest()
    paths = {
        "README.md",
        manifest["video"]["script"],
        *manifest["documentation"].values(),
    }

    assert all((ROOT / path).is_file() for path in paths)
    assert (ROOT / "app.py").is_file()
    assert manifest["demo"]["command"] == "streamlit run app.py"


def test_submission_evidence_matches_reproducible_scenario():
    manifest = _manifest()
    evidence = manifest["scenario_evidence"]
    jobs = load_jobs(SCENARIO / "jobs.json")
    workers = load_workers(SCENARIO / "workers.json")
    matrix = load_temperature_matrix(SCENARIO / "temperature_matrix.json")
    metadata = json.loads((SCENARIO / "metadata.json").read_text(encoding="utf-8"))
    worker = next(
        item
        for item in workers
        if item.id == metadata["operational_assumptions"]["selected_worker_id"]
    )
    comparison = compare_schedules(jobs, matrix, worker=worker, weights=HEAT_FIRST)

    assert evidence["scenario_id"] == metadata["scenario_id"]
    assert evidence["temperature_provider"] == metadata["temperature_data"]["provider"]
    assert (
        evidence["temperature_data_date"] == metadata["temperature_data"]["data_date"]
    )
    assert evidence["heat_threshold_c"] == SchedulerConfig().heat_threshold_c
    assert (
        metadata["operational_assumptions"]["heat_threshold_c"]
        == SchedulerConfig().heat_threshold_c
    )
    assert evidence["baseline_heat_load"] == round(
        comparison.baseline_metrics.total_heat_load, 2
    )
    assert evidence["optimized_heat_load"] == round(
        comparison.optimized_metrics.total_heat_load, 2
    )
    assert evidence["heat_load_reduction_percent"] == pytest.approx(
        round(comparison.heat_load_reduction_percent, 2)
    )
    assert evidence["jobs_moved"] == comparison.moved_jobs
    assert evidence["jobs_total"] == len(jobs)


def test_submission_status_does_not_claim_unpublished_links_are_ready():
    manifest = _manifest()
    status = manifest["deliverable_status"]

    assert manifest["repository_url"] == "https://github.com/MichelleHan7/HeatOps"
    assert manifest["demo"]["hosted_url"] is None
    assert manifest["video"]["url"] is None
    assert status["working_prototype"] == "ready"
    assert status["hosted_demo"] == "pending"
    assert status["video"] == "pending"
    assert manifest["video"]["required_duration_minutes"] == [2, 5]


def test_ci_workflow_covers_quality_and_demo_smoke_checks():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for required in (
        'python-version: ["3.11", "3.12"]',
        'python -m pip install -e ".[demo,dev]"',
        "ruff check .",
        "ruff format --check .",
        "pytest -q",
        "python -m compileall",
        "heatops-evaluate --mode heat_first --format json",
    ):
        assert required in workflow
