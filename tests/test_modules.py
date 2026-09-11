"""Tests that all six module endpoints are reachable."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

# Modules that are still placeholders.
PLACEHOLDER_PATHS = [
    "/api/v1/officers/status",
]

# Module 1 Phase 4, module 2 Phase 5, module 3 Phase 6C, module 5 Phase 7,
# module 6 Phase 8.
IMPLEMENTED_PATHS = [
    "/api/v1/regulations/status",
    "/api/v1/documents/status",
    "/api/v1/queue/module",
    "/api/v1/eligibility/status",
    "/api/v1/feedback/status",
]


def test_placeholder_module_status_endpoints():
    for path in PLACEHOLDER_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json()["status"] == "not_implemented"


def test_implemented_module_status_endpoints():
    for path in IMPLEMENTED_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json()["status"] == "available"
