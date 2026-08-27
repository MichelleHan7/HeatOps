import json
from pathlib import Path

from heatops.integrations.aoi import build_aoi_from_jobs
from heatops.integrations.fortyguard import FortyGuardClient
from heatops.integrations.temperature_matcher import match_jobs_to_temperatures

ROOT = Path(__file__).resolve().parent.parent
JOBS_PATH = ROOT / "data" / "sample_jobs.json"


with open(JOBS_PATH, "r") as f:
    jobs = json.load(f)


print(f"Loaded {len(jobs)} jobs.")


polygon_aoi = build_aoi_from_jobs(jobs)

print("AOI generated.")
print(json.dumps(polygon_aoi, indent=2))


client = FortyGuardClient()

activity_id = client.create_heatmap(
    polygon_aoi=polygon_aoi,

    # Historical test first, so we don't hit the +12h forecast limit.
    start_date="2026-08-24",
    start_time="14:00",

    granularity=100,
)

print("\nSubmitted heatmap.")
print(f"Activity ID: {activity_id}")


result = client.wait_for_result(activity_id)

print("\nHeatmap completed!")


map_data = result.get("map_data", {})
stats_data = result.get("stats_data", {})

features = map_data.get("features", [])

print(f"Number of map tiles: {len(features)}")
print("\nStats:")
print(json.dumps(stats_data, indent=2))

print("\nFirst heatmap feature:")
print(json.dumps(features[0], indent=2))

matched_jobs = match_jobs_to_temperatures(
    jobs,
    features
)

print("\nJob temperatures:")

for job in matched_jobs:
    temperature = job["temperature"]

    if temperature is None:
        print(
            f'{job["id"]} | '
            f'{job["name"]} | '
            f'No matching temperature tile'
        )
    else:
        print(
            f'{job["id"]} | '
            f'{job["name"]} | '
            f'{temperature:.2f}°C | '
            f'Tile {job["tile_id"]}'
        )