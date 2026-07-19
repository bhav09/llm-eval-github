import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "checks" in body
    assert body["checks"]["corpus"] is True


def test_recommendations(client):
    response = client.get("/api/recommendations")
    assert response.status_code == 200
    body = response.json()
    assert "model_a" in body
    assert "model_b" in body


def test_list_runs(client):
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert "runs" in response.json()


def test_custom_classify_mock(client):
    response = client.post(
        "/api/classify/custom",
        json={
            "title": "App crashes on login",
            "body": "When I run doctl auth init the client segfaults",
            "model_a": "mock-a",
            "model_b": "mock-b",
            "use_mock": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_a"]["predicted_label"] is not None
    assert body["model_b"]["predicted_label"] is not None
    assert "agreement" in body


def test_custom_classify_requires_different_models(client):
    response = client.post(
        "/api/classify/custom",
        json={
            "title": "Test",
            "body": "body",
            "model_a": "same",
            "model_b": "same",
            "use_mock": True,
        },
    )
    assert response.status_code == 400


def test_corpus_stats(client):
    response = client.get("/api/corpus/stats")
    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_run_issues_filtering(client):
    runs_res = client.get("/api/runs")
    assert runs_res.status_code == 200
    runs = runs_res.json()["runs"]
    if not runs:
        pytest.skip("No preloaded runs found to test issue filtering")
    
    run_id = runs[0]["run_id"]
    
    all_res = client.get(f"/api/runs/{run_id}/issues?dataset_filter=all")
    assert all_res.status_code == 200
    all_body = all_res.json()
    assert "items" in all_body
    
    scored_res = client.get(f"/api/runs/{run_id}/issues?dataset_filter=scored")
    assert scored_res.status_code == 200
    scored_body = scored_res.json()
    assert "items" in scored_body
    
    unscored_res = client.get(f"/api/runs/{run_id}/issues?dataset_filter=unscored")
    assert unscored_res.status_code == 200
    unscored_body = unscored_res.json()
    assert "items" in unscored_body


def test_start_run_custom_settings(client):
    response = client.post(
        "/api/runs",
        json={
            "model_a": "mock-a",
            "model_b": "mock-b",
            "limit": 5,
            "use_mock": True,
            "confirm_spend": True,
            "concurrency": 12,
            "request_timeout_sec": 30,
            "max_retries": 2,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["concurrency"] == 12


def test_start_funnel_custom_settings(client):
    response = client.post(
        "/api/funnel/start",
        json={
            "use_mock": True,
            "confirm_spend": True,
            "concurrency": 15,
            "adjudicator_model": "mock-evaluator",
            "pilot_issue_count": 3,
            "full_issue_count": 8,
            "error_rate_elim": 0.15,
            "invalid_rate_elim": 0.15,
        },
    )
    assert response.status_code in (200, 409)


def test_invalid_settings_validation(client):
    # Test invalid negative concurrency
    response = client.post(
        "/api/runs",
        json={
            "model_a": "mock-a",
            "model_b": "mock-b",
            "limit": 5,
            "use_mock": True,
            "confirm_spend": True,
            "concurrency": -5,
        },
    )
    assert response.status_code == 422

    # Test invalid error rate > 1.0
    response = client.post(
        "/api/funnel/start",
        json={
            "use_mock": True,
            "confirm_spend": True,
            "error_rate_elim": 1.5,
        },
    )
    assert response.status_code == 422
