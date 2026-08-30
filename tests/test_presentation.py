from dataclasses import replace

import pytest

from heatops.domain.models import (
    Job,
    OptimizationResult,
    OptimizationWeights,
    ScheduleAssignment,
)
from heatops.evaluation.models import JobChange, ScheduleComparison, ScheduleMetrics
from heatops.presentation import (
    build_job_change_records,
    build_map_marker_records,
    build_metric_card_records,
    build_temperature_curve_records,
    build_timeline_records,
    build_tradeoff_records,
    empty_schedule_metrics,
)


def _jobs():
    return [
        Job(
            id="JOB-B",
            name="Pole inspection",
            latitude=33.46,
            longitude=-112.06,
            duration_minutes=45,
            earliest_start="08:00",
            deadline="12:00",
            priority=1,
        ),
        Job(
            id="JOB-A",
            name="Transformer inspection",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="12:00",
            priority=3,
        ),
    ]


def _assignment(job_id, start, duration, temperature, heat):
    return ScheduleAssignment(
        job_id=job_id,
        worker_id="CREW-1",
        start_minute=start,
        end_minute=start + duration,
        temperature_c=temperature,
        heat_load=heat,
    )


def _result(*assignments, status="OPTIMAL"):
    return OptimizationResult(
        assignments=assignments,
        status=status,
        objective_value=0,
        total_heat_load=sum(item.heat_load for item in assignments),
        total_delay_hours=0,
    )


def _metrics(heat, peak, minutes, weighted_delay, idle):
    return ScheduleMetrics(
        total_heat_load=heat,
        peak_temperature_c=peak,
        minutes_above_threshold=minutes,
        total_delay_hours=weighted_delay,
        priority_weighted_delay_hours=weighted_delay,
        idle_minutes=idle,
        scheduled_jobs=2,
    )


def _comparison():
    baseline = _result(
        _assignment("JOB-A", 480, 60, 38.0, 8.0),
        _assignment("JOB-B", 540, 45, 39.0, 7.0),
    )
    optimized = _result(
        _assignment("JOB-B", 480, 45, 36.0, 5.0),
        _assignment("JOB-A", 600, 60, 34.0, 4.0),
    )
    changes = (
        JobChange(
            job_id="JOB-A",
            baseline_start_minute=480,
            optimized_start_minute=600,
            start_delta_minutes=120,
            baseline_temperature_c=38.0,
            optimized_temperature_c=34.0,
            temperature_delta_c=-4.0,
            baseline_heat_load=8.0,
            optimized_heat_load=4.0,
            heat_load_delta=-4.0,
            moved=True,
            explanation="JOB-A moved later and reduced operational Heat Load.",
        ),
        JobChange(
            job_id="JOB-B",
            baseline_start_minute=540,
            optimized_start_minute=480,
            start_delta_minutes=-60,
            baseline_temperature_c=39.0,
            optimized_temperature_c=36.0,
            temperature_delta_c=-3.0,
            baseline_heat_load=7.0,
            optimized_heat_load=5.0,
            heat_load_delta=-2.0,
            moved=True,
            explanation="JOB-B moved earlier and reduced operational Heat Load.",
        ),
    )
    return ScheduleComparison(
        baseline_result=baseline,
        optimized_result=optimized,
        baseline_metrics=_metrics(15.0, 39.0, 105, 1.0, 0),
        optimized_metrics=_metrics(9.0, 36.0, 60, 4.0, 75),
        heat_load_reduction_percent=40.0,
        moved_jobs=2,
        job_changes=changes,
    )


def test_timeline_records_are_chronological_and_format_times():
    result = _result(
        _assignment("JOB-A", 600, 60, 34.0, 4.0),
        _assignment("JOB-B", 480, 45, 36.0, 5.0),
    )

    records = build_timeline_records(result, _jobs(), "HeatOps")

    assert [record.job_id for record in records] == ["JOB-B", "JOB-A"]
    assert records[0].start_time == "08:00"
    assert records[0].end_time == "08:45"
    assert records[0].schedule == "HeatOps"
    assert records[1].priority == 3


