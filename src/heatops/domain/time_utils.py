def time_to_minutes(value: str) -> int:
    if not isinstance(value, str):
        raise TypeError("Time values must be strings in HH:MM format.")

    parts = value.split(":")

    if len(parts) != 2:
        raise ValueError(f"Invalid time {value!r}; expected HH:MM.")

    try:
        hours, minutes = map(int, parts)
    except ValueError as error:
        raise ValueError(f"Invalid time {value!r}; expected numeric HH:MM.") from error

    if not 0 <= hours <= 24 or not 0 <= minutes < 60:
        raise ValueError(f"Invalid time {value!r}; expected HH:MM.")

    if hours == 24 and minutes != 0:
        raise ValueError("24 is only valid as 24:00.")

    return hours * 60 + minutes


def minutes_to_time(value: int) -> str:
    if not isinstance(value, int):
        raise TypeError("Minutes must be an integer.")

    if value < 0:
        raise ValueError("Minutes cannot be negative.")

    hours = value // 60
    minutes = value % 60
    return f"{hours:02d}:{minutes:02d}"
