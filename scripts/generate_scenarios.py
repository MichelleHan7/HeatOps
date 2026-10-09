import argparse
import json
from pathlib import Path

from heatops.benchmark.scenario_generator import (
    FAMILIES,
    GeneratorSettings,
    generate_scenario,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jobs", type=int, default=10)
    p.add_argument("--crews", type=int, default=2)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--family", choices=FAMILIES, default="hot")
    p.add_argument("--output", default="reports/scenario.json")
    p.add_argument("--settings", type=Path, help="Optional GeneratorSettings JSON")
    a = p.parse_args()
    settings = (
        GeneratorSettings(**json.loads(a.settings.read_text())) if a.settings else None
    )
    generate_scenario(a.jobs, a.crews, a.seed, a.family, settings=settings).save(
        a.output
    )


if __name__ == "__main__":
    main()
