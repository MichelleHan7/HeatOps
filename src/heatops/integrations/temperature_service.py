import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Literal, cast

from heatops.domain.models import Job, TemperatureMatrix
from heatops.domain.time_utils import time_to_minutes
from heatops.integrations.aoi import build_aoi_from_jobs
from heatops.integrations.fortyguard import FortyGuardClient, FortyGuardError
from heatops.integrations.temperature_matcher import match_jobs_to_temperatures

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"


class TemperatureServiceError(RuntimeError):
    """Base exception for temperature data orchestration failures."""


class TemperatureDataValidationError(TemperatureServiceError, ValueError):
    """Raised when temperature data is incomplete or malformed."""


class TemperatureUnavailableError(TemperatureServiceError):
    """Raised when neither live data nor a valid cache is available."""


@dataclass(frozen=True)
class TemperatureDataMetadata:
    source: Literal["live", "cache"]
    requested_date: str
    data_date: str
    time_slots: tuple[str, ...]
    granularity: int
    generated_at: str
    cache_path: str | None
    activity_ids: tuple[str, ...] = ()
    fallback_reason: str | None = None


@dataclass(frozen=True)
class TemperatureDataResult:
    matrix: TemperatureMatrix
    metadata: TemperatureDataMetadata


def _validated_time_slots(time_slots: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not time_slots:
        raise ValueError("At least one time slot is required.")

    validated = tuple(time_slots)

    for time_slot in validated:
        time_to_minutes(time_slot)

    if len(validated) != len(set(validated)):
        raise ValueError("Time slots must be unique.")

    return validated


def validate_temperature_matrix(
    matrix: TemperatureMatrix,
    jobs: list[Job],
    time_slots: list[str] | tuple[str, ...],
) -> None:
    """Ensure every requested job and time has a finite temperature."""

    validated_slots = _validated_time_slots(time_slots)

    if not isinstance(matrix, dict):
        raise TemperatureDataValidationError("Temperature matrix must be an object.")

    for job in jobs:
        try:
            record = matrix[job.id]
            temperatures = record["temperatures"]
        except (KeyError, TypeError) as error:
            raise TemperatureDataValidationError(
                f"Temperature matrix is missing job {job.id}."
            ) from error

        if not isinstance(temperatures, dict):
            raise TemperatureDataValidationError(
                f"Temperature record for {job.id} must contain an object."
            )

        for time_slot in validated_slots:
            try:
                temperature = temperatures[time_slot]
            except KeyError as error:
                raise TemperatureDataValidationError(
                    f"Temperature matrix is missing {job.id} at {time_slot}."
                ) from error

            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not isfinite(temperature)
            ):
                raise TemperatureDataValidationError(
                    f"Temperature for {job.id} at {time_slot} must be finite."
                )


