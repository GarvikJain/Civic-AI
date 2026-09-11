"""Tests for password hashing and JWT tokens."""

from backend.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    hashed = hash_password("civicai123")
    assert hashed != "civicai123"
    assert verify_password("civicai123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token():
    token = create_access_token(subject="citizen@example.com", role="citizen")
    payload = decode_access_token(token)
    assert payload["sub"] == "citizen@example.com"
    assert payload["role"] == "citizen"
