import json

from heatops.benchmark.runner import run_benchmarks


def test_end_to_end_benchmark_and_resume(tmp_path):
    manifest = {
        "solver_time_limit_seconds": 2,
        "additional_weighted_delay_minutes": 60,
        "configurations": [
            {
                "label": "smoke",
                "jobs": 3,
                "crews": 2,
                "families": ["hot", "mild"],
                "seed_start": 0,
                "instances": 1,
                "travel": False,
            }
        ],
    }
    rows = run_benchmarks(manifest, tmp_path)
    assert len(rows) == 8
    assert all(r["status"] == "OPTIMAL" for r in rows)
    assert all(r["constraint_violations"] == 0 for r in rows)
    assert all(r["reduction_percent"] is None for r in rows if r["family"] == "mild")
    summary = json.loads((tmp_path / "benchmark_summary.json").read_text())
    assert len(summary) == 8
    assert run_benchmarks(manifest, tmp_path, resume=True) == rows
    assert (tmp_path / "tradeoff.png").stat().st_size > 1000


def test_parallel_runner_retains_all_policy_rows(tmp_path):
    manifest = {
        "execution_workers": 2,
        "solver_time_limit_seconds": 2,
        "additional_weighted_delay_minutes": 0,
        "configurations": [
            {
                "label": "parallel",
                "jobs": 2,
                "crews": 2,
                "families": ["hot"],
                "seed_start": 0,
                "instances": 2,
                "travel": False,
            }
        ],
    }
    rows = run_benchmarks(manifest, tmp_path)
    assert len(rows) == 8
    assert all(r["constraint_violations"] == 0 for r in rows)
    assert (tmp_path / "benchmark_details.jsonl.gz").exists()
