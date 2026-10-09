"""Streamlit multi-crew workspace. Computation only on explicit user request."""

import csv
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from heatops.benchmark.scenario_generator import (
    FAMILIES,
    Scenario,
    generate_scenario,
    scenario_from_dict,
)
from heatops.benchmark.scenario_validation import validate_scenario
from heatops.cli import DEFAULT_SCENARIO
from heatops.domain.config import SchedulerConfig
from heatops.domain.loaders import load_jobs, load_temperature_matrix, load_workers
from heatops.domain.models import Job, Worker
from heatops.evaluation.fleet import compare_fleet
from heatops.integrations.open_meteo import OpenMeteoProvider
from heatops.integrations.weather_provider import (
    FortyGuardProvider,
    StaticProvider,
    fetch_with_fallback,
)
from heatops.optimization.multi_crew import POLICIES, SUCCESS
from heatops.optimization.travel import TravelConfig


def schedule_csv(assignments):
    fields = (
        "job_id",
        "worker_id",
        "start_minute",
        "end_minute",
        "temperature_c",
        "heat_load",
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(assignments)
    return output.getvalue()


def csv_scenario(jobs_text, workers_text, temperatures_text):
    jobs = []
    for row in csv.DictReader(io.StringIO(jobs_text)):
        for key in ("latitude", "longitude", "physical_intensity"):
            if row.get(key):
                row[key] = float(row[key])
            else:
                row.pop(key, None)
        for key in ("duration_minutes", "priority"):
            row[key] = int(row[key])
        row["required_skill"] = row.get("required_skill") or None
        jobs.append(Job(**row))
    workers = []
    for row in csv.DictReader(io.StringIO(workers_text)):
        row["start_latitude"], row["start_longitude"] = (
            float(row["start_latitude"]),
            float(row["start_longitude"]),
        )
        row["skills"] = tuple(
            s.strip() for s in row.get("skills", "").split(";") if s.strip()
        )
        if row.get("acclimatization"):
            row["acclimatization"] = float(row["acclimatization"])
        else:
            row.pop("acclimatization", None)
        if row.get("unavailable"):
            row["unavailable"] = json.loads(row["unavailable"])
        else:
            row.pop("unavailable", None)
        workers.append(Worker(**row))
    s = Scenario(
        jobs,
        workers,
        json.loads(temperatures_text),
        {"source": "user_supplied_unverified"},
    )
    validate_scenario(s)
    return s


@st.cache_resource
def meteo_provider():
    return OpenMeteoProvider()


def render_workspace():
    st.header("Multi-crew workspace")
    st.caption(
        "Compare crews, scheduling delay and modeled Heat Load. Results are planning estimates, not medical risk scores."
    )
    with st.sidebar:
        scenario_type = st.selectbox(
            "Scenario",
            ("Synthetic workload", "Phoenix snapshot", "Upload JSON", "Upload CSV"),
        )
        n_jobs = st.selectbox("Job count", (5, 10, 25, 50, 100), index=1)
        crews = st.number_input("Crew count", 1, 10, 2)
        seed = st.number_input("Scenario seed", 0, 1000000, 42)
        family = st.selectbox("Temperature family", FAMILIES, index=1)
        policy = st.selectbox("Fleet policy", POLICIES, index=2)
        budget = st.number_input(
            "Extra priority-weighted delay (minutes)", 0, 10000, 60
        )
        limit = st.slider("Solve limit per policy (seconds)", 1, 30, 5)
        travel_enabled = st.checkbox("Enforce estimated travel (up to 25 jobs)")
        speed = st.number_input("Assumed travel speed (km/h)", 1.0, 120.0, 30.0)
        source = st.selectbox(
            "Weather source",
            ("Scenario data (offline)", "Open-Meteo", "FortyGuard API"),
        )
        weather_date = st.date_input("Weather date", datetime.now(UTC).date())
        timezone = st.text_input("Local timezone", "America/Phoenix")
        uploaded = (
            st.file_uploader("Scenario JSON", type=["json"])
            if scenario_type == "Upload JSON"
            else None
        )
        uploads = []
        if scenario_type == "Upload CSV":
            uploads = [
                st.file_uploader(label, type=[ext])
                for label, ext in (
                    ("Jobs CSV", "csv"),
                    ("Workers CSV", "csv"),
                    ("Temperature matrix JSON", "json"),
                )
            ]
        requested = st.button("Run multi-crew comparison", type="primary")
    if requested:
        st.session_state.pop("fleet_payload", None)
        try:
            if scenario_type == "Synthetic workload":
                s = generate_scenario(n_jobs, crews, seed, family)
            elif scenario_type == "Phoenix snapshot":
                workers = load_workers(DEFAULT_SCENARIO / "workers.json")
                if crews > len(workers):
                    raise ValueError(
                        f"Phoenix provides {len(workers)} crews; choose at most that many"
                    )
                metadata = json.loads((DEFAULT_SCENARIO / "metadata.json").read_text())[
                    "temperature_data"
                ]
                s = Scenario(
                    load_jobs(DEFAULT_SCENARIO / "jobs.json"),
                    workers[:crews],
                    load_temperature_matrix(
                        DEFAULT_SCENARIO / "temperature_matrix.json"
                    ),
                    metadata,
                )
            elif scenario_type == "Upload JSON":
                if uploaded is None:
                    raise ValueError("Upload a scenario JSON first")
                s = scenario_from_dict(json.loads(uploaded.getvalue()))
            else:
                if len(uploads) != 3 or any(x is None for x in uploads):
                    raise ValueError("Upload all three CSV/matrix inputs first")
                s = csv_scenario(*(x.getvalue().decode("utf-8") for x in uploads))
            if len(s.jobs) > 100 or len(s.workers) > 10:
                raise ValueError("Dashboard limit: 100 jobs and 10 crews")
            if source != "Scenario data (offline)":
                provider = (
                    meteo_provider() if source == "Open-Meteo" else FortyGuardProvider()
                )
                weather = fetch_with_fallback(
                    provider,
                    s.jobs,
                    weather_date.isoformat(),
                    timezone,
                    fallback=StaticProvider(s.temperature_matrix, s.metadata),
                )
                s.temperature_matrix, s.metadata, s.witness = (
                    weather.matrix,
                    weather.metadata,
                    (),
                )
            validate_scenario(s)
            config, travel = (
                SchedulerConfig(solver_time_limit_seconds=limit),
                TravelConfig(enabled=travel_enabled, speed_kmh=speed),
            )
            with st.spinner("Solving baseline and selected policy…"):
                comparison = compare_fleet(
                    s.jobs,
                    s.workers,
                    s.temperature_matrix,
                    policies=(policy,),
                    config=config,
                    travel=travel,
                    additional_delay_minutes=budget,
                    initial_schedule=s.witness if not travel_enabled else (),
                )
            st.session_state["fleet_payload"] = {
                "comparison": comparison,
                "scenario": s.to_dict(),
                "policy": policy,
                "config": asdict(config),
                "travel": asdict(travel),
            }
        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as error:
            st.error(f"Could not build comparison: {error}")
    if "fleet_payload" not in st.session_state:
        st.info(
            "Choose a workload and click Run multi-crew comparison. No API key is needed for offline data."
        )
        return
    payload = st.session_state["fleet_payload"]
    comparison, s, selected = (
        payload["comparison"],
        payload["scenario"],
        payload["policy"],
    )
    st.caption("Showing the last completed run. Click Run to apply changed controls.")
    metadata = s["metadata"]
    st.info(
        f"Temperature source: {metadata.get('source')} · date: {metadata.get('data_date') or metadata.get('date') or 'synthetic / unspecified'}"
    )
    if metadata.get("fallback_reason"):
        st.warning(
            "Weather retrieval unavailable; this result uses the explicitly labeled scenario data."
        )
    if metadata.get("attribution"):
        st.caption(metadata["attribution"])
    st.download_button(
        "Download comparison JSON",
        json.dumps(payload, indent=2),
        "heatops-comparison.json",
        "application/json",
    )
    p = comparison.get(selected)
    if p is None:
        st.error(
            "Selected policy was not run because the baseline had no feasible incumbent."
        )
        st.json(comparison)
        return
    r, m = p["result"], p["metrics"]
    if r["status"] not in SUCCESS:
        st.warning(f"Solver status: {r['status']} · {r['message']}")
        return
    if m["constraint_violations"]:
        st.error("Independent validation failed; do not use this schedule.")
        st.json(m["violations"])
        return
    cards = st.columns(4)
    cards[0].metric(
        "Heat Load reduction",
        f"{p['heat_reduction_percent']:.2f}%"
        if p["heat_reduction_percent"] is not None
        else "N/A",
    )
    cards[1].metric("Assigned jobs", len(r["assignments"]))
    cards[2].metric("Weighted delay (hours)", f"{r['weighted_delay_minutes'] / 60:.2f}")
    cards[3].metric("Runtime (seconds)", f"{r['runtime_seconds']:.3f}")
    st.caption(
        f"{r['status']} · integer-objective gap {r['relative_gap']:.2%} · {m['constraint_violations']} constraint violations"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "policy": name,
                    "status": x["result"]["status"],
                    "Heat Load": x["result"]["total_heat_load"],
                    "weighted delay minutes": x["result"]["weighted_delay_minutes"],
                    "runtime seconds": x["result"]["runtime_seconds"],
                    "travel km": x["metrics"]["estimated_travel_km"],
                }
                for name, x in comparison.items()
            ]
        ),
        hide_index=True,
    )
    for name, data in comparison.items():
        rows = data["result"]["assignments"]
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        st.subheader(f"{name} · crew timeline")
        chart = (
            alt.Chart(frame)
            .mark_bar(cornerRadius=3)
            .encode(
                x=alt.X(
                    "start_minute:Q",
                    title="Minutes from midnight",
                    scale=alt.Scale(zero=False),
                ),
                x2="end_minute:Q",
                y=alt.Y("worker_id:N", title="Crew"),
                color="worker_id:N",
                tooltip=[
                    "job_id",
                    "worker_id",
                    "start_minute",
                    "end_minute",
                    "temperature_c",
                    "heat_load",
                ],
            )
        )
        st.altair_chart(chart, width="stretch")
    st.subheader("Crew utilization")
    st.bar_chart(
        pd.DataFrame(
            {
                "crew": list(m["crew_utilization"]),
                "service / available shift": list(m["crew_utilization"].values()),
            }
        ).set_index("crew")
    )
    frame = pd.DataFrame(r["assignments"]).merge(
        pd.DataFrame(s["jobs"])[["id", "name", "latitude", "longitude"]],
        left_on="job_id",
        right_on="id",
    )
    crew_colors = {
        w["id"]: [40 + (i * 79) % 200, 70 + (i * 43) % 160, 100 + (i * 61) % 150]
        for i, w in enumerate(s["workers"])
    }
    frame["color"] = frame.worker_id.map(crew_colors)
    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            frame,
            get_position="[longitude, latitude]",
            get_fill_color="color",
            get_radius=90,
            pickable=True,
        )
    ]
    if payload["travel"]["enabled"]:
        paths = []
        for w in s["workers"]:
            route = frame[frame.worker_id == w["id"]].sort_values("start_minute")
            if len(route):
                paths.append(
                    {
                        "path": [
                            [w["start_longitude"], w["start_latitude"]],
                            *route[["longitude", "latitude"]].values.tolist(),
                        ],
                        "color": crew_colors[w["id"]],
                    }
                )
        layers.append(
            pdk.Layer(
                "PathLayer",
                paths,
                get_path="path",
                get_color="color",
                width_min_pixels=3,
            )
        )
        st.caption(
            f"Estimated travel: {m['estimated_travel_km']:.2f} km / {m['estimated_travel_minutes']} minutes. Straight lines show task order, not road directions."
        )
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=float(frame.latitude.mean()),
                longitude=float(frame.longitude.mean()),
                zoom=11,
            ),
            tooltip={"text": "{job_id} · {worker_id}"},
        )
    )
    curves = [
        {"job": key, "hour": t, "temperature_c": v}
        for key, value in s["temperature_matrix"].items()
        for t, v in value["temperatures"].items()
    ]
    st.subheader("Temperature profiles")
    st.altair_chart(
        alt.Chart(pd.DataFrame(curves))
        .mark_line()
        .encode(x="hour:O", y="temperature_c:Q", color="job:N"),
        width="stretch",
    )
    st.dataframe(frame, hide_index=True)
    st.download_button(
        "Download schedule CSV",
        schedule_csv(r["assignments"]),
        "heatops-schedule.csv",
        "text/csv",
    )
    st.download_button(
        "Download schedule JSON",
        json.dumps(r["assignments"], indent=2),
        "heatops-schedule.json",
        "application/json",
    )
    st.download_button(
        "Download metrics JSON",
        json.dumps(m, indent=2),
        "heatops-metrics.json",
        "application/json",
    )
