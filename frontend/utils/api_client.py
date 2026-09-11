"""Thin wrapper around the CivicAI backend API.

Every Streamlit page talks to the backend through this file, so the HTTP
details stay in one place.
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Read the same .env file the backend uses.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"
TIMEOUT_SECONDS = 10


def _url(path: str) -> str:
    return f"{BACKEND_URL}{API_PREFIX}{path}"


def get(path: str, token: str | None = None) -> dict:
    """Send a GET request and return the JSON response."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.get(_url(path), headers=headers, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def post(path: str, payload: dict, token: str | None = None) -> dict:
    """Send a POST request with a JSON body and return the JSON response."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.post(
        _url(path), json=payload, headers=headers, timeout=TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()


def upload(
    path: str, files: dict, data: dict | None = None, token: str | None = None
) -> dict:
    """Send a multipart POST (a file upload) and return the JSON response."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.post(
        _url(path),
        files=files,
        data=data or {},
        headers=headers,
        # OCR on a large scan takes longer than a normal API call.
        timeout=TIMEOUT_SECONDS * 6,
    )
    response.raise_for_status()
    return response.json()


def check_backend() -> dict | None:
    """Return the /health response, or None if the backend is unreachable."""
    try:
        return get("/health")
    except requests.RequestException:
        return None
