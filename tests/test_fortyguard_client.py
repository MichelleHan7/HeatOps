from unittest.mock import Mock

import pytest
import requests

from heatops.integrations.fortyguard import (
    FortyGuardActivityError,
    FortyGuardAPIError,
    FortyGuardClient,
    FortyGuardConfigurationError,
    FortyGuardResponseError,
    FortyGuardTimeoutError,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, invalid_json=False):
        self.payload = payload
        self.status_code = status_code
        self.invalid_json = invalid_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid JSON")
        return self.payload


def _client(session=None, sleeps=None, **kwargs):
    sleep_calls = sleeps if sleeps is not None else []
    return FortyGuardClient(
        api_key="test-api-key",
        base_url="https://fortyguard.test/",
        session=session or Mock(),
        sleep=sleep_calls.append,
        **kwargs,
    )


def test_client_initializes_from_environment(monkeypatch):
    monkeypatch.setenv("FORTYGUARD_API_KEY", "test-api-key")
    monkeypatch.setenv("FORTYGUARD_BASE_URL", "https://example.test/")

    client = FortyGuardClient()

    assert client.api_key == "test-api-key"
    assert client.base_url == "https://example.test"
    assert client.headers["api-key"] == "test-api-key"


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("FORTYGUARD_API_KEY", raising=False)

    with pytest.raises(FortyGuardConfigurationError, match="API_KEY"):
        FortyGuardClient()


def test_create_heatmap_returns_validated_activity_id():
    session = Mock()
    session.request.return_value = FakeResponse(
        {"data": {"activity_id": "activity-123"}}
    )
    client = _client(session)
    polygon = {"type": "Polygon", "coordinates": []}

    activity_id = client.create_heatmap(polygon, "2026-08-24", "08:00")

    assert activity_id == "activity-123"
    session.request.assert_called_once_with(
        "POST",
        "https://fortyguard.test/v1/heatmap",
        headers=client.headers,
        timeout=30,
        json={
            "polygon_aoi": polygon,
            "date_time": {
                "start_date": "2026-08-24",
                "start_time": "08:00",
                "filter_type": 1,
            },
            "granularity": 100,
        },
    )


def test_transient_response_is_retried_with_bounded_backoff():
    session = Mock()
    session.request.side_effect = [
        FakeResponse({"error": "busy"}, status_code=503),
        FakeResponse({"data": {"activity_id": "activity-123"}}),
    ]
    sleeps = []
    client = _client(
        session,
        sleeps,
        max_request_attempts=2,
        retry_backoff_seconds=0.25,
    )

    assert client.create_heatmap({}, "2026-08-24", "08:00") == "activity-123"
    assert session.request.call_count == 2
    assert sleeps == [0.25]


def test_auth_error_is_not_retried():
    session = Mock()
    session.request.return_value = FakeResponse({}, status_code=401)
    client = _client(session, max_request_attempts=3)

    with pytest.raises(FortyGuardAPIError, match="HTTP 401"):
        client.create_heatmap({}, "2026-08-24", "08:00")

    assert session.request.call_count == 1


def test_request_exception_is_retried_then_raises_domain_error():
    session = Mock()
    session.request.side_effect = requests.ConnectionError("offline")
    client = _client(session, max_request_attempts=2, retry_backoff_seconds=0)

    with pytest.raises(FortyGuardAPIError, match="after 2 attempts"):
        client.create_heatmap({}, "2026-08-24", "08:00")

    assert session.request.call_count == 2


def test_create_heatmap_rejects_malformed_response():
    session = Mock()
    session.request.return_value = FakeResponse({"data": {}})

    with pytest.raises(FortyGuardResponseError, match="activity_id"):
        _client(session).create_heatmap({}, "2026-08-24", "08:00")


def test_invalid_json_is_reported_as_response_error():
    session = Mock()
    session.request.return_value = FakeResponse(invalid_json=True)

    with pytest.raises(FortyGuardResponseError, match="invalid JSON"):
        _client(session).create_heatmap({}, "2026-08-24", "08:00")


def test_wait_for_result_polls_until_success_without_printing(capsys):
    session = Mock()
    session.request.side_effect = [
        FakeResponse({"data": {"status": "pending"}}),
        FakeResponse({"data": {"status": "completed", "result": {"features": []}}}),
    ]
    sleeps = []

    result = _client(session, sleeps).wait_for_result(
        "activity-123", poll_interval=2, max_attempts=2
    )

    assert result == {"features": []}
    assert sleeps == [2]
    assert capsys.readouterr().out == ""


def test_wait_for_result_raises_on_failed_activity():
    session = Mock()
    session.request.return_value = FakeResponse(
        {"data": {"status": "failed", "message": "invalid AOI"}}
    )

    with pytest.raises(FortyGuardActivityError, match="invalid AOI"):
        _client(session).wait_for_result("activity-123", max_attempts=1)


def test_wait_for_result_times_out_after_exact_attempt_limit():
    session = Mock()
    session.request.return_value = FakeResponse({"data": {"status": "processing"}})
    sleeps = []

    with pytest.raises(FortyGuardTimeoutError, match="3 status checks"):
        _client(session, sleeps).wait_for_result(
            "activity-123", poll_interval=1, max_attempts=3
        )

    assert session.request.call_count == 3
    assert sleeps == [1, 1]


def test_wait_for_result_rejects_malformed_status_schema():
    session = Mock()
    session.request.return_value = FakeResponse({"data": {}})

    with pytest.raises(FortyGuardResponseError, match="data.status"):
        _client(session).wait_for_result("activity-123", max_attempts=1)
