import json

from heatops.domain.loaders import load_jobs, load_workers


def test_load_jobs(tmp_path):
    jobs_path = tmp_path / "jobs.json"

    jobs_path.write_text(
        json.dumps(
            [
                {
                    "id": "JOB-001",
                    "name": "Test Inspection",
                    "latitude": 33.45,
                    "longitude": -112.07,
                    "duration_minutes": 60,
                    "earliest_start": "08:00",
                    "deadline": "12:00",
                    "priority": 2,
                }
            ]
        )
    )

    jobs = load_jobs(jobs_path)

    assert len(jobs) == 1
    assert jobs[0].id == "JOB-001"
    assert jobs[0].duration_minutes == 60
    assert jobs[0].required_skill is None
    assert jobs[0].physical_intensity == 1.0


def test_load_workers(tmp_path):
    workers_path = tmp_path / "workers.json"

    workers_path.write_text(
        json.dumps(
            [
                {
                    "id": "CREW-001",
                    "name": "Crew Alpha",
                    "start_latitude": 33.45,
                    "start_longitude": -112.07,
                    "shift_start": "08:00",
                    "shift_end": "18:00",
                    "skills": ["inspection"],
                }
            ]
        )
    )

    workers = load_workers(workers_path)

    assert len(workers) == 1
    assert workers[0].id == "CREW-001"
    assert workers[0].skills == ("inspection",)
    assert workers[0].acclimatization == 1.0
