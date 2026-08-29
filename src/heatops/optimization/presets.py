from heatops.domain.models import OptimizationWeights

OPERATIONS_FIRST = OptimizationWeights(heat=0.0, delay=1.0)
BALANCED = OptimizationWeights(heat=0.5, delay=0.5)
HEAT_FIRST = OptimizationWeights(heat=1.0, delay=0.0)

PRESETS = {
    "operations_first": OPERATIONS_FIRST,
    "balanced": BALANCED,
    "heat_first": HEAT_FIRST,
}


def get_preset(name: str) -> OptimizationWeights:
    try:
        return PRESETS[name]
    except KeyError as error:
        valid_names = ", ".join(PRESETS)
        raise ValueError(
            f"Unknown optimization preset {name!r}. Choose from: {valid_names}."
        ) from error


def weights_from_heat_priority(heat_priority: float) -> OptimizationWeights:
    """Convert an interpretable 0-100 control to normalized objective weights."""

    if not 0 <= heat_priority <= 100:
        raise ValueError("heat_priority must be between 0 and 100.")

    heat_weight = heat_priority / 100
    return OptimizationWeights(
        heat=heat_weight,
        delay=1 - heat_weight,
    )
