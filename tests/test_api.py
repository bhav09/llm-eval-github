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