def _extract_features(result: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        features = result["map_data"]["features"]
    except (KeyError, TypeError) as error:
        raise TemperatureDataValidationError(
            "FortyGuard result is missing map_data.features."
        ) from error

    if not isinstance(features, list):
        raise TemperatureDataValidationError(
            "FortyGuard map_data.features must be a list."
        )

    if any(not isinstance(feature, dict) for feature in features):
        raise TemperatureDataValidationError(
            "Every FortyGuard map feature must be an object."
        )

    return features


def _write_cache(
    cache_dir: Path,
    result: TemperatureDataResult,
    generated_at: datetime,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / (
        f"temperature_matrix_{result.metadata.data_date}_"
        f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    payload = {
        "metadata": asdict(result.metadata),
        "temperature_matrix": result.matrix,
    }
    cache_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return cache_path


def _load_latest_cache(
    cache_dir: Path,
    jobs: list[Job],
    time_slots: tuple[str, ...],
    requested_date: str,
    fallback_reason: str,
) -> TemperatureDataResult:
    candidates = (
        sorted(
            cache_dir.glob("temperature_matrix_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if cache_dir.exists()
        else []
    )

    for cache_path in candidates:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            raw_matrix = payload["temperature_matrix"]
            raw_metadata = payload["metadata"]
            matrix = cast(TemperatureMatrix, raw_matrix)
            validate_temperature_matrix(matrix, jobs, time_slots)
            cached_slots = tuple(raw_metadata["time_slots"])
            metadata = TemperatureDataMetadata(
                source="cache",
                requested_date=requested_date,
                data_date=str(raw_metadata["data_date"]),
                time_slots=time_slots,
                granularity=int(raw_metadata["granularity"]),
                generated_at=str(raw_metadata["generated_at"]),
                cache_path=str(cache_path),
                activity_ids=tuple(raw_metadata.get("activity_ids", ())),
                fallback_reason=fallback_reason,
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue

        if not set(time_slots).issubset(cached_slots):
            continue

        return TemperatureDataResult(matrix=matrix, metadata=metadata)

    raise TemperatureUnavailableError(
        f"No valid cached temperature matrix was found in {cache_dir}."
    )


def fetch_temperature_data(
    jobs: list[Job],
    requested_date: str,
    time_slots: list[str] | tuple[str, ...],
    *,
    client: FortyGuardClient | None = None,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    granularity: int = 100,
    allow_cache_fallback: bool = True,
    aoi_padding: float = 0.005,
    poll_interval: float = 5,
    max_poll_attempts: int = 120,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> TemperatureDataResult:
    """Fetch a validated matrix live, or return the latest valid cached matrix."""

    if not jobs:
        raise ValueError("At least one job is required.")

    try:
        date.fromisoformat(requested_date)
    except (TypeError, ValueError) as error:
        raise ValueError("requested_date must use YYYY-MM-DD format.") from error

    slots = _validated_time_slots(time_slots)

    if isinstance(granularity, bool) or not isinstance(granularity, int):
        raise TypeError("granularity must be an integer.")

    if granularity <= 0:
        raise ValueError("granularity must be positive.")

    cache_directory = Path(cache_dir)

    try:
        live_client = client or FortyGuardClient()
        polygon_aoi = build_aoi_from_jobs(jobs, padding=aoi_padding)
        matrix: TemperatureMatrix = {
            job.id: {"name": job.name, "temperatures": {}} for job in jobs
        }
        activity_ids = []

        for time_slot in slots:
            activity_id = live_client.create_heatmap(
                polygon_aoi=polygon_aoi,
                start_date=requested_date,
                start_time=time_slot,
                granularity=granularity,
            )
            activity_ids.append(activity_id)
            live_result = live_client.wait_for_result(
                activity_id,
                poll_interval=poll_interval,
                max_attempts=max_poll_attempts,
            )
            features = _extract_features(live_result)

            try:
                matched_jobs = match_jobs_to_temperatures(jobs, features)
            except ValueError as error:
                raise TemperatureDataValidationError(str(error)) from error

            for matched_job in matched_jobs:
                temperature = matched_job["temperature"]

                if temperature is None:
                    raise TemperatureDataValidationError(
                        f"No FortyGuard tile covers {matched_job['id']} at {time_slot}."
                    )

                matrix[matched_job["id"]]["temperatures"][time_slot] = temperature

        validate_temperature_matrix(matrix, jobs, slots)
        generated_at = clock().astimezone(UTC)
        metadata = TemperatureDataMetadata(
            source="live",
            requested_date=requested_date,
            data_date=requested_date,
            time_slots=slots,
            granularity=granularity,
            generated_at=generated_at.isoformat(),
            cache_path=None,
            activity_ids=tuple(activity_ids),
        )
        live_data = TemperatureDataResult(matrix=matrix, metadata=metadata)
        try:
            cache_path = _write_cache(cache_directory, live_data, generated_at)
        except OSError:
            return live_data

        return replace(
            live_data,
            metadata=replace(metadata, cache_path=str(cache_path)),
        )
    except (FortyGuardError, TemperatureDataValidationError) as live_error:
        if not allow_cache_fallback:
            raise TemperatureUnavailableError(
                f"Live FortyGuard temperature retrieval failed: {live_error}"
            ) from live_error

        try:
            return _load_latest_cache(
                cache_directory,
                jobs,
                slots,
                requested_date,
                str(live_error),
            )
        except TemperatureUnavailableError as cache_error:
            raise TemperatureUnavailableError(
                "Live FortyGuard temperature retrieval failed and no valid "
                f"cache is available: {live_error}"
            ) from cache_error
