"""Contract for password hashing: salted, self-describing, and never raising."""

import base64
import hashlib

from driftless.auth.passwords import hash_password, verify_password


def test_hashing_is_salted_and_verifies_only_the_right_password() -> None:
    stored = hash_password("correct horse")
    assert "correct horse" not in stored and stored.startswith("scrypt$")
    assert verify_password("correct horse", stored) is True
    assert verify_password("Correct horse", stored) is False
    assert hash_password("same") != hash_password("same")  # per-password random salt


def test_a_malformed_stored_value_is_false_never_an_exception() -> None:
    bad = ["", "not-a-hash", "scrypt$1$2$3", "argon2$1$8$1$c2FsdA==$aGFzaA==", "scrypt$x$8$1$a$b"]
    for stored in bad:
        assert verify_password("anything", stored) is False


def test_a_hash_made_with_other_parameters_still_verifies() -> None:
    """The stored string describes itself, so a later cost bump still verifies it."""
    salt, encode = b"sixteen bytes!!!", base64.b64encode
    digest = hashlib.scrypt(b"pw", salt=salt, n=1024, r=8, p=1, dklen=32)
    cheap = f"scrypt$1024$8$1${encode(salt).decode()}${encode(digest).decode()}"
    assert verify_password("pw", cheap) is True and verify_password("nope", cheap) is False
