import json
from pathlib import Path

from heatops.integrations.aoi import build_aoi_from_jobs
from heatops.integrations.fortyguard import FortyGuardClient
from heatops.integrations.temperature_matcher import match_jobs_to_temperatures

ROOT = Path(__file__).resolve().parent.parent
JOBS_PATH = ROOT / "data" / "sample_jobs.json"


# Development date:
# use historical data first so results are reproducible
DATE = "2026-08-24"

TIME_SLOTS = [
    "08:00",
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
    "19:00",
]


with open(JOBS_PATH, "r") as f:
    jobs = json.load(f)


polygon_aoi = build_aoi_from_jobs(jobs)

client = FortyGuardClient()


temperature_matrix = {
    job["id"]: {
        "name": job["name"],
        "temperatures": {}
    }
    for job in jobs
}


for time_slot in TIME_SLOTS:
    print(f"\n=== Fetching {DATE} {time_slot} ===")

    activity_id = client.create_heatmap(
        polygon_aoi=polygon_aoi,
        start_date=DATE,
        start_time=time_slot,
        granularity=100,
    )

    result = client.wait_for_result(activity_id)

    features = result["map_data"]["features"]

    matched_jobs = match_jobs_to_temperatures(
        jobs,
        features
    )

    for job in matched_jobs:
        temperature_matrix[job["id"]]["temperatures"][time_slot] = (
            job["temperature"]
        )


print("\n\nTEMPERATURE MATRIX")
print("=" * 80)

header = f'{"Job":<12}'
for time_slot in TIME_SLOTS:
    header += f'{time_slot:>10}'

print(header)


for job in jobs:
    job_id = job["id"]

    row = f'{job_id:<12}'

    for time_slot in TIME_SLOTS:
        temp = temperature_matrix[job_id]["temperatures"][time_slot]

        if temp is None:
            row += f'{"N/A":>10}'
        else:
            row += f'{temp:>9.2f}°'

    print(row)


output_path = ROOT / "data" / "temperature_matrix.json"

with open(output_path, "w") as f:
    json.dump(
        temperature_matrix,
        f,
        indent=2
    )

print(f"\nSaved matrix to: {output_path}")