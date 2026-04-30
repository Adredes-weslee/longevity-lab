"""Backend smoke tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from longevity_lab.api.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Yield a lifespan-aware API test client."""
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    """The health route should respond with an OK payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_metadata_bootstrap(client: TestClient) -> None:
    """The bootstrap route should return organs and conditions."""
    response = client.get("/api/metadata/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert payload["organs"]
    assert payload["conditions"]


def test_request_id_header_added(client: TestClient) -> None:
    """Responses should include an X-Request-ID header."""
    response = client.get("/api/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id


def test_request_id_header_preserved(client: TestClient) -> None:
    """If a client supplies X-Request-ID, it should be preserved."""
    inbound_request_id = "test-request-id"
    response = client.get("/api/health", headers={"X-Request-ID": inbound_request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == inbound_request_id


def test_request_id_header_rejects_invalid_input(client: TestClient) -> None:
    """Invalid inbound request IDs should be replaced with a safe generated value."""
    inbound_request_id = "bad id"
    response = client.get("/api/health", headers={"X-Request-ID": inbound_request_id})
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id != inbound_request_id
    assert len(request_id) == 32


def test_scenario_compare(client: TestClient) -> None:
    """The compare route should return baseline, candidate, and deltas."""
    payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["baseline"]["conditions"]
    assert body["candidate"]["conditions"]
    assert body["organ_deltas"]


def test_scenario_compare_missing_baseline_fields_uses_defaults(client: TestClient) -> None:
    """Missing baseline fields should fall back to safe schema defaults."""
    full_payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    expected = client.post("/api/scenario/compare", json=full_payload)
    assert expected.status_code == 200

    payload_missing = {
        **full_payload,
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
        },
    }
    response = client.post("/api/scenario/compare", json=payload_missing)
    assert response.status_code == 200
    assert response.json() == expected.json()


def test_scenario_compare_missing_candidate_fields_uses_defaults(client: TestClient) -> None:
    """Missing candidate fields should fall back to safe schema defaults."""
    full_payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    expected = client.post("/api/scenario/compare", json=full_payload)
    assert expected.status_code == 200

    payload_missing = {
        **full_payload,
        "candidate": {
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload_missing)
    assert response.status_code == 200
    assert response.json() == expected.json()


def test_scenario_compare_out_of_range_still_422(client: TestClient) -> None:
    """Out-of-range values should still return a validation error."""
    payload = {
        "baseline": {
            "age": 10,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload)
    assert response.status_code == 422


def test_scenario_compare_unknown_extra_field_still_422(client: TestClient) -> None:
    """Unknown extra fields should still return a validation error."""
    payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
            "unknown_extra": 1,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload)
    assert response.status_code == 422
