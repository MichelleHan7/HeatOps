import pytest

from heatops.benchmark.scenario_generator import (
    FAMILIES,
    generate_scenario,
    scenario_from_dict,
)
from heatops.benchmark.scenario_validation import validate_scenario


@pytest.mark.parametrize("n,c", [(5, 1), (10, 2), (25, 5), (50, 5), (100, 10)])
@pytest.mark.parametrize("family", FAMILIES)
def test_witness_and_reproducible_generation(n, c, family):
    s = generate_scenario(n, c, 42, family)
    validate_scenario(s)
    assert s.to_dict() == generate_scenario(n, c, 42, family).to_dict()
    assert s.to_dict() != generate_scenario(n, c, 43, family).to_dict()
    assert s.metadata["source"] == "synthetic"
    assert scenario_from_dict(s.to_dict()).to_dict() == s.to_dict()


def test_reject_impossible_size_and_missing_data():
    with pytest.raises(ValueError):
        generate_scenario(100, 1)
    s = generate_scenario()
    s.temperature_matrix[s.jobs[0].id]["temperatures"].pop("08:00")
    with pytest.raises(ValueError):
        validate_scenario(s)
