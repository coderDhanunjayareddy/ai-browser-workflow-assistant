from __future__ import annotations

from app.product import security


def test_password_hashing_round_trip_and_wrong_password_fails():
    encoded = security.hash_password("correct horse battery staple")
    assert encoded.startswith("pbkdf2_sha256$")
    assert security.verify_password("correct horse battery staple", encoded) is True
    assert security.verify_password("wrong password", encoded) is False


def test_signed_token_round_trip_and_tamper_rejection():
    token = security.create_token("user-1", "session-1")
    payload = security.decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["sid"] == "session-1"
    assert security.decode_token(token + "tamper") is None
    assert len(security.token_hash(token)) == 64
