import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from heatops.integrations.fortyguard import FortyGuardAPIError

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_SPEC = spec_from_file_location("heatops_demo_app", APP_PATH)
assert APP_SPEC is not None and APP_SPEC.loader is not None
app = module_from_spec(APP_SPEC)
sys.modules[APP_SPEC.name] = app
APP_SPEC.loader.exec_module(app)


def test_demo_scenario_loads_without_api_key(monkeypatch):
    monkeypatch.delenv("FORTYGUARD_API_KEY", raising=False)

    scenario = app.load_demo_scenario()

    assert len(scenario.jobs) == 5
    assert scenario.selected_worker.id == "CREW-001"
    assert scenario.metadata["temperature_data"]["provider"] == "FortyGuard"


@pytest.mark.parametrize(
    ("label", "expected_key", "expected_weights"),
    [
        ("Operations-first", "operations_first", (0.0, 1.0)),
        ("Balanced", "balanced", (0.5, 0.5)),
        ("Heat-first", "heat_first", (1.0, 0.0)),
        ("Custom", "custom", (0.8, 0.2)),
    ],
)
def test_dashboard_modes_and_slider_resolve_to_expected_weights(
    label,
    expected_key,
    expected_weights,
):
    mode_key, weights = app.resolve_weights(label, 80)

    assert mode_key == expected_key
    assert weights.normalized() == pytest.approx(expected_weights)


def test_dashboard_state_uses_shared_evaluation_metrics():
    scenario = app.load_demo_scenario()

    state = app.build_dashboard_state(
        scenario,
        scenario.temperature_matrix,
        "Heat-first",
        50,
    )

    assert state.mode_key == "heat_first"
    assert state.comparison is state.preset_comparisons["heat_first"]
    assert state.comparison.optimized_metrics.total_heat_load == pytest.approx(
        state.comparison.optimized_result.total_heat_load
    )
    assert state.comparison.optimized_metrics.total_heat_load < (
        state.comparison.baseline_metrics.total_heat_load
    )
    assert [record.mode for record in state.tradeoff_records] == [
        "operations_first",
        "balanced",
        "heat_first",
    ]


def test_custom_dashboard_state_adds_tradeoff_point():
    scenario = app.load_demo_scenario()

    state = app.build_dashboard_state(
        scenario,
        scenario.temperature_matrix,
        "Custom",
        80,
    )

    assert state.weights.heat == 0.8
    assert state.weights.delay == pytest.approx(0.2)
    assert state.tradeoff_records[-1].mode == "custom"
    assert state.tradeoff_records[-1].heat_weight_percent == 80


def test_live_failure_falls_back_without_leaking_api_key(tmp_path, monkeypatch):
    secret = "super-secret-key"
    monkeypatch.setenv("FORTYGUARD_API_KEY", secret)
    scenario = app.load_demo_scenario()

    class FailingClient:
        def create_heatmap(self, **kwargs):
            raise FortyGuardAPIError(f"request failed with credential {secret}")

        def wait_for_result(self, *args, **kwargs):
            raise AssertionError("Polling should not run after create failure.")

    source = app.resolve_temperature_source(
        scenario,
        True,
        client=FailingClient(),
        cache_dir=tmp_path,
    )

    assert source.source == "snapshot"
    assert source.matrix == scenario.temperature_matrix
    assert "unavailable" in source.detail
    assert secret not in source.detail
    assert secret not in source.label


def test_missing_scenario_has_readable_error(tmp_path):
    with pytest.raises(app.ScenarioLoadError, match="Could not load"):
        app.load_demo_scenario(tmp_path / "missing")


def test_streamlit_app_smoke_renders_cached_demo_without_secrets(monkeypatch):
    monkeypatch.delenv("FORTYGUARD_API_KEY", raising=False)
    dashboard = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not dashboard.exception
    assert dashboard.title[0].value == "HeatOps"
    assert dashboard.selectbox[0].options == list(app.MODE_OPTIONS)
    assert dashboard.selectbox[0].value == "Balanced"
    assert dashboard.slider[0].disabled is True
    assert dashboard.button[0].label == "Optimize schedule"
    assert len(dashboard.metric) == 6
    assert dashboard.metric[0].label == "Heat Load reduction"
    assert any("Bundled FortyGuard snapshot" in item.value for item in dashboard.info)
    assert any(
        "Baseline vs optimized timeline" in item.value for item in dashboard.subheader
    )


def test_streamlit_app_can_optimize_custom_slider_mode(monkeypatch):
    monkeypatch.delenv("FORTYGUARD_API_KEY", raising=False)
    dashboard = AppTest.from_file(APP_PATH, default_timeout=30).run()
    dashboard.selectbox[0].select("Custom").run()

    assert dashboard.slider[0].disabled is False

    dashboard.slider[0].set_value(80).run()
    dashboard.button[0].click().run()
    state = dashboard.session_state["dashboard_state"]

    assert not dashboard.exception
    assert state.mode_key == "custom"
    assert state.weights.normalized() == pytest.approx((0.8, 0.2))
    assert len(dashboard.metric) == 6
