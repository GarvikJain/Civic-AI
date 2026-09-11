"""Tests that all six module endpoints are reachable."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

# Module 1 Phase 4 through module 4 Phase 9.
IMPLEMENTED_PATHS = [
    "/api/v1/regulations/status",
    "/api/v1/documents/status",
    "/api/v1/queue/module",
    "/api/v1/eligibility/status",
    "/api/v1/feedback/status",
    "/api/v1/officers/status",
]


PLACEHOLDER_PATHS = []


def test_placeholder_module_status_endpoints():
    """All six CivicAI modules now report as available."""
    assert PLACEHOLDER_PATHS == []


def test_implemented_module_status_endpoints():
    for path in IMPLEMENTED_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json()["status"] == "available"
