import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from heatops.cli import DEFAULT_SCENARIO
from heatops.domain.config import SchedulerConfig
from heatops.domain.loaders import load_jobs, load_temperature_matrix, load_workers
from heatops.domain.models import (
    Job,
    OptimizationWeights,
    TemperatureMatrix,
    Worker,
)
from heatops.evaluation.models import ScheduleComparison
from heatops.evaluation.service import compare_schedules
from heatops.integrations.fortyguard import FortyGuardClient
from heatops.integrations.temperature_service import (
    TemperatureServiceError,
    fetch_temperature_data,
)
from heatops.optimization.presets import PRESETS, weights_from_heat_priority
from heatops.presentation import (
    MODE_LABELS,
    JobChangeRecord,
    MapMarkerRecord,
    MetricCardRecord,
    TemperatureCurveRecord,
    TimelineRecord,
    TradeoffRecord,
    build_job_change_records,
    build_map_marker_records,
    build_metric_card_records,
    build_temperature_curve_records,
    build_timeline_records,
    build_tradeoff_records,
)

MODE_OPTIONS = (*MODE_LABELS.values(), "Custom")
MODE_KEYS_BY_LABEL = {label: key for key, label in MODE_LABELS.items()}


class ScenarioLoadError(RuntimeError):
    """Raised when the bundled demo scenario cannot be loaded safely."""


@dataclass(frozen=True)
class DemoScenario:
    jobs: tuple[Job, ...]
    workers: tuple[Worker, ...]
    selected_worker: Worker
    temperature_matrix: TemperatureMatrix
    metadata: dict


@dataclass(frozen=True)
class TemperatureSourceState:
    matrix: TemperatureMatrix
    source: Literal["snapshot", "live", "cache"]
    label: str
    detail: str
    data_date: str


@dataclass(frozen=True)
class DashboardState:
    mode_key: str
    mode_label: str
    weights: OptimizationWeights
    comparison: ScheduleComparison
    preset_comparisons: dict[str, ScheduleComparison]
    tradeoff_records: tuple[TradeoffRecord, ...]


def load_demo_scenario(path: str | Path = DEFAULT_SCENARIO) -> DemoScenario:
    """Load and validate the deterministic Phoenix dashboard scenario."""

    scenario_path = Path(path)

    try:
        jobs = tuple(load_jobs(scenario_path / "jobs.json"))
        workers = tuple(load_workers(scenario_path / "workers.json"))
        matrix = load_temperature_matrix(scenario_path / "temperature_matrix.json")
        metadata = json.loads(
            (scenario_path / "metadata.json").read_text(encoding="utf-8")
        )
        selected_worker_id = metadata["operational_assumptions"]["selected_worker_id"]
        selected_worker = next(
            worker for worker in workers if worker.id == selected_worker_id
        )
    except (KeyError, OSError, StopIteration, TypeError, ValueError) as error:
        raise ScenarioLoadError(
            f"Could not load the Phoenix demo scenario from {scenario_path}."
        ) from error

    if not jobs:
        raise ScenarioLoadError("The Phoenix demo scenario contains no jobs.")

    return DemoScenario(
        jobs=jobs,
        workers=workers,
        selected_worker=selected_worker,
        temperature_matrix=matrix,
        metadata=metadata,
    )


def resolve_weights(
    mode_label: str,
    heat_priority: float,
) -> tuple[str, OptimizationWeights]:
    """Resolve a preset label or the dashboard's custom priority control."""

    if mode_label == "Custom":
        return "custom", weights_from_heat_priority(heat_priority)

    try:
        mode_key = MODE_KEYS_BY_LABEL[mode_label]
    except KeyError as error:
        valid = ", ".join(MODE_OPTIONS)
        raise ValueError(
            f"Unknown dashboard mode {mode_label!r}. Choose from: {valid}."
        ) from error

    return mode_key, PRESETS[mode_key]


def _configured_fortyguard_client() -> FortyGuardClient | None:
    api_key = os.getenv("FORTYGUARD_API_KEY")
    base_url = os.getenv("FORTYGUARD_BASE_URL")

    if not api_key:
        try:
            api_key = st.secrets.get("FORTYGUARD_API_KEY")
            base_url = st.secrets.get("FORTYGUARD_BASE_URL", base_url)
        except StreamlitSecretNotFoundError:
            return None

    if not api_key:
        return None

    return FortyGuardClient(api_key=api_key, base_url=base_url)


