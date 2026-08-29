import pytest

from heatops.domain.time_utils import minutes_to_time, time_to_minutes


def test_time_to_minutes():
    assert time_to_minutes("08:00") == 480
    assert time_to_minutes("13:30") == 810


def test_minutes_to_time():
    assert minutes_to_time(480) == "08:00"
    assert minutes_to_time(810) == "13:30"


@pytest.mark.parametrize("value", ["25:00", "12:60", "not-a-time"])
def test_time_to_minutes_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        time_to_minutes(value)


def test_minutes_to_time_rejects_negative_values():
    with pytest.raises(ValueError):
        minutes_to_time(-1)
