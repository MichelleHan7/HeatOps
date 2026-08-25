import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv(
    "FORTYGUARD_BASE_URL",
    "https://api.fortyguard.com"
)


class FortyGuardClient:
    def __init__(self):
        self.api_key = os.getenv("FORTYGUARD_API_KEY")

        if not self.api_key:
            raise ValueError(
                "FORTYGUARD_API_KEY is missing. "
                "Add it to your .env file."
            )

        self.headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def create_heatmap(
        self,
        polygon_aoi,
        start_date,
        start_time,
        granularity=100,
    ):
        payload = {
            "polygon_aoi": polygon_aoi,
            "date_time": {
                "start_date": start_date,
                "start_time": start_time,
                "filter_type": 1,
            },
            "granularity": granularity,
        }

        response = requests.post(
            f"{BASE_URL}/v1/heatmap",
            headers=self.headers,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        return data["data"]["activity_id"]

    def wait_for_result(
        self,
        activity_id,
        poll_interval=5,
        max_attempts=120,
    ):
        url = f"{BASE_URL}/v1/status/{activity_id}"

        for _ in range(max_attempts):
            response = requests.get(
                url,
                headers=self.headers,
                timeout=30,
            )

            response.raise_for_status()

            data = response.json()["data"]
            status = data["status"].lower()

            print(f"FortyGuard status: {status}")

            if status in ("completed", "succeeded"):
                return data["result"]

            if status in ("failed", "error"):
                raise RuntimeError(
                    f"FortyGuard activity {activity_id} failed."
                )

            time.sleep(poll_interval)

        raise TimeoutError(
            f"FortyGuard activity {activity_id} timed out."
        )