def resolve_temperature_source(
    scenario: DemoScenario,
    use_live_data: bool,
    *,
    client: FortyGuardClient | None = None,
    cache_dir: str | Path | None = None,
) -> TemperatureSourceState:
    """Use live/cached FortyGuard data when requested, otherwise the snapshot."""

    temperature_metadata = scenario.metadata["temperature_data"]
    snapshot_date = str(temperature_metadata["data_date"])

    if not use_live_data:
        return TemperatureSourceState(
            matrix=scenario.temperature_matrix,
            source="snapshot",
            label="Bundled FortyGuard snapshot",
            detail="Reproducible Phoenix data included with the demo.",
            data_date=snapshot_date,
        )

    fetch_kwargs = {}

    if cache_dir is not None:
        fetch_kwargs["cache_dir"] = cache_dir

    try:
        result = fetch_temperature_data(
            list(scenario.jobs),
            snapshot_date,
            tuple(temperature_metadata["time_slots"]),
            client=client,
            granularity=int(temperature_metadata["granularity_meters"]),
            **fetch_kwargs,
        )
    except TemperatureServiceError:
        return TemperatureSourceState(
            matrix=scenario.temperature_matrix,
            source="snapshot",
            label="Bundled FortyGuard snapshot",
            detail=(
                "Live data was unavailable, so HeatOps kept the validated demo "
                "snapshot."
            ),
            data_date=snapshot_date,
        )

    source = result.metadata.source
    label = (
        "Live FortyGuard data" if source == "live" else "Cached FortyGuard API response"
    )
    return TemperatureSourceState(
        matrix=result.matrix,
        source=source,
        label=label,
        detail=(
            "Temperature matrix passed job/time-slot validation before optimization."
        ),
        data_date=result.metadata.data_date,
    )


def build_dashboard_state(
    scenario: DemoScenario,
    temperature_matrix: TemperatureMatrix,
    mode_label: str,
    heat_priority: float,
) -> DashboardState:
    """Compute the selected result and the three preset tradeoff points."""

    mode_key, weights = resolve_weights(mode_label, heat_priority)
    jobs = list(scenario.jobs)
    worker = scenario.selected_worker
    config = SchedulerConfig()
    preset_comparisons = {
        preset: compare_schedules(
            jobs,
            temperature_matrix,
            worker=worker,
            weights=preset_weights,
            config=config,
        )
        for preset, preset_weights in PRESETS.items()
    }

    if mode_key in preset_comparisons:
        comparison = preset_comparisons[mode_key]
        tradeoff_comparisons = preset_comparisons
        tradeoff_weights = PRESETS
    else:
        comparison = compare_schedules(
            jobs,
            temperature_matrix,
            worker=worker,
            weights=weights,
            config=config,
        )
        tradeoff_comparisons = {**preset_comparisons, mode_key: comparison}
        tradeoff_weights = {**PRESETS, mode_key: weights}

    return DashboardState(
        mode_key=mode_key,
        mode_label=mode_label,
        weights=weights,
        comparison=comparison,
        preset_comparisons=preset_comparisons,
        tradeoff_records=build_tradeoff_records(
            tradeoff_comparisons,
            tradeoff_weights,
        ),
    )


def _records_frame(records: tuple) -> pd.DataFrame:
    return pd.DataFrame(asdict(record) for record in records)


def _timeline_chart(records: tuple[TimelineRecord, ...]) -> alt.Chart:
    frame = _records_frame(records)
    base_date = pd.Timestamp("2026-08-24")
    frame["start"] = base_date + pd.to_timedelta(frame["start_minute"], unit="m")
    frame["end"] = base_date + pd.to_timedelta(frame["end_minute"], unit="m")

    return (
        alt.Chart(frame)
        .mark_bar(cornerRadius=5, height=22)
        .encode(
            x=alt.X("start:T", title="Time", axis=alt.Axis(format="%H:%M")),
            x2="end:T",
            y=alt.Y("job_name:N", title=None, sort=None),
            color=alt.Color(
                "temperature_c:Q",
                title="Temperature (C)",
                scale=alt.Scale(scheme="orangered"),
            ),
            tooltip=[
                alt.Tooltip("job_name:N", title="Job"),
                alt.Tooltip("start_time:N", title="Start"),
                alt.Tooltip("end_time:N", title="End"),
                alt.Tooltip("temperature_c:Q", title="Temperature", format=".2f"),
                alt.Tooltip("heat_load:Q", title="Heat Load", format=".2f"),
            ],
        )
        .properties(height=max(220, len(records) * 42))
    )


