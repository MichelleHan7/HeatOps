import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from heatops.cli import main


def _write_inputs(tmp_path):
    jobs = tmp_path / "jobs.json"
    workers = tmp_path / "workers.json"
    temperatures = tmp_path / "temperatures.json"
    jobs.write_text(
        json.dumps(
            [
                {
                    "id": "JOB-1",
                    "name": "Inspection",
                    "latitude": 33.45,
                    "longitude": -112.07,
                    "duration_minutes": 60,
                    "earliest_start": "08:00",
                    "deadline": "10:00",
                    "priority": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    workers.write_text(
        json.dumps(
            [
                {
                    "id": "CREW-1",
                    "name": "Crew 1",
                    "start_latitude": 33.45,
                    "start_longitude": -112.07,
                    "shift_start": "08:00",
                    "shift_end": "10:00",
                    "skills": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    temperatures.write_text(
        json.dumps(
            {
                "JOB-1": {
                    "name": "Inspection",
                    "temperatures": {
                        "08:00": 36.0,
                        "09:00": 34.0,
                        "10:00": 33.0,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return jobs, workers, temperatures


def _args(paths, *extra):
    jobs, workers, temperatures = paths
    return [
        "--jobs",
        str(jobs),
        "--workers",
        str(workers),
        "--temperatures",
        str(temperatures),
        "--worker-id",
        "CREW-1",
        *extra,
    ]


def test_cli_json_output_is_machine_readable(tmp_path, capsys):
    return_code = main(
        _args(_write_inputs(tmp_path), "--mode", "heat_first", "--format", "json")
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert return_code == 0
    assert captured.err == ""
    assert payload["mode"] == "heat_first"
    assert payload["weights"] == {"delay": 0.0, "heat": 1.0}
    assert payload["comparison"]["moved_jobs"] == 1


def test_cli_text_output_uses_custom_heat_priority(tmp_path, capsys):
    return_code = main(_args(_write_inputs(tmp_path), "--heat-priority", "75"))

    output = capsys.readouterr().out

    assert return_code == 0
    assert "custom (75% heat priority)" in output
    assert "BASELINE SCHEDULE" in output
    assert "HEATOPS SCHEDULE" in output


def test_cli_returns_clear_error_for_unknown_worker(tmp_path, capsys):
    args = _args(_write_inputs(tmp_path))
    args[args.index("CREW-1")] = "MISSING"

    return_code = main(args)

    captured = capsys.readouterr()
    assert return_code == 2
    assert captured.out == ""
    assert "Unknown worker 'MISSING'" in captured.err


def test_cli_rejects_unknown_mode():
    with pytest.raises(SystemExit) as error:
        main(["--mode", "unknown"])

    assert error.value.code == 2


def test_evaluate_script_is_import_safe(capsys):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"
    spec = spec_from_file_location("heatops_evaluate_script", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
