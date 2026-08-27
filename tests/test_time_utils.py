from heatops.domain.time_utils import minutes_to_time, time_to_minutes


def test_time_to_minutes():
    assert time_to_minutes("08:00") == 480
    assert time_to_minutes("13:30") == 810


def test_minutes_to_time():
    assert minutes_to_time(480) == "08:00"
    assert minutes_to_time(810) == "13:30"