"""Password hashing on the standard library's ``hashlib.scrypt``.

Not argon2 or bcrypt on purpose: a dependency is declared here only when a phase
needs one and CI pip-audits every one, so a hashing library would be permanent
CVE surface for a job the stdlib already does. The stored form describes itself
(``scrypt$n$r$p$salt$hash``, base64), so a later cost bump still verifies older
hashes. The random salt feeds no rendered surface or report, so it is no
determinism violation — identical passwords hashing differently is the point.
"""

import base64
import hashlib
import hmac
import secrets

SCHEME, SALT_BYTES, KEY_BYTES = "scrypt", 16, 32
N, R, P = 2**14, 8, 1  # ~16 MiB per hash: the standard interactive scrypt cost


def _derive(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=length)


def hash_password(password: str) -> str:
    """Hash ``password`` under a fresh random salt; returns the value to store."""
    salt, b64 = secrets.token_bytes(SALT_BYTES), base64.b64encode
    digest = _derive(password, salt, N, R, P, KEY_BYTES)
    return f"{SCHEME}${N}${R}${P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """``False`` — never an exception — for an empty, malformed or foreign-scheme value."""
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != SCHEME:
        return False
    try:
        n, r, p = (int(part) for part in parts[1:4])
        salt, expected = base64.b64decode(parts[4]), base64.b64decode(parts[5])
        candidate = _derive(password, salt, n, r, p, len(expected))
    except ValueError:  # bad integer, bad base64, or parameters scrypt refuses
        return False
    return hmac.compare_digest(candidate, expected)
