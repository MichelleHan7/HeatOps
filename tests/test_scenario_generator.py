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


def test_configurable_generation_and_unchanged_registered_defaults():
    import hashlib
    import json

    from heatops.benchmark.scenario_generator import GeneratorSettings

    # Hashes from preregistered generator commit 724a023; works in shallow CI clones.
    hashes = {
        "mild": "fdf8d29b9766267fed6f8e63673cbc0f524ebba3735037fa3a8ef1116d2b2235",
        "hot": "8ff5c272bbf3ab282b42237d1256399cbe9cd350a3c24dfd3cfc0d38456977ec",
        "variable": "18614bad94344b9f6d8c4ebf2f02db8911371d28c0256de9ddfd81aed049c216",
        "flat": "cb0c96c55f5c6b2514a7eb4959476666d3462230792a3dceaadaffa80e406acb",
        "spatial": "b39fc369605eb2125a4a511cfd08a9db8a61dc243057e9f0eb74c05924aaa053",
    }
    for family in FAMILIES:
        content = json.dumps(
            generate_scenario(10, 2, 10000, family).to_dict(), sort_keys=True
        )
        assert hashlib.sha256(content.encode()).hexdigest() == hashes[family]
    settings = GeneratorSettings(
        shift_start="09:00",
        shift_end="17:00",
        duration_choices=(30,),
        max_priority=1,
        intensity_min=1,
        intensity_max=1,
        center_latitude=40,
        center_longitude=-75,
        skills=("basic", "repair"),
        temperature_mean_c=28,
        temperature_amplitude_c=2,
    )
    s = generate_scenario(5, 2, 42, settings=settings)
    validate_scenario(s)
    assert all(
        j.duration_minutes == 30 and j.priority == 1 and j.physical_intensity == 1
        for j in s.jobs
    )
    assert all(w.shift_start == "09:00" for w in s.workers)