def _temperature_chart(
    records: tuple[TemperatureCurveRecord, ...],
    threshold_c: float,
) -> alt.LayerChart:
    frame = _records_frame(records)
    base_date = pd.Timestamp("2026-08-24")
    frame["time"] = base_date + pd.to_timedelta(frame["minute"], unit="m")
    curves = (
        alt.Chart(frame)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("time:T", title="Time", axis=alt.Axis(format="%H:%M")),
            y=alt.Y(
                "temperature_c:Q",
                title="Modeled temperature (C)",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color("job_name:N", title="Job"),
            tooltip=[
                alt.Tooltip("job_name:N", title="Job"),
                alt.Tooltip("time_label:N", title="Time"),
                alt.Tooltip("temperature_c:Q", title="Temperature", format=".2f"),
            ],
        )
    )
    threshold = (
        alt.Chart(pd.DataFrame({"threshold": [threshold_c]}))
        .mark_rule(color="#475569", strokeDash=[6, 4])
        .encode(
            y="threshold:Q",
            tooltip=[alt.Tooltip("threshold:Q", title="Heat threshold")],
        )
    )
    return curves + threshold


def _tradeoff_chart(records: tuple[TradeoffRecord, ...]) -> alt.Chart:
    frame = _records_frame(records)
    return (
        alt.Chart(frame)
        .mark_circle(size=220, opacity=0.9)
        .encode(
            x=alt.X(
                "priority_weighted_delay_hours:Q",
                title="Priority-weighted delay (hours)",
            ),
            y=alt.Y(
                "total_heat_load:Q",
                title="Operational Heat Load",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color("mode_label:N", title="Mode"),
            tooltip=[
                alt.Tooltip("mode_label:N", title="Mode"),
                alt.Tooltip("heat_weight_percent:Q", title="Heat weight", format=".0f"),
                alt.Tooltip("total_heat_load:Q", title="Heat Load", format=".2f"),
                alt.Tooltip(
                    "priority_weighted_delay_hours:Q",
                    title="Weighted delay",
                    format=".2f",
                ),
                alt.Tooltip("moved_jobs:Q", title="Jobs moved"),
            ],
        )
        .properties(height=320)
    )


def _schedule_map(
    baseline: tuple[MapMarkerRecord, ...],
    optimized: tuple[MapMarkerRecord, ...],
) -> pdk.Deck:
    baseline_frame = _records_frame(baseline)
    optimized_frame = _records_frame(optimized)
    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            baseline_frame,
            get_position="[longitude, latitude]",
            get_fill_color=[100, 116, 139, 115],
            get_radius=145,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            optimized_frame,
            get_position="[longitude, latitude]",
            get_fill_color=[234, 88, 12, 215],
            get_radius=85,
            pickable=True,
        ),
    ]
    all_markers = (*baseline, *optimized)
    center_latitude = sum(marker.latitude for marker in all_markers) / len(all_markers)
    center_longitude = sum(marker.longitude for marker in all_markers) / len(
        all_markers
    )

    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=center_latitude,
            longitude=center_longitude,
            zoom=12.5,
            pitch=25,
        ),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={
            "html": (
                "<b>{schedule}: {job_name}</b><br/>Start: {start_time}<br/>"
                "Temperature: {temperature_c} C<br/>Heat Load: {heat_load}"
            )
        },
    )


def _render_data_source(source: TemperatureSourceState) -> None:
    message = f"{source.label} · data date {source.data_date}. {source.detail}"

    if source.source == "live":
        st.success(message, icon="✅")
    elif "unavailable" in source.detail.lower():
        st.warning(message, icon="⚠️")
    else:
        st.info(message, icon="ℹ️")


def _render_metric_cards(cards: tuple[MetricCardRecord, ...]) -> None:
    first_row = st.columns(3)
    second_row = st.columns(3)

    for column, card in zip((*first_row, *second_row), cards, strict=True):
        column.metric(
            card.label,
            card.display_value,
            card.display_delta,
            delta_color="inverse",
            help=card.help_text,
        )


def _render_schedule_tradeoff(comparison: ScheduleComparison) -> None:
    delay_delta = (
        comparison.optimized_metrics.priority_weighted_delay_hours
        - comparison.baseline_metrics.priority_weighted_delay_hours
    )
    idle_delta = (
        comparison.optimized_metrics.idle_minutes
        - comparison.baseline_metrics.idle_minutes
    )

    if delay_delta > 0 or idle_delta > 0:
        st.warning(
            "Operational trade-off: the selected schedule adds "
            f"{max(delay_delta, 0):.2f} priority-weighted delay hours and "
            f"{max(idle_delta, 0):.0f} idle minutes versus the baseline."
        )
    else:
        st.success(
            "The selected schedule does not add priority-weighted delay or crew "
            "idle time versus the baseline."
        )


def _render_job_changes(records: tuple[JobChangeRecord, ...]) -> None:
    for record in records:
        icon = "↔️" if record.moved else "•"

        with st.container(border=True):
            st.markdown(f"**{icon} {record.job_name}** · `{record.job_id}`")
            st.caption(
                f"{record.baseline_start} → {record.optimized_start} · "
                f"Temperature {record.temperature_change} · "
                f"Heat Load {record.heat_load_change}"
            )
            st.write(record.explanation)


