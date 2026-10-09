import csv
import io
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from heatops.benchmark.scenario_generator import generate_scenario
from heatops.cli import main
from heatops.ui.fleet import schedule_csv


def test_cli_fleet_and_legacy(capsys, tmp_path):
    s = generate_scenario(5, 2)
    path = tmp_path / "scenario.json"
    s.save(path)
    assert (
        main(["--scenario", str(path), "--policy", "delay_budget", "--format", "json"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert (
        payload["comparison"]["delay_budget"]["metrics"]["constraint_violations"] == 0
    )
    rows = payload["comparison"]["delay_budget"]["result"]["assignments"]
    exported = list(csv.DictReader(io.StringIO(schedule_csv(rows))))
    assert [r["job_id"] for r in exported] == [r["job_id"] for r in rows]
    assert main(["--mode", "heat_first", "--format", "json"]) == 0
    legacy = json.loads(capsys.readouterr().out)
    assert round(legacy["comparison"]["heat_load_reduction_percent"], 2) == 2.97


def test_fleet_app_runs_and_exports_without_credentials(monkeypatch):
    monkeypatch.delenv("FORTYGUARD_API_KEY", raising=False)
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "app.py", default_timeout=45
    ).run()
    app.checkbox(key="fleet_workspace").check().run()
    assert not app.exception
    app.selectbox[1].select(5).run()
    app.button[0].click().run()
    assert not app.exception
    p = app.session_state["fleet_payload"]
    assert len(p["comparison"]["balanced"]["result"]["assignments"]) == 5
    assert p["scenario"]["metadata"]["source"] == "synthetic"
    assert len(app.metric) == 4
    assert not app.error


def test_fleet_app_invalid_capacity_handled():
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "app.py", default_timeout=45
    ).run()
    app.checkbox(key="fleet_workspace").check().run()
    app.selectbox[1].select(100).run()
    app.number_input[0].set_value(1).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.error


def test_custom_csv_schema_roundtrip():
    from dataclasses import asdict

    from heatops.ui.fleet import csv_scenario

    s = generate_scenario(2, 2)

    def serialize(rows):
        f = io.StringIO()
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        return f.getvalue()

    workers = []
    for w in s.workers:
        row = asdict(w)
        row["skills"] = ";".join(w.skills)
        row["unavailable"] = json.dumps(w.unavailable)
        workers.append(row)
    loaded = csv_scenario(
        serialize([asdict(j) for j in s.jobs]),
        serialize(workers),
        json.dumps(s.temperature_matrix),
    )
    assert loaded.jobs == s.jobs
    assert loaded.workers == s.workers
    assert loaded.metadata["source"] == "user_supplied_unverified"