def test_map_markers_propagate_coordinates_and_moved_state():
    markers = build_map_marker_records(
        _comparison().optimized_result,
        _jobs(),
        "HeatOps",
        {"JOB-A"},
    )

    assert markers[0].job_id == "JOB-B"
    assert markers[0].latitude == 33.46
    assert markers[0].longitude == -112.06
    assert markers[0].moved is False
    assert markers[1].moved is True


def test_temperature_curves_use_stable_job_and_time_order():
    matrix = {
        "JOB-A": {
            "name": "Transformer inspection",
            "temperatures": {"09:00": 35.0, "08:00": 34.0},
        },
        "JOB-B": {
            "name": "Pole inspection",
            "temperatures": {"09:00": 36.0, "08:00": 35.0},
        },
    }

    records = build_temperature_curve_records(_jobs(), matrix)

    assert [(record.job_id, record.time_label) for record in records] == [
        ("JOB-A", "08:00"),
        ("JOB-A", "09:00"),
        ("JOB-B", "08:00"),
        ("JOB-B", "09:00"),
    ]
    assert records[0].minute == 480


def test_metric_cards_have_consistent_labels_values_and_deltas():
    cards = {card.key: card for card in build_metric_card_records(_comparison())}

    assert cards["heat_load_reduction"].display_value == "40.0%"
    assert cards["heat_load_reduction"].display_delta == "-6.00 Heat Load"
    assert cards["heat_load"].display_value == "9.00"
    assert cards["heat_load"].display_delta == "-6.00 vs baseline"
    assert cards["peak_temperature"].display_value == "36.00 C"
    assert cards["minutes_above_threshold"].display_delta == ("-45 min vs baseline")
    assert "not a medical risk assessment" in cards["heat_load"].help_text


def test_metric_cards_handle_empty_peak_without_crashing():
    empty = empty_schedule_metrics()
    comparison = replace(
        _comparison(),
        baseline_metrics=empty,
        optimized_metrics=empty,
    )
    cards = {card.key: card for card in build_metric_card_records(comparison)}

    assert cards["peak_temperature"].display_value == "N/A"
    assert cards["peak_temperature"].display_delta == "N/A"


def test_job_change_records_attach_names_and_format_changes():
    records = build_job_change_records(_comparison(), _jobs())

    assert [record.job_id for record in records] == ["JOB-A", "JOB-B"]
    assert records[0].job_name == "Transformer inspection"
    assert records[0].baseline_start == "08:00"
    assert records[0].optimized_start == "10:00"
    assert records[0].temperature_change == "-4.00 C"


def test_tradeoff_records_follow_preset_order_and_keep_numeric_metrics():
    comparison = _comparison()
    comparisons = {
        "heat_first": comparison,
        "operations_first": replace(comparison, moved_jobs=0),
        "balanced": replace(comparison, moved_jobs=1),
    }

    records = build_tradeoff_records(comparisons)

    assert [record.mode for record in records] == [
        "operations_first",
        "balanced",
        "heat_first",
    ]
    assert records[0].mode_label == "Operations-first"
    assert records[0].heat_weight_percent == 0
    assert records[2].heat_weight_percent == 100
    assert records[1].total_heat_load == 9.0


def test_tradeoff_records_require_weights_for_custom_mode():
    with pytest.raises(ValueError, match="weights are missing"):
        build_tradeoff_records({"custom": _comparison()})

    records = build_tradeoff_records(
        {"custom": _comparison()},
        {"custom": OptimizationWeights(heat=0.75, delay=0.25)},
    )
    assert records[0].mode_label == "Custom"
    assert records[0].heat_weight_percent == 75


def test_empty_or_infeasible_schedule_returns_empty_chart_records():
    result = _result(status="INFEASIBLE")

    assert build_timeline_records(result, _jobs(), "HeatOps") == ()
    assert build_map_marker_records(result, _jobs(), "HeatOps") == ()
    assert build_temperature_curve_records([], {}) == ()


def test_unknown_schedule_job_has_readable_error():
    result = _result(_assignment("UNKNOWN", 480, 60, 35.0, 5.0))

    with pytest.raises(ValueError, match="unknown job 'UNKNOWN'"):
        build_timeline_records(result, _jobs(), "HeatOps")
