from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


def _load_script():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "fetch_temperature_matrix.py"
    )
    spec = spec_from_file_location("heatops_fetch_temperature_script", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fetch_temperature_script_is_import_safe(capsys):
    _load_script()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_hourly_slots_are_inclusive():
    module = _load_script()

    assert module._hourly_slots("08:00", "10:00") == [
        "08:00",
        "09:00",
        "10:00",
    ]


def test_hourly_slots_reject_non_hour_boundary():
    module = _load_script()

    with pytest.raises(ValueError, match="on the hour"):
        module._hourly_slots("08:30", "10:00")