def main() -> None:
    st.set_page_config(
        page_title="HeatOps · Heat-aware field operations",
        page_icon="☀️",
        layout="wide",
    )

    try:
        scenario = load_demo_scenario()
    except ScenarioLoadError as error:
        st.error(str(error), icon="🚨")
        return

    st.title("HeatOps")
    st.markdown(
        "**Heat-aware field operations planning powered by FortyGuard hyperlocal "
        "temperature intelligence.**"
    )
    st.caption(
        "Phoenix utility demo · Operational Heat Load is a planning score, not a "
        "medical risk assessment."
    )

    with st.sidebar:
        st.header("Optimization controls")
        mode_label = st.selectbox(
            "Optimization mode",
            MODE_OPTIONS,
            index=1,
            help="Presets make the heat-versus-delay trade-off explicit.",
        )
        heat_priority = st.slider(
            "Heat priority",
            min_value=0,
            max_value=100,
            value=50,
            step=5,
            disabled=mode_label != "Custom",
            help="Custom mode gives the remaining weight to operational delay.",
        )
        use_live_data = st.checkbox(
            "Refresh from FortyGuard API",
            value=False,
            help="Falls back to the bundled validated snapshot if live data is unavailable.",
        )
        optimize_requested = st.button(
            "Optimize schedule",
            type="primary",
            width="stretch",
        )
        st.divider()
        st.caption(
            f"Crew: {scenario.selected_worker.name} · "
            f"{scenario.selected_worker.shift_start}–{scenario.selected_worker.shift_end}"
        )
        st.caption(f"Jobs: {len(scenario.jobs)} · Slot size: 15 minutes")

    if optimize_requested or "dashboard_state" not in st.session_state:
        try:
            client = _configured_fortyguard_client() if use_live_data else None
            source = resolve_temperature_source(
                scenario,
                use_live_data,
                client=client,
            )
            dashboard = build_dashboard_state(
                scenario,
                source.matrix,
                mode_label,
                heat_priority,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            st.error(f"HeatOps could not build this schedule: {error}", icon="🚨")
            return

        st.session_state["temperature_source"] = source
        st.session_state["dashboard_state"] = dashboard

    source = st.session_state["temperature_source"]
    dashboard = st.session_state["dashboard_state"]
    comparison = dashboard.comparison
    jobs = list(scenario.jobs)
    moved_job_ids = {change.job_id for change in comparison.job_changes if change.moved}

    _render_data_source(source)
    st.subheader(f"{dashboard.mode_label} result")
    heat_weight, delay_weight = dashboard.weights.normalized()
    st.caption(
        f"Objective weights: {heat_weight:.0%} heat · {delay_weight:.0%} delay · "
        f"{comparison.moved_jobs} of {len(jobs)} jobs moved"
    )
    _render_metric_cards(build_metric_card_records(comparison))
    _render_schedule_tradeoff(comparison)

    st.subheader("Baseline vs optimized timeline")
    baseline_records = build_timeline_records(
        comparison.baseline_result,
        jobs,
        "Operations-first baseline",
    )
    optimized_records = build_timeline_records(
        comparison.optimized_result,
        jobs,
        dashboard.mode_label,
    )
    baseline_column, optimized_column = st.columns(2)

    with baseline_column:
        st.markdown("#### Operations-first baseline")
        st.altair_chart(
            _timeline_chart(baseline_records),
            width="stretch",
        )

    with optimized_column:
        st.markdown(f"#### HeatOps · {dashboard.mode_label}")
        st.altair_chart(
            _timeline_chart(optimized_records),
            width="stretch",
        )

    st.subheader("Field locations")
    baseline_markers = build_map_marker_records(
        comparison.baseline_result,
        jobs,
        "Baseline",
        moved_job_ids,
    )
    optimized_markers = build_map_marker_records(
        comparison.optimized_result,
        jobs,
        "HeatOps",
        moved_job_ids,
    )
    st.caption(
        "Large gray markers show baseline assignments; orange markers show HeatOps."
    )
    st.pydeck_chart(
        _schedule_map(baseline_markers, optimized_markers),
        width="stretch",
    )

    chart_column, tradeoff_column = st.columns(2)

    with chart_column:
        st.subheader("FortyGuard temperature curves")
        temperature_records = build_temperature_curve_records(
            jobs,
            source.matrix,
        )
        st.altair_chart(
            _temperature_chart(
                temperature_records,
                SchedulerConfig().heat_threshold_c,
            ),
            width="stretch",
        )

    with tradeoff_column:
        st.subheader("Heat vs delay trade-off")
        st.altair_chart(
            _tradeoff_chart(dashboard.tradeoff_records),
            width="stretch",
        )

    st.subheader("Why the schedule changed")
    _render_job_changes(build_job_change_records(comparison, jobs))


if __name__ == "__main__":
    main()
