from heatops.integrations.fortyguard import FortyGuardClient


def test_client_initializes_with_api_key(monkeypatch):
    monkeypatch.setenv(
        "FORTYGUARD_API_KEY",
        "test-api-key",
    )

    client = FortyGuardClient()

    assert client.api_key == "test-api-key"
    assert client.headers["api-key"] == "test-api-key"
    assert client.headers["Content-Type"] == "application/json"