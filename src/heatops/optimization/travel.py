"""Deterministic approximate travel; no routing-service dependency."""

from dataclasses import dataclass, field
from math import asin, ceil, cos, isfinite, radians, sin, sqrt


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    for lat, lon in (a, b):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid travel coordinates")
    lat1, lat2 = radians(a[0]), radians(b[0])
    dlat, dlon = lat2 - lat1, radians(b[1] - a[1])
    return (
        6371.0088
        * 2
        * asin(
            min(
                1, sqrt(sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2)
            )
        )
    )


@dataclass(frozen=True)
class TravelConfig:
    enabled: bool = False
    speed_kmh: float = 30.0
    distance_multiplier: float = 1.3
    # Optional directed durations. Keys use job IDs and depot:<worker ID>.
    minutes_matrix: dict[tuple[str, str], int] = field(default_factory=dict)
    max_jobs: int = 25

    def __post_init__(self):
        if not isfinite(self.speed_kmh) or self.speed_kmh <= 0:
            raise ValueError("Travel speed must be positive")
        if not isfinite(self.distance_multiplier) or self.distance_multiplier < 1:
            raise ValueError("Distance multiplier must be at least 1")
        if self.max_jobs < 1:
            raise ValueError("Travel max_jobs must be positive")
        for key, value in self.minutes_matrix.items():
            if (
                len(key) != 2
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    "Travel matrix requires directed pairs and nonnegative integer minutes"
                )

    def leg(self, from_id, to_id, a, b):
        distance = haversine_km(a, b) * self.distance_multiplier
        minutes = self.minutes_matrix.get((from_id, to_id))
        if minutes is None:
            minutes = ceil(distance / self.speed_kmh * 60)
        return distance, minutes
