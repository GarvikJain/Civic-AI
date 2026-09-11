"""Tests that all six module endpoints are reachable."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

MODULE_PATHS = [
    "/api/v1/regulations/status",
    "/api/v1/documents/status",
    "/api/v1/queue/status",
    "/api/v1/officers/status",
    "/api/v1/eligibility/status",
    "/api/v1/feedback/status",
]


def test_module_status_endpoints():
    for path in MODULE_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json()["status"] == "not_implemented"
