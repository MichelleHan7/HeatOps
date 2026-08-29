import os
import time
from collections.abc import Callable
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://api.fortyguard.com"
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class FortyGuardError(RuntimeError):
    """Base exception for recoverable FortyGuard integration failures."""


class FortyGuardConfigurationError(FortyGuardError, ValueError):
    """Raised when required client configuration is absent or invalid."""


class FortyGuardAPIError(FortyGuardError):
    """Raised when an HTTP request cannot be completed successfully."""


class FortyGuardResponseError(FortyGuardError):
    """Raised when the API response does not match the expected schema."""


class FortyGuardActivityError(FortyGuardError):
    """Raised when FortyGuard reports that an activity failed."""


class FortyGuardTimeoutError(FortyGuardError, TimeoutError):
    """Raised when an activity does not finish within bounded polling."""


class FortyGuardClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        request_timeout_seconds: float = 30,
        max_request_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        resolved_api_key = api_key or os.getenv("FORTYGUARD_API_KEY")

        if not resolved_api_key or not resolved_api_key.strip():
            raise FortyGuardConfigurationError(
                "FORTYGUARD_API_KEY is missing. Add it to your .env file."
            )

        if request_timeout_seconds <= 0:
            raise FortyGuardConfigurationError(
                "request_timeout_seconds must be positive."
            )

        if max_request_attempts <= 0:
            raise FortyGuardConfigurationError("max_request_attempts must be positive.")

        if retry_backoff_seconds < 0:
            raise FortyGuardConfigurationError(
                "retry_backoff_seconds cannot be negative."
            )

        self.api_key = resolved_api_key.strip()
        self.base_url = base_url or os.getenv("FORTYGUARD_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = self.base_url.rstrip("/")
        self.session = session or requests.Session()
        self.request_timeout_seconds = request_timeout_seconds
        self.max_request_attempts = max_request_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep = sleep
        self.headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request_json(
        self,
        method: str,
        path: str,
        **request_kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        for attempt in range(self.max_request_attempts):
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=self.request_timeout_seconds,
                    **request_kwargs,
                )
            except requests.RequestException as error:
                if attempt + 1 == self.max_request_attempts:
                    raise FortyGuardAPIError(
                        f"FortyGuard {method} {path} failed after "
                        f"{self.max_request_attempts} attempts."
                    ) from error

                self.sleep(self.retry_backoff_seconds * (2**attempt))
                continue

            if (
                response.status_code in TRANSIENT_STATUS_CODES
                and attempt + 1 < self.max_request_attempts
            ):
                self.sleep(self.retry_backoff_seconds * (2**attempt))
                continue

            try:
                response.raise_for_status()
            except requests.RequestException as error:
                raise FortyGuardAPIError(
                    f"FortyGuard {method} {path} returned HTTP {response.status_code}."
                ) from error

            try:
                payload = response.json()
            except ValueError as error:
                raise FortyGuardResponseError(
                    f"FortyGuard {method} {path} returned invalid JSON."
                ) from error

            if not isinstance(payload, dict):
                raise FortyGuardResponseError(
                    f"FortyGuard {method} {path} returned a non-object response."
                )

            return payload

        raise AssertionError("The bounded request loop exited unexpectedly.")

    def create_heatmap(
        self,
        polygon_aoi: dict[str, Any],
        start_date: str,
        start_time: str,
        granularity: int = 100,
    ) -> str:
        if not isinstance(polygon_aoi, dict):
            raise TypeError("polygon_aoi must be a GeoJSON object.")

        if not start_date or not start_time:
            raise ValueError("start_date and start_time are required.")

        if isinstance(granularity, bool) or not isinstance(granularity, int):
            raise TypeError("granularity must be an integer.")

        if granularity <= 0:
            raise ValueError("granularity must be positive.")

        payload = {
            "polygon_aoi": polygon_aoi,
            "date_time": {
                "start_date": start_date,
                "start_time": start_time,
                "filter_type": 1,
            },
            "granularity": granularity,
        }
        response = self._request_json("POST", "/v1/heatmap", json=payload)

        try:
            activity_id = response["data"]["activity_id"]
        except (KeyError, TypeError) as error:
            raise FortyGuardResponseError(
                "FortyGuard create response is missing data.activity_id."
            ) from error

        if not isinstance(activity_id, str) or not activity_id.strip():
            raise FortyGuardResponseError(
                "FortyGuard data.activity_id must be a non-empty string."
            )

        return activity_id

    def wait_for_result(
        self,
        activity_id: str,
        poll_interval: float = 5,
        max_attempts: int = 120,
    ) -> dict[str, Any]:
        if not activity_id or not activity_id.strip():
            raise ValueError("activity_id must be a non-empty string.")

        if poll_interval < 0:
            raise ValueError("poll_interval cannot be negative.")

        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")

        path = f"/v1/status/{activity_id}"

        for attempt in range(max_attempts):
            response = self._request_json("GET", path)

            try:
                data = response["data"]
                status = data["status"]
            except (KeyError, TypeError) as error:
                raise FortyGuardResponseError(
                    "FortyGuard status response is missing data.status."
                ) from error

            if not isinstance(status, str):
                raise FortyGuardResponseError(
                    "FortyGuard data.status must be a string."
                )

            normalized_status = status.lower()

            if normalized_status in {"completed", "succeeded"}:
                result = data.get("result")

                if not isinstance(result, dict):
                    raise FortyGuardResponseError(
                        "Completed FortyGuard activity is missing an object result."
                    )

                return result

            if normalized_status in {"failed", "error"}:
                detail = data.get("message") or data.get("error")
                suffix = f": {detail}" if detail else "."
                raise FortyGuardActivityError(
                    f"FortyGuard activity {activity_id} failed{suffix}"
                )

            if attempt + 1 < max_attempts:
                self.sleep(poll_interval)

        raise FortyGuardTimeoutError(
            f"FortyGuard activity {activity_id} did not complete after "
            f"{max_attempts} status checks."
        )